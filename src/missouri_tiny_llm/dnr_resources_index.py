"""Build and query Missouri DNR data/e-services resource metadata."""

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
from urllib.parse import urljoin, urlparse

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw_public" / "dnr_resources"
INDEX_PATH = RAW_DIR / "dnr_resources_index.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "dnr_resources_index_report.json"
SOURCE_NAME = "Missouri DNR data and e-services metadata"


@dataclass(frozen=True)
class DnrPage:
    key: str
    label: str
    url: str
    default_topic: str


PAGES: tuple[DnrPage, ...] = (
    DnrPage("overview", "DNR Data and e-Services", "https://dnr.mo.gov/data-e-services", "data/e-services overview"),
    DnrPage("water", "DNR Water Data and e-Services", "https://dnr.mo.gov/water/data-e-services", "water data/e-services"),
    DnrPage("air", "DNR Air Data and e-Services", "https://dnr.mo.gov/air/data-e-services", "air quality/emissions"),
    DnrPage(
        "waste_recycling",
        "DNR Waste and Recycling Data and e-Services",
        "https://dnr.mo.gov/waste-recycling/data-e-services",
        "waste/recycling/remediation",
    ),
    DnrPage(
        "land_geology",
        "DNR Land and Geology Maps, Data and Research",
        "https://dnr.mo.gov/land-geology/maps-data-research",
        "land/geology/GIS",
    ),
    DnrPage("energy", "DNR Energy Data", "https://dnr.mo.gov/energy/information/data", "energy data"),
    DnrPage(
        "permits",
        "DNR Permits, Certifications, Registrations and Licenses",
        "https://dnr.mo.gov/permits-certifications-registrations-licenses",
        "permits/forms/public notices",
    ),
    DnrPage("forms", "DNR Forms and Applications", "https://dnr.mo.gov/forms-applications", "permits/forms/public notices"),
    DnrPage("public_notices", "DNR Public Notices and Comments", "https://dnr.mo.gov/public-notices-comments", "permits/forms/public notices"),
)

ANCHOR_PATTERN = re.compile(r"<a\s+[^>]*href=['\"]([^'\"]+)['\"][^>]*>(.*?)</a>", re.I | re.S)
YEAR_PATTERN = re.compile(r"\b(20\d{2}|19\d{2})\b")

KEEP_PATTERN = re.compile(
    r"data|e-services?|permit|certification|registration|license|report|search|map|viewer|gis|arcgis|"
    r"mocwis|mogem|lims|wims|geostrat|geoedge|lris|wisd|e-start|agilaire|moeis|edmr|"
    r"drinking|wastewater|stormwater|boil|impaired|water quality|groundwater|surface water|water use|"
    r"emissions|monitoring|air quality|current air|hazardous|solid waste|recycling|environmental|"
    r"public notice|forms?|applications?|well|operator|energy|database|portal|system|beach|lake|drought|"
    r"mine map|geologic|geology|bibliography|seismic|sinkhole|discharge|operator certification",
    re.I,
)
SKIP_PATTERN = re.compile(
    r"^(skip|home$|contact|accessibility|privacy|careers?|calendar|facebook|x - formerly twitter|twitter|"
    r"instagram|youtube|flickr|search$|governor|mo\.gov|find an agency|online services|about us|"
    r"communications|photo contest|video broadcasts|get email updates|sites of interest|click here to save a life|"
    r"ada and non-discrimination|data policy|privacy policy|archived content|google terms of service)$",
    re.I,
)

GENERIC_QUERY_TOKENS = {
    "ABOUT",
    "AND",
    "ARE",
    "CAN",
    "CONNECTED",
    "DATA",
    "DNR",
    "DO",
    "ENVIRONMENT",
    "ENVIRONMENTAL",
    "EXACT",
    "FOR",
    "GIVE",
    "INDEX",
    "INDEXED",
    "LINK",
    "LINKS",
    "MISSOURI",
    "PUBLIC",
    "RESOURCE",
    "RESOURCES",
    "SEARCH",
    "SHOW",
    "SOURCE",
    "SOURCES",
    "THE",
    "WHAT",
    "WHERE",
    "WHICH",
}


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
    cleaned = re.sub(r"[^A-Z0-9/$.-]+", " ", clean_text(value).upper())
    return re.sub(r"\s+", " ", cleaned).strip()


