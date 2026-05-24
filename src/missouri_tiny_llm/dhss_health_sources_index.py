"""Build and query DHSS public-health resource metadata."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw_public" / "dhss_health_sources"
INDEX_PATH = RAW_DIR / "dhss_health_sources_index.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "dhss_health_sources_index_report.json"
SOURCE_NAME = "DHSS public-health resource metadata"


@dataclass(frozen=True)
class HealthPage:
    key: str
    label: str
    url: str
    default_topic: str


PAGES: tuple[HealthPage, ...] = (
    HealthPage("data_home", "DHSS Data, Surveillance Systems & Statistical Reports", "https://health.mo.gov/data/", "data portal"),
    HealthPage("live_births", "DHSS Live Births", "https://health.mo.gov/data/livebirths/index.php", "births/vital statistics"),
    HealthPage("deaths", "DHSS Deaths", "https://health.mo.gov/data/deaths/index.php", "deaths/vital statistics"),
    HealthPage("patient_abstract", "DHSS Patient Abstract System", "https://health.mo.gov/data/patientabstractsystem/index.php", "hospitalizations/PAS"),
    HealthPage("brfss", "DHSS BRFSS", "https://health.mo.gov/data/brfss/", "BRFSS"),
    HealthPage("county_level_study", "DHSS County-Level Study", "https://health.mo.gov/data/cls/index.php", "county-level study"),
    HealthPage("focus", "DHSS FOCUS Articles", "https://health.mo.gov/data/focus/", "vital statistics reports"),
    HealthPage("mophims_profiles", "MOPHIMS Community Data Profiles", "https://healthapps.dhss.mo.gov/MoPhims/ProfileHome", "county profiles"),
    HealthPage("mophims_mica", "MOPHIMS MICA", "https://healthapps.dhss.mo.gov/MoPhims/MICAHome", "MICA"),
)


ANCHOR_PATTERN = re.compile(r"<a\s+[^>]*href=['\"]([^'\"]+)['\"][^>]*>(.*?)</a>", re.I | re.S)
YEAR_PATTERN = re.compile(r"\b(20\d{2}|19\d{2})\b")

MICA_CODE_LABELS = {
    "BM": "Birth MICA",
    "CDDM": "Chronic Disease Deaths MICA",
    "CIM": "Cancer Incidence MICA",
    "DM": "Death MICA",
    "EA": "Asthma Environmental Public Health Tracking",
    "EAQ25": "Air Quality Environmental Public Health Tracking",
    "EBD": "Birth Defects Environmental Public Health Tracking",
    "EBL": "Blood Lead Levels Environmental Public Health Tracking",
    "EC": "COPD Environmental Public Health Tracking",
    "ECM": "Carbon Monoxide Poisoning Environmental Public Health Tracking",
    "EHI": "Heat-Related Illness Environmental Public Health Tracking",
    "EMI": "Myocardial Infarction Environmental Public Health Tracking",
    "ERAD": "Radon Environmental Public Health Tracking",
    "ERM": "Emergency Room MICA",
    "EWQ25": "Water Quality Environmental Public Health Tracking",
    "FM": "Fertility and Pregnancy Rate MICA",
    "IHM": "Inpatient Hospitalization MICA",
    "IM": "Injury MICA",
    "PHM": "Preventable Hospitalization MICA",
    "PM": "Pregnancy MICA",
    "PNM": "Population MICA",
    "PROM": "Procedures MICA",
    "WCM": "WIC Child MICA",
    "WIM": "WIC Infant MICA",
    "WLM": "WIC Linked Prenatal-Postpartum MICA",
    "WPNM": "WIC Prenatal MICA",
    "WPPM": "WIC Postpartum MICA",
}

GENERIC_QUERY_TOKENS = {
    "AND",
    "BUILD",
    "CAN",
    "CHART",
    "CREATE",
    "DATA",
    "DHSS",
    "FOR",
    "GIVE",
    "HEALTH",
    "INDEX",
    "INDEXED",
    "LINK",
    "LINKS",
    "MAKE",
    "MAP",
    "ME",
    "MISSOURI",
    "PUBLIC",
    "QUERY",
    "RESOURCE",
    "RESOURCES",
    "SHOW",
    "SOURCE",
    "SOURCES",
    "TABLE",
    "THE",
    "WHAT",
    "WHERE",
    "WHICH",
}

KEEP_PATTERN = re.compile(
    r"mophims|mica|profile|community data|brfss|behavioral risk|birth|death|vital|focus|patient abstract|"
    r"hospital|emergency room|pas|county-level|county level|cls|chir|health data training|data release|"
    r"surveillance|dashboard|opioid|sudors|movdrs|life expectancy|ypll|age adjustment|hai|essence|"
    r"environmental public health tracking|querybuilder|statistics|report|pdf|xls|xlsx|documentation",
    re.I,
)
SKIP_PATTERN = re.compile(
    r"^(skip to|home$|about us$|contact us$|facebook|twitter|instagram|rss|email us|internet explorer|google chrome|mozilla firefox|mo\.gov|governor kehoe|find an agency|online services)",
    re.I,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def clean_text(value: Any) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", str(value or ""), flags=re.S)
    decoded = html.unescape(without_tags).replace("\xa0", " ")
    return re.sub(r"\s+", " ", decoded).strip()


def normalize_text(value: Any) -> str:
    cleaned = re.sub(r"[^A-Z0-9/-]+", " ", clean_text(value).upper())
    return re.sub(r"\s+", " ", cleaned).strip()


def query_tokens(value: Any) -> set[str]:
    return {
        token
        for token in normalize_text(value).replace("/", " ").replace("-", " ").split()
        if len(token) > 2 and token not in GENERIC_QUERY_TOKENS
    }


def mica_query_parts(url: str) -> tuple[str | None, str | None, str | None]:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    qbc = (query.get("qbc") or [None])[0]
    q = (query.get("q") or [None])[0]
    mode = (query.get("m") or [None])[0]
    return qbc, q, mode


def mode_label(mode: str | None, raw_label: str) -> str | None:
    lowered = raw_label.lower()
    if mode == "1" or "table" in lowered:
        return "Build a Table"
    if mode == "2" or "map" in lowered:
        return "Make a Map"
    if mode == "3" or "chart" in lowered:
        return "Create a Chart"
    return clean_text(raw_label) or None


def normalized_label(raw_label: str, url: str) -> str:
    qbc, _, mode = mica_query_parts(url)
    if qbc in MICA_CODE_LABELS:
        action = mode_label(mode, raw_label)
        if action and normalize_text(raw_label) in {"BUILD A TABLE", "MAKE A MAP", "CREATE A CHART"}:
            return f"{MICA_CODE_LABELS[qbc]} - {action}"
    return clean_text(raw_label)


def resource_type(url: str, label: str) -> str:
    parsed = urlparse(url)
    lowered = f"{url} {label}".lower()
    if "querybuilder.aspx" in lowered or "mophims" in parsed.netloc.lower():
        return "mophims_app"
    if parsed.path.lower().endswith(".pdf") or "/pdf/" in parsed.path.lower():
        return "pdf"
    if parsed.path.lower().endswith((".xls", ".xlsx", ".csv")) or "/xls/" in parsed.path.lower():
        return "download"
    if parsed.netloc.endswith("health.mo.gov"):
        return "dhss_page"
    if parsed.netloc.endswith("dhss.mo.gov"):
        return "dhss_app"
    return "external_page"


def infer_topic(page: HealthPage, label: str, url: str) -> str:
    lowered = f"{page.default_topic} {label} {url}".lower()
    qbc, _, _ = mica_query_parts(url)
    if qbc in MICA_CODE_LABELS or "mica" in lowered or "querybuilder" in lowered:
        if "inpatient" in lowered or "hospital" in lowered or "emergency room" in lowered or qbc in {"IHM", "ERM", "PHM", "PROM"}:
            return "hospitalizations/PAS"
        if "birth" in lowered or qbc in {"BM", "FM", "PM", "WCM", "WIM", "WLM", "WPNM", "WPPM"}:
            return "births/vital statistics"
        if "death" in lowered or qbc in {"DM", "CDDM"}:
            return "deaths/vital statistics"
        if qbc in {"EA", "EAQ25", "EBD", "EBL", "EC", "ECM", "EHI", "EMI", "ERAD", "EWQ25"}:
            return "environmental tracking"
        return "MICA"
    if "profile" in lowered or "community data" in lowered or "profilehome" in lowered:
        return "county profiles"
    if "brfss" in lowered or "behavioral risk" in lowered:
        return "BRFSS"
    if "patient abstract" in lowered or "hospitalization" in lowered or "hospitalisations" in lowered or "emergency room" in lowered or "pas" in lowered:
        return "hospitalizations/PAS"
    if "livebirth" in lowered or "birth" in lowered or "vitalrecords" in lowered:
        return "births/vital statistics"
    if "death" in lowered or "mortality" in lowered:
        return "deaths/vital statistics"
    if "focus" in lowered or "vital statistics" in lowered:
        return "vital statistics reports"
    if "county-level" in lowered or "county level" in lowered or "cls" in lowered:
        return "county-level study"
    if "opioid" in lowered or "sudors" in lowered or "movdrs" in lowered or "surveillance" in lowered or "essence" in lowered:
        return "surveillance dashboards"
    if "hai" in lowered or "health care-associated" in lowered or "healthcare-associated" in lowered:
        return "healthcare-associated infection"
    if "tracking" in lowered or "environmental" in lowered or "gis" in lowered:
        return "environmental tracking"
    if "training" in lowered or "data release" in lowered or "policy" in lowered or "fee schedule" in lowered:
        return "data policy/training"
    return page.default_topic


def year_label(label: str, url: str) -> str | None:
    matches = YEAR_PATTERN.findall(f"{label} {url}")
    return matches[-1] if matches else None


def is_relevant_link(label: str, absolute_url: str) -> bool:
    if not label or SKIP_PATTERN.search(label):
        return False
    if absolute_url.startswith(("mailto:", "tel:")):
        return False
    return bool(KEEP_PATTERN.search(f"{label} {absolute_url}"))


def parse_page_links(page: HealthPage, page_text: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for href, raw_label in ANCHOR_PATTERN.findall(page_text):
        absolute = urljoin(page.url, html.unescape(href))
        label = normalized_label(raw_label, absolute)
        if not is_relevant_link(label, absolute):
            continue
        key = (label, absolute)
        if key in seen:
            continue
        seen.add(key)
        qbc, q, mode = mica_query_parts(absolute)
        records.append(
            {
                "resource_id": hashlib.sha1(f"{page.key}:{label}:{absolute}".encode("utf-8")).hexdigest()[:16],
                "label": label,
                "url": absolute,
                "topic": infer_topic(page, label, absolute),
                "resource_type": resource_type(absolute, label),
                "year_label": year_label(label, absolute),
                "page_key": page.key,
                "page_label": page.label,
                "source_page": page.url,
                "source_host": urlparse(absolute).netloc,
                "mica_code": qbc,
                "mica_query": q,
                "output_mode": mode,
            }
        )
    return records


def top_counts(counter: Counter[str], limit: int = 12) -> list[dict[str, Any]]:
    return [
        {"label": label, "count": count}
        for label, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:limit]
        if label
    ]


def build_dhss_health_sources_index(force: bool = False, delay_seconds: float = 0.03) -> dict[str, Any]:
    if INDEX_PATH.exists() and not force:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (compatible; MissouriPublicDataChat/1.0; +https://github.com/Stroudmj00/missouri-tiny-llm-case-study)",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        }
    )
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    records: list[dict[str, Any]] = []
    pages: list[dict[str, Any]] = []
    seen_global: set[tuple[str, str]] = set()

    for page in PAGES:
        response = session.get(page.url, timeout=60)
        response.raise_for_status()
        text = response.text
        local_page = RAW_DIR / f"{page.key}.html"
        local_page.write_text(text, encoding="utf-8")
        parsed = parse_page_links(page, text)
        deduped: list[dict[str, Any]] = []
        for record in parsed:
            dedupe_key = (record["label"], record["url"])
            if dedupe_key in seen_global:
                continue
            seen_global.add(dedupe_key)
            deduped.append(record)
        records.extend(deduped)
        pages.append(
            {
                "key": page.key,
                "label": page.label,
                "url": page.url,
                "local_file": str(local_page.relative_to(PROJECT_ROOT)),
                "bytes": len(text.encode("utf-8", errors="replace")),
                "sha256": sha256_text(text),
                "resource_count": len(deduped),
            }
        )
        if delay_seconds:
            time.sleep(delay_seconds)

    topics = Counter(record["topic"] for record in records)
    resource_types = Counter(record["resource_type"] for record in records)
    pages_counter = Counter(record["page_label"] for record in records)
    payload = {
        "generated_at_utc": utc_now(),
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "source": SOURCE_NAME,
        "index_path": str(INDEX_PATH.relative_to(PROJECT_ROOT)),
        "page_count": len(pages),
        "record_count": len(records),
        "topic_count": len(topics),
        "resource_type_counts": dict(sorted(resource_types.items())),
        "top_topics": top_counts(topics),
        "top_pages": top_counts(pages_counter),
        "pages": pages,
        "notes": [
            "This index stores DHSS public-health resource metadata and source links only.",
            "It does not parse MOPHIMS/MICA query results, patient-level records, vital-record certificates, or hospital discharge records.",
            "Exact numeric county health, birth/death, BRFSS, and PAS values still require source-specific aggregate parsers with suppression handling.",
        ],
        "records": records,
    }
    write_json(INDEX_PATH, payload)
    write_json(REPORT_PATH, {key: value for key, value in payload.items() if key != "records"})
    return payload


def topic_terms(question: str) -> set[str]:
    lowered = question.lower()
    terms: set[str] = set()
    if any(term in lowered for term in ["profile", "profiles", "county health", "community data"]):
        terms.add("county profiles")
    if "brfss" in lowered or "behavioral risk" in lowered:
        terms.add("BRFSS")
    if any(term in lowered for term in ["mica", "mophims", "query builder", "querybuilder"]):
        terms.add("MICA")
    if any(term in lowered for term in ["birth", "live birth", "vital"]):
        terms.add("births/vital statistics")
    if any(term in lowered for term in ["death", "mortality"]):
        terms.add("deaths/vital statistics")
    if any(term in lowered for term in ["hospital", "hospitalization", "hospitalisation", "patient abstract", "pas", "emergency room", "inpatient"]):
        terms.add("hospitalizations/PAS")
    if any(term in lowered for term in ["focus", "vital statistics report"]):
        terms.add("vital statistics reports")
    if any(term in lowered for term in ["county-level", "county level", "cls"]):
        terms.add("county-level study")
    if any(term in lowered for term in ["surveillance", "opioid", "sudors", "movdrs", "essence"]):
        terms.add("surveillance dashboards")
    if any(term in lowered for term in ["environmental", "tracking", "blood lead", "air quality", "asthma"]):
        terms.add("environmental tracking")
    return terms


def asks_for_summary(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["indexed", "available", "coverage", "what data", "what resources", "what links", "what dhss"])


class DhssHealthSourcesIndex:
    def __init__(self, path: Path = INDEX_PATH) -> None:
        self.path = path
        self._payload: dict[str, Any] | None = None

    def available(self) -> bool:
        return self.path.exists() and self.path.stat().st_size > 0

    def payload(self) -> dict[str, Any]:
        if self._payload is None:
            self._payload = json.loads(self.path.read_text(encoding="utf-8")) if self.available() else {}
        return self._payload

    def records(self) -> list[dict[str, Any]]:
        return list(self.payload().get("records", []))

    def citation(self, matched_rows: int = 0) -> list[dict[str, Any]]:
        payload = self.payload()
        return [
            {
                "dataset": payload.get("source", SOURCE_NAME),
                "category": "Public health",
                "kind": "DHSS public-health resource metadata",
                "lookup_table": "dhss_health_sources_index",
                "year": None,
                "year_range": None,
                "source_files": [
                    {
                        "category": page.get("key"),
                        "category_label": page.get("label"),
                        "file_name": page.get("url"),
                        "row_count": page.get("resource_count"),
                        "bytes": page.get("bytes"),
                        "sha256": page.get("sha256"),
                    }
                    for page in payload.get("pages", [])
                ],
                "source_file_count": payload.get("page_count"),
                "source_rows": payload.get("record_count"),
                "matched_rows": matched_rows,
            }
        ]

    def unavailable_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "The DHSS public-health resource metadata index has not been built yet. Run "
                "`python scripts/build_dhss_health_sources_index.py --force` to index official DHSS health resource links."
            ),
            "retrieved_context_id": "dhss_health_sources_index:missing",
            "retrieved_source": "dhss_health_sources_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "The DHSS health-resource route exists, but the local ignored index is missing.",
            "citations": [],
            "source_rows": [],
        }

    def summary_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        topics = "; ".join(f"{item['label']}: {item['count']}" for item in payload.get("top_topics", [])[:8])
        resource_types = "; ".join(f"{key}: {value}" for key, value in payload.get("resource_type_counts", {}).items())
        return {
            "question": question,
            "answer": (
                "The DHSS public-health resource metadata layer indexes official public DHSS health-data links from "
                f"{payload.get('page_count', 0)} source page(s). It contains {payload.get('record_count', 0):,} resource link(s). "
                f"Top topics: {topics}. Resource types: {resource_types}. "
                "It can return cited links for county profiles, MOPHIMS/MICA query tools, BRFSS, births/deaths, hospitalizations/PAS, county-level study, and vital-statistics FOCUS reports. "
                "It does not parse MOPHIMS/MICA numeric results yet."
            ),
            "retrieved_context_id": "dhss_health_sources_index:summary",
            "retrieved_source": "dhss_health_sources_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local DHSS public-health resource metadata index.",
            "citations": self.citation(matched_rows=payload.get("record_count", 0)),
            "source_rows": [],
        }

    def topic_summary_answer(self, question: str, topics: set[str]) -> dict[str, Any]:
        rows = [record for record in self.records() if record.get("topic") in topics]
        if not rows:
            return self.summary_answer(question)
        topic_counts = Counter(str(row.get("topic", "")) for row in rows)
        type_counts = Counter(str(row.get("resource_type", "")) for row in rows)
        topic_text = "; ".join(f"{label}: {count}" for label, count in sorted(topic_counts.items()))
        type_text = "; ".join(f"{label}: {count}" for label, count in sorted(type_counts.items()))
        examples = "; ".join(
            f"{row['label']} ({row['resource_type']}): {row['url']}"
            for row in sorted(rows, key=lambda item: (str(item.get("topic")), str(item.get("label"))))[:5]
        )
        return {
            "question": question,
            "answer": (
                f"The DHSS public-health resource metadata layer has {len(rows):,} indexed link(s) for this topic request. "
                f"Topic counts: {topic_text}. Resource types: {type_text}. Examples: {examples}. "
                "These are source links and resource metadata, not parsed numeric public-health values."
            ),
            "retrieved_context_id": "dhss_health_sources_index:topic_summary",
            "retrieved_source": "dhss_health_sources_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local DHSS public-health resource metadata index.",
            "citations": self.citation(matched_rows=len(rows)),
            "source_rows": [],
        }

    def rows_for_question(self, question: str) -> list[dict[str, Any]]:
        records = self.records()
        wanted_topics = topic_terms(question)
        if wanted_topics:
            topic_filtered = [record for record in records if record.get("topic") in wanted_topics]
            if topic_filtered:
                records = topic_filtered
        wanted_years = {year for year in re.findall(r"\b(?:20\d{2}|19\d{2})\b", question)}
        if wanted_years:
            year_filtered = [
                record
                for record in records
                if record.get("year_label") in wanted_years or any(year in str(record.get("label", "")) for year in wanted_years)
            ]
            if year_filtered:
                records = year_filtered
        q_tokens = query_tokens(question)
        if q_tokens:
            scored: list[tuple[int, dict[str, Any]]] = []
            for record in records:
                blob = " ".join(str(record.get(key, "")) for key in ["label", "topic", "page_label", "resource_type", "year_label", "mica_code"])
                tokens = query_tokens(blob)
                score = len(q_tokens & tokens)
                label_norm = normalize_text(record.get("label", ""))
                row_url = str(record.get("url", "")).lower()
                question_norm = normalize_text(question)
                if normalize_text(record.get("label", "")) in normalize_text(question):
                    score += 25
                if record.get("mica_code") and str(record["mica_code"]).upper() in normalize_text(question).split():
                    score += 10
                if "PROFILE" in question_norm and ("PROFILEHOME" in row_url.upper() or "COMMUNITY DATA PROFILES" in label_norm):
                    score += 8
                if "BRFSS" in question_norm and ("BRFSS" in label_norm or "brfss" in row_url):
                    score += 8
                if "INPATIENT" in question_norm and record.get("mica_code") == "IHM":
                    score += 8
                if "PATIENT ABSTRACT" in question_norm and "patientabstractsystem" in row_url:
                    score += 8
                if label_norm in {"ABOUT", "BUILD A TABLE", "MAKE A MAP", "CREATE A CHART"}:
                    score -= 3
                if score:
                    scored.append((score, record))
            if scored:
                ranked = sorted(scored, key=lambda item: (-item[0], item[1]["label"], item[1]["url"]))
                best = ranked[0][0]
                records = [record for score, record in ranked if score == best]
        return records

    def rows_answer(self, question: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
        if not rows:
            return self.missing_answer(question)
        matched_count = len(rows)
        preview = rows[:5]
        rendered = "; ".join(
            f"{row['label']} ({row['topic']}, {row['resource_type']}): {row['url']}"
            for row in preview
        )
        return {
            "question": question,
            "answer": f"Showing {len(preview)} of {matched_count} matching DHSS public-health resource metadata row(s): {rendered}.",
            "retrieved_context_id": "dhss_health_sources_index:match",
            "retrieved_source": "dhss_health_sources_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local DHSS public-health resource metadata index.",
            "citations": self.citation(matched_rows=matched_count),
            "source_rows": [{"source_file": row["source_page"], "values": row} for row in preview],
        }

    def missing_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "I have indexed DHSS public-health resource metadata, but this question did not match a supported topic, "
                "resource label, MICA code, or year. Try `What DHSS health resources are indexed?`, "
                "`Give me the BRFSS link`, or `Give me the DHSS MICA link for inpatient hospitalizations`."
            ),
            "retrieved_context_id": "dhss_health_sources_index:no_match",
            "retrieved_source": "dhss_health_sources_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Answered from DHSS public-health coverage metadata because no exact resource row matched.",
            "citations": self.citation(),
            "source_rows": [],
        }

    def answer(self, question: str) -> dict[str, Any] | None:
        if not self.available():
            return self.unavailable_answer(question)
        terms = topic_terms(question)
        if asks_for_summary(question) and terms:
            return self.topic_summary_answer(question, terms)
        if asks_for_summary(question) and not terms:
            return self.summary_answer(question)
        rows = self.rows_for_question(question)
        if rows:
            return self.rows_answer(question, rows)
        if asks_for_summary(question):
            return self.summary_answer(question)
        return self.missing_answer(question)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--delay-seconds", type=float, default=0.03)
    args = parser.parse_args()
    payload = build_dhss_health_sources_index(force=args.force, delay_seconds=args.delay_seconds)
    print(json.dumps({key: value for key, value in payload.items() if key != "records"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
