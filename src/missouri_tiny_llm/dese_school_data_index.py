"""Build and query DESE school-data resource metadata."""

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
RAW_DIR = PROJECT_ROOT / "data" / "raw_public" / "dese_school_data"
INDEX_PATH = RAW_DIR / "dese_school_data_index.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "dese_school_data_index_report.json"
SOURCE_NAME = "DESE School Data resources"


@dataclass(frozen=True)
class DesePage:
    key: str
    label: str
    url: str
    default_topic: str


PAGES: tuple[DesePage, ...] = (
    DesePage("school_data", "DESE School Data", "https://dese.mo.gov/school-data", "school data"),
    DesePage(
        "accountability_data",
        "DESE Accountability Data",
        "https://dese.mo.gov/quality-schools/accountability-data",
        "accountability",
    ),
    DesePage(
        "msip",
        "Missouri School Improvement Program",
        "https://dese.mo.gov/quality-schools/mo-school-improvement-program",
        "accountability",
    ),
    DesePage(
        "core_data_mosis",
        "Core Data/MOSIS",
        "https://dese.mo.gov/data-system-management/core-datamosis",
        "core data/mosis",
    ),
    DesePage(
        "file_layouts",
        "Core Data/MOSIS File Layouts 2025-26",
        "https://dese.mo.gov/data-system-management/core-datamosis/file-layouts-2025-26",
        "file layouts",
    ),
    DesePage(
        "code_sets",
        "Core Data/MOSIS Code Sets 2025-26",
        "https://dese.mo.gov/data-system-management/core-datamosis/code-sets-2025-26",
        "code sets",
    ),
    DesePage(
        "school_finance",
        "DESE School Finance Topics and Procedures",
        "https://dese.mo.gov/financial-admin-services/school-finance/finance-topics-procedures",
        "school finance",
    ),
    DesePage(
        "special_education",
        "DESE Special Education Data",
        "https://dese.mo.gov/special-education/special-education-data",
        "special education",
    ),
)


LINK_PATTERN = re.compile(r"<a\s+[^>]*href=['\"]([^'\"]+)['\"][^>]*>(.*?)</a>", re.I | re.S)
YEAR_PATTERN = re.compile(r"\b(20\d{2})(?:[-/](\d{2}))?\b")

SKIP_LABEL_PATTERN = re.compile(
    r"^(skip to|map$|contact us$|privacy|data policy|home$|search$|login|reset password|deese? homepage|web accessibility)",
    re.I,
)
RESOURCE_KEEP_PATTERN = re.compile(
    r"accountability|assessment|apr|msip|ranking|growth model|core data|mosis|file layout|filespec|code set|school data|"
    r"data portal|dashboard|visualization|school finance|budget|salary|fund|accounting|audit|bond|attendance|special education|"
    r"data report|download|excel|xlsx|pdf|manual|guide|documentation|student|staff|personnel|directory|mcds",
    re.I,
)