def query_tokens(value: Any) -> set[str]:
    return {
        token.strip("$.,")
        for token in normalize_text(value).replace("/", " ").replace("-", " ").split()
        if len(token.strip("$.,()")) > 2 and token.strip("$.,()") not in GENERIC_QUERY_TOKENS
    }


def year_label(label: str, url: str) -> str | None:
    matches = YEAR_PATTERN.findall(f"{label} {url}")
    return matches[-1] if matches else None


def resource_type(url: str, label: str) -> str:
    lowered = f"{url} {label}".lower()
    path = urlparse(url).path.lower()
    host = urlparse(url).netloc.lower()
    if path.endswith(".pdf"):
        if any(term in lowered for term in ["form", "application", "permit"]):
            return "form_pdf"
        return "pdf"
    if any(term in lowered for term in ["arcgis", "map", "viewer", "gis", "geostrat", "geoedge", "lris", "wisd", "spatial"]):
        return "map_or_gis"
    if host.startswith("apps") or any(
        term in lowered
        for term in [
            "search",
            "system",
            "application",
            "portal",
            "tool",
            "mocwis",
            "mogem",
            "lims",
            "wims",
            "moeis",
            "edmr",
            "agilaire",
            "e-start",
            "database",
        ]
    ):
        return "search_or_data_system"
    if any(term in lowered for term in ["permit", "certification", "registration", "license", "epermitting"]):
        return "permit_or_form_page"
    if any(term in lowered for term in ["public notice", "public comment"]):
        return "public_notice_page"
    if any(term in lowered for term in ["report", "data", "e-services", "statistics", "profile"]):
        return "data_or_report_page"
    if "dnr.mo.gov" in host:
        return "dnr_page"
    return "external_page"


def infer_topic(page: DnrPage, label: str, url: str) -> str:
    lowered = f"{page.default_topic} {label} {url}".lower()
    if any(term in lowered for term in ["air", "emission", "agilaire", "moeis", "current air", "vehicle inspection"]):
        return "air quality/emissions"
    if any(term in lowered for term in ["waste", "recycling", "hazardous", "solid waste", "e-start", "remediation", "cleanup", "regulated facilit"]):
        return "waste/recycling/remediation"
    if any(term in lowered for term in ["energy", "electricity", "weatherization", "petroleum", "natural gas", "coal", "renewable", "eia"]):
        return "energy data"
    if any(term in lowered for term in ["geology", "geologic", "geostrat", "geoedge", "lris", "wisd", "mine map", "well", "drilling", "seismic", "sinkhole", "karst", "bibliography"]):
        return "land/geology/GIS"
    if any(term in lowered for term in ["arcgis", "gis", "map viewer", "map service", "webappviewer", "opendata.arcgis"]):
        return "maps/GIS services"
    if any(term in lowered for term in ["public notice", "public comment", "forms", "application", "permit", "certification", "registration", "license", "epermitting"]):
        if any(term in lowered for term in ["water permit", "wastewater", "stormwater", "mocwis", "edmr", "discharge"]):
            return "water permits/wastewater/stormwater"
        return "permits/forms/public notices"
    if any(term in lowered for term in ["drinking water", "boil water", "public water", "water system", "operator certification"]):
        return "public drinking water"
    if any(term in lowered for term in ["impaired", "water quality", "quality standards", "quality data", "waterbody", "waterway", "stream", "river", "lake", "wetland", "lims"]):
        return "impaired waters/water quality"
    if any(term in lowered for term in ["groundwater", "surface water", "drought", "flood", "water use", "usgs current water", "beach status"]):
        return "water monitoring/hydrology"
    if any(term in lowered for term in ["mocwis", "mogem", "lims", "wims", "system", "search", "portal", "database", "e-services"]):
        return "data systems/tools"
    if "water" in lowered:
        return "water data/e-services"
    return page.default_topic


def is_relevant_link(label: str, absolute_url: str) -> bool:
    if not label or SKIP_PATTERN.search(label):
        return False
    if absolute_url.startswith(("mailto:", "tel:", "javascript:")):
        return False
    parsed = urlparse(absolute_url)
    if parsed.scheme not in {"http", "https"}:
        return False
    return bool(KEEP_PATTERN.search(f"{label} {absolute_url}"))


def parse_page_links(page: DnrPage, page_text: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for href, raw_label in ANCHOR_PATTERN.findall(page_text):
        absolute = urljoin(page.url, html.unescape(href)).split("#", 1)[0]
        label = clean_text(raw_label)
        if not is_relevant_link(label, absolute):
            continue
        key = (label, absolute)
        if key in seen:
            continue
        seen.add(key)
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
            }
        )
    return records