GENERIC_QUERY_TOKENS = {
    "ABOUT",
    "DATA",
    "DESE",
    "DO",
    "DOES",
    "FOR",
    "FROM",
    "GIVE",
    "HAVE",
    "INDEX",
    "INDEXED",
    "LINK",
    "LINKS",
    "ME",
    "MISSOURI",
    "PUBLIC",
    "RESOURCE",
    "RESOURCES",
    "SCHOOL",
    "SCHOOLS",
    "SHOW",
    "SOURCE",
    "SOURCES",
    "THE",
    "WHAT",
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
    cleaned = re.sub(r"[^A-Z0-9/-]+", " ", clean_text(value).upper())
    return re.sub(r"\s+", " ", cleaned).strip()


def query_tokens(value: Any) -> set[str]:
    return {
        token
        for token in normalize_text(value).replace("/", " ").replace("-", " ").split()
        if len(token) > 2 and token not in GENERIC_QUERY_TOKENS
    }


def resource_type(url: str, label: str) -> str:
    lowered = f"{url} {label}".lower()
    parsed = urlparse(url)
    if lowered.startswith("mailto:"):
        return "email"
    if "visualizations.aspx" in lowered or "mcds" in parsed.netloc.lower():
        return "dese_app"
    if "filespec" in lowered or "info.mo.gov/dese/file_spec" in lowered:
        return "file_spec_html"
    if lowered.endswith(".xlsx") or "excel" in lowered or "filedownloadwebhandler" in lowered or "/media/" in lowered and "download" in lowered:
        return "download"
    if lowered.endswith(".xls"):
        return "download"
    if lowered.endswith(".pdf") or "/media/pdf/" in lowered:
        return "pdf"
    if parsed.netloc.endswith("dese.mo.gov"):
        return "dese_page"
    return "external_page"


def infer_topic(page: DesePage, label: str, url: str) -> str:
    lowered = f"{page.default_topic} {label} {url}".lower()
    if page.key == "code_sets" or "code set" in lowered or "codesets" in lowered or "_codes" in lowered:
        return "code sets"
    if page.key == "file_layouts" or "filespec" in lowered or "file layout" in lowered or "layout" in lowered:
        return "file layouts"
    if "finance" in lowered or "budget" in lowered or "salary" in lowered or "fund" in lowered or "accounting" in lowered:
        return "school finance"
    if "special education" in lowered or "sped" in lowered:
        return "special education"
    if "assessment" in lowered or "eoc" in lowered or "map-a" in lowered or "wida" in lowered:
        return "assessment"
    if "apr" in lowered or "msip" in lowered or "accountability" in lowered or "growth model" in lowered or "ranking" in lowered:
        return "accountability"
    if "directory" in lowered:
        return "directory"
    if "mcds" in lowered or "visualization" in lowered or "dashboard" in lowered or "data portal" in lowered:
        return "data portal/dashboard"
    if "core data" in lowered or "mosis" in lowered:
        return "core data/mosis"
    return page.default_topic


def year_label(label: str, url: str) -> str | None:
    matches = YEAR_PATTERN.findall(f"{label} {url}")
    if not matches:
        return None
    first = matches[-1]
    if first[1]:
        return f"{first[0]}-{first[1]}"
    return first[0]


def is_relevant_link(label: str, absolute_url: str) -> bool:
    if not label or SKIP_LABEL_PATTERN.search(label):
        return False
    if absolute_url.startswith("mailto:"):
        return False
    return bool(RESOURCE_KEEP_PATTERN.search(f"{label} {absolute_url}"))


def parse_page_links(page: DesePage, page_text: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for href, raw_label in LINK_PATTERN.findall(page_text):
        label = clean_text(raw_label)
        absolute = urljoin(page.url, html.unescape(href))
        key = (label, absolute)
        if key in seen or not is_relevant_link(label, absolute):
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
    ]


def build_dese_school_data_index(force: bool = False, delay_seconds: float = 0.03) -> dict[str, Any]:
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
    seen_urls: set[tuple[str, str]] = set()

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
            if dedupe_key in seen_urls:
                continue
            seen_urls.add(dedupe_key)
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
            "This index stores DESE public school-data resource metadata and source links only.",
            "It does not parse MCDS dashboard numeric values, accountability calculations, finance tables, or staff records.",
            "Exact numeric school values still require source-specific parsers for selected DESE exports or dashboards.",
        ],
        "records": records,
    }
    write_json(INDEX_PATH, payload)
    write_json(REPORT_PATH, {key: value for key, value in payload.items() if key != "records"})
    return payload


def topic_terms(question: str) -> set[str]:
    lowered = question.lower()
    terms: set[str] = set()
    if any(term in lowered for term in ["apr", "msip", "accountability", "growth model", "ranking"]):
        terms.add("accountability")
    if any(term in lowered for term in ["assessment", "eoc", "map-a", "wida"]):
        terms.add("assessment")
    if any(term in lowered for term in ["finance", "budget", "salary", "fund", "accounting", "audit", "bond"]):
        terms.add("school finance")
    if any(term in lowered for term in ["core data", "mosis"]):
        terms.add("core data/mosis")
    if "file layout" in lowered or "file layouts" in lowered or "filespec" in lowered:
        terms.add("file layouts")
    if "code set" in lowered or "code sets" in lowered:
        terms.add("code sets")
    if "special education" in lowered or "sped" in lowered:
        terms.add("special education")
    if any(term in lowered for term in ["dashboard", "data portal", "mcds", "visualization"]):
        terms.add("data portal/dashboard")
    return terms


def asks_for_summary(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["indexed", "available", "coverage", "what data", "what resources", "what links"])


class DeseSchoolDataIndex:
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
                "category": "Education",
                "kind": "DESE school-data resource metadata",
                "lookup_table": "dese_school_data_index",
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
                "The DESE School Data resource metadata index has not been built yet. Run "
                "`python scripts/build_dese_school_data_index.py --force` to index official DESE school-data resource links."
            ),
            "retrieved_context_id": "dese_school_data_index:missing",
            "retrieved_source": "dese_school_data_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "The DESE School Data route exists, but the local ignored index is missing.",
            "citations": [],
            "source_rows": [],
        }

    def summary_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        topics = "; ".join(f"{item['label']}: {item['count']}" for item in payload.get("top_topics", [])[:7])
        resource_types = "; ".join(f"{key}: {value}" for key, value in payload.get("resource_type_counts", {}).items())
        return {
            "question": question,
            "answer": (
                "The DESE School Data resource metadata layer indexes official public DESE school-data links from "
                f"{payload.get('page_count', 0)} source page(s). It contains {payload.get('record_count', 0):,} resource link(s). "
                f"Top topics: {topics}. Resource types: {resource_types}. "
                "It can return cited links for accountability/APR, MSIP, Core Data/MOSIS file layouts and code sets, school finance guidance, assessment resources, and special-education data resources. "
                "It does not parse MCDS dashboard numeric values yet."
            ),
            "retrieved_context_id": "dese_school_data_index:summary",
            "retrieved_source": "dese_school_data_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local DESE School Data resource metadata index.",
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
                f"The DESE School Data resource metadata layer has {len(rows):,} indexed link(s) for this topic request. "
                f"Topic counts: {topic_text}. Resource types: {type_text}. Examples: {examples}. "
                "These are source links and resource metadata, not parsed MCDS numeric values."
            ),
            "retrieved_context_id": "dese_school_data_index:topic_summary",
            "retrieved_source": "dese_school_data_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local DESE School Data resource metadata index.",
            "citations": self.citation(matched_rows=len(rows)),
            "source_rows": [],
        }

    def rows_for_question(self, question: str) -> list[dict[str, Any]]:
        records = self.records()
        wanted_topics = topic_terms(question)
        if wanted_topics:
            records = [record for record in records if record.get("topic") in wanted_topics]
        wanted_years = {year for year in re.findall(r"\b20\d{2}(?:-\d{2})?\b", question)}
        if wanted_years:
            year_filtered = [record for record in records if record.get("year_label") in wanted_years or any(year in str(record.get("label", "")) for year in wanted_years)]
            if year_filtered:
                records = year_filtered
        q_tokens = query_tokens(question)
        if q_tokens:
            scored: list[tuple[int, dict[str, Any]]] = []
            for record in records:
                blob = " ".join(str(record.get(key, "")) for key in ["label", "topic", "page_label", "resource_type", "year_label"])
                tokens = query_tokens(blob)
                score = len(q_tokens & tokens)
                if normalize_text(record.get("label", "")) in normalize_text(question):
                    score += 25
                if score:
                    scored.append((score, record))
            if scored:
                ranked = sorted(scored, key=lambda item: (-item[0], item[1]["label"]))
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
            "answer": f"Showing {len(preview)} of {matched_count} matching DESE School Data resource metadata row(s): {rendered}.",
            "retrieved_context_id": "dese_school_data_index:match",
            "retrieved_source": "dese_school_data_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local DESE School Data resource metadata index.",
            "citations": self.citation(matched_rows=matched_count),
            "source_rows": [{"source_file": row["source_page"], "values": row} for row in preview],
        }

    def missing_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "I have indexed DESE School Data resource metadata, but this question did not match a supported topic, "
                "resource label, or year. Try `What DESE school data resources are indexed?`, "
                "`Give me the link for 2025 APR Ranking - LEAs`, or `What Core Data/MOSIS file layout resources are indexed?`"
            ),
            "retrieved_context_id": "dese_school_data_index:no_match",
            "retrieved_source": "dese_school_data_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Answered from DESE School Data coverage metadata because no exact resource row matched.",
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
    payload = build_dese_school_data_index(force=args.force, delay_seconds=args.delay_seconds)
    print(json.dumps({key: value for key, value in payload.items() if key != "records"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