def top_counts(counter: Counter[str], limit: int = 12) -> list[dict[str, Any]]:
    return [
        {"label": label, "count": count}
        for label, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:limit]
        if label
    ]


def build_dnr_resources_index(force: bool = False, delay_seconds: float = 0.03) -> dict[str, Any]:
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
            "This index stores Missouri DNR public data/e-services resource metadata and source links only.",
            "It does not download GIS layers, permit-result tables, detailed Consumer Confidence Report documents, or PDF corpora.",
            "Numeric water-quality, permit, impaired-water, emission, waste-site, or geospatial values still require dedicated parsers before exact answers should be given.",
        ],
        "records": records,
    }
    write_json(INDEX_PATH, payload)
    write_json(REPORT_PATH, {key: value for key, value in payload.items() if key != "records"})
    return payload


def topic_terms(question: str) -> set[str]:
    lowered = question.lower()
    terms: set[str] = set()
    if any(term in lowered for term in ["air", "emission", "moeis", "agilaire", "current air"]):
        terms.add("air quality/emissions")
    if any(term in lowered for term in ["waste", "recycling", "hazardous", "solid waste", "e-start", "cleanup", "remediation"]):
        terms.add("waste/recycling/remediation")
    if any(term in lowered for term in ["energy", "electricity", "weatherization", "eia"]):
        terms.add("energy data")
    if any(term in lowered for term in ["geology", "geologic", "geostrat", "geoedge", "well", "wims", "wisd", "mine map", "sinkhole", "seismic"]):
        terms.add("land/geology/GIS")
    if any(term in lowered for term in ["gis", "map", "arcgis", "viewer"]):
        terms.add("maps/GIS services")
    if any(term in lowered for term in ["permit", "certification", "registration", "license", "form", "application", "public notice", "public comment"]):
        terms.add("permits/forms/public notices")
    if any(term in lowered for term in ["water permit", "wastewater", "stormwater", "mocwis", "edmr", "discharge"]):
        terms.add("water permits/wastewater/stormwater")
    if any(term in lowered for term in ["drinking water", "boil water", "public water", "water system", "operator certification"]):
        terms.add("public drinking water")
    if any(term in lowered for term in ["impaired", "water quality", "waterbody", "waterway", "quality standards", "lims"]):
        terms.add("impaired waters/water quality")
    if any(term in lowered for term in ["groundwater", "surface water", "drought", "flood", "water use", "beach"]):
        terms.add("water monitoring/hydrology")
    if any(term in lowered for term in ["mogem", "mocwis", "lims", "wims", "system", "portal", "database", "tool", "e-service"]):
        terms.add("data systems/tools")
    if "water" in lowered and not terms:
        terms.add("water data/e-services")
    return terms


def resource_type_terms(question: str) -> set[str]:
    lowered = question.lower()
    terms: set[str] = set()
    if any(term in lowered for term in ["gis", "map", "viewer", "arcgis"]):
        terms.add("map_or_gis")
    if any(term in lowered for term in ["search", "lookup", "system", "portal", "tool", "database", "mocwis", "mogem", "lims", "wims"]):
        terms.add("search_or_data_system")
    if any(term in lowered for term in ["permit", "certification", "registration", "license", "form", "application", "epermitting"]):
        terms.add("permit_or_form_page")
    if any(term in lowered for term in ["public notice", "public comment"]):
        terms.add("public_notice_page")
    if any(term in lowered for term in ["report", "data", "e-services"]):
        terms.add("data_or_report_page")
    return terms


def asks_for_summary(question: str) -> bool:
    lowered = question.lower()
    return any(
        term in lowered
        for term in ["indexed", "available", "coverage", "connected", "what data", "what resources", "what links", "what dnr", "what reports"]
    )


class DnrResourcesIndex:
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
                "category": "Environment",
                "kind": "DNR public-resource metadata",
                "lookup_table": "dnr_resources_index",
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
                "The DNR data/e-services resource metadata index has not been built yet. Run "
                "`python scripts/build_dnr_resources_index.py --force` to index official DNR environmental resource links."
            ),
            "retrieved_context_id": "dnr_resources_index:missing",
            "retrieved_source": "dnr_resources_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "The DNR route exists, but the local ignored index is missing.",
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
                "The DNR data/e-services resource metadata layer indexes official Missouri DNR public links from "
                f"{payload.get('page_count', 0)} source page(s). It contains {payload.get('record_count', 0):,} resource link(s). "
                f"Top topics: {topics}. Resource types: {resource_types}. "
                "It can return cited links for water permits, MoCWIS, drinking-water tools, impaired waters and water-quality resources, GIS/map viewers, air-emissions tools, E-Start, WIMS, GeoSTRAT, energy data, forms, and public notices. "
                "It is link metadata, not a numeric parser for environmental measurements or permit-result rows."
            ),
            "retrieved_context_id": "dnr_resources_index:summary",
            "retrieved_source": "dnr_resources_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local DNR data/e-services resource metadata index.",
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
            for row in sorted(rows, key=lambda item: (str(item.get("topic")), str(item.get("label"))))[:6]
        )
        return {
            "question": question,
            "answer": (
                f"The DNR data/e-services resource metadata layer has {len(rows):,} indexed link(s) for this topic request. "
                f"Topic counts: {topic_text}. Resource types: {type_text}. Examples: {examples}. "
                "These are source links and resource metadata, not parsed environmental numeric values."
            ),
            "retrieved_context_id": "dnr_resources_index:topic_summary",
            "retrieved_source": "dnr_resources_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local DNR data/e-services resource metadata index.",
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
        wanted_types = resource_type_terms(question)
        if wanted_types:
            type_filtered = [record for record in records if record.get("resource_type") in wanted_types]
            if type_filtered:
                records = type_filtered
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
            question_norm = normalize_text(question)
            for record in records:
                blob = " ".join(str(record.get(key, "")) for key in ["label", "topic", "page_label", "resource_type", "year_label"])
                tokens = query_tokens(blob)
                score = len(q_tokens & tokens)
                label_norm = normalize_text(record.get("label", ""))
                url_lowered = str(record.get("url", "")).lower()
                if label_norm and label_norm in question_norm:
                    score += 25
                if "MOCWIS" in question_norm and "mocwis" in url_lowered:
                    score += 12
                if "MOGEM" in question_norm and "mogem" in url_lowered:
                    score += 12
                if "WIMS" in question_norm and "wims" in url_lowered:
                    score += 12
                if "IMPAIRED" in question_norm and "impaired" in url_lowered:
                    score += 10
                if "DRINKING" in question_norm and "drinking" in url_lowered:
                    score += 8
                if "PERMIT" in question_norm and record.get("resource_type") == "permit_or_form_page":
                    score += 6
                if "MAP" in question_norm and record.get("resource_type") == "map_or_gis":
                    score += 6
                if score:
                    scored.append((score, record))
            if scored:
                ranked = sorted(scored, key=lambda item: (-item[0], item[1]["label"], item[1]["url"]))
                best = ranked[0][0]
                records = [record for score, record in ranked if score >= max(1, best - 2)]
        return records

    def rows_answer(self, question: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
        if not rows:
            return self.missing_answer(question)
        matched_count = len(rows)
        preview = rows[:12]
        source_preview = rows[:5]
        rendered = "; ".join(
            f"{row['label']} ({row['topic']}, {row['resource_type']}): {row['url']}"
            for row in preview
        )
        return {
            "question": question,
            "answer": f"Showing {len(preview)} of {matched_count} matching DNR data/e-services resource metadata row(s): {rendered}.",
            "retrieved_context_id": "dnr_resources_index:match",
            "retrieved_source": "dnr_resources_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local DNR data/e-services resource metadata index.",
            "citations": self.citation(matched_rows=matched_count),
            "source_rows": [{"source_file": row["source_page"], "values": row} for row in source_preview],
        }

    def missing_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "I have indexed DNR data/e-services resource metadata, but this question did not match a supported topic, resource label, or year. "
                "Try `What DNR resources are indexed?`, `Give me DNR water permit links`, "
                "`Where is Missouri impaired waters data?`, or `What DNR GIS resources are indexed?`."
            ),
            "retrieved_context_id": "dnr_resources_index:no_match",
            "retrieved_source": "dnr_resources_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Answered from DNR resource coverage metadata because no exact resource row matched.",
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
    payload = build_dnr_resources_index(force=args.force, delay_seconds=args.delay_seconds)
    print(json.dumps({key: value for key, value in payload.items() if key != "records"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
