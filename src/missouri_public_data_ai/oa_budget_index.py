"""Build and query Office of Administration Budget and Planning metadata."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw_public" / "oa_budget"
INDEX_PATH = RAW_DIR / "oa_budget_index.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "oa_budget_index_report.json"
LANDING_PAGE = "https://oa.mo.gov/budget-and-planning"
BUDPLAN_HOME = "https://budplan.oa.mo.gov/"

SOURCE_PAGES = [
    {
        "key": "budget_information",
        "label": "Budget Information",
        "url": "https://budplan.oa.mo.gov/budget-information",
    },
    {
        "key": "revenue_information",
        "label": "Revenue Information",
        "url": "https://budplan.oa.mo.gov/revenue-information",
    },
    {
        "key": "performance_measures",
        "label": "Performance Measure Resources",
        "url": "https://budplan.oa.mo.gov/measures-matter",
    },
    {
        "key": "demographic_information",
        "label": "Demographic Information",
        "url": "https://budplan.oa.mo.gov/demographic-information",
    },
    {
        "key": "redistricting",
        "label": "Redistricting Office",
        "url": "https://budplan.oa.mo.gov/redistricting-office",
    },
]

ANCHOR_PATTERN = re.compile(r"<a\s+href=['\"]?([^'\" >]+)['\"]?[^>]*>(.*?)</a>", re.I | re.S)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def clean_text(value: Any) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", str(value or ""), flags=re.S)
    decoded = html.unescape(without_tags)
    decoded = decoded.replace("\u200b", "").replace("\ufeff", "")
    return re.sub(r"\s+", " ", decoded).strip()


def normalize_url(base_url: str, href: str) -> str:
    url = urljoin(base_url, href)
    # Some Drupal links are emitted as /budplan.oa.mo.gov/...; normalize them.
    url = url.replace("https://budplan.oa.mo.gov/budplan.oa.mo.gov/", "https://budplan.oa.mo.gov/")
    return url


def normalize_text(value: Any) -> str:
    cleaned = re.sub(r"[^A-Z0-9]+", " ", clean_text(value).upper())
    return re.sub(r"\s+", " ", cleaned).strip()


def file_type(url: str) -> str:
    parsed_path = urlparse(url).path.lower()
    suffix = Path(parsed_path).suffix.lower().lstrip(".")
    if suffix:
        return suffix
    if "/media/pdf/" in parsed_path:
        return "pdf"
    if "/media/file/" in parsed_path or "/download" in parsed_path:
        return "file"
    return "page"


def fiscal_year(label: str, url: str) -> int | None:
    text = f"{label} {url}"
    match = re.search(r"\bFY\s*20(\d{2})\b", text, flags=re.I)
    if match:
        return int(f"20{match.group(1)}")
    match = re.search(r"\bfy20(\d{2})\b", text, flags=re.I)
    if match:
        return int(f"20{match.group(1)}")
    match = re.search(r"\bFY\s*(\d{2})\b", text, flags=re.I)
    if match:
        year = int(match.group(1))
        return 2000 + year if year < 80 else 1900 + year
    match = re.search(r"\bfy(\d{2})\b", text, flags=re.I)
    if match:
        year = int(match.group(1))
        return 2000 + year if year < 80 else 1900 + year
    match = re.search(r"\bbudget-information/fy(\d{4})\b", url, flags=re.I)
    if match:
        return int(match.group(1))
    match = re.search(r"\bFY[_\s-](\d{2})\b", text, flags=re.I)
    if match:
        year = int(match.group(1))
        return 2000 + year if year < 80 else 1900 + year
    return None


def calendar_year(label: str, url: str) -> int | None:
    match = re.search(r"\b(20\d{2}|19\d{2})\b", f"{label} {url}")
    return int(match.group(1)) if match else None


def document_type(label: str, url: str, section: str) -> str:
    lowered = f"{label} {url}".lower()
    if section == "revenue_information":
        if file_type(url) in {"xls", "xlsx", "csv"} or "detail" in lowered or "/download" in lowered:
            return "revenue_detail"
        return "revenue_press_release"
    if "executive budget" in lowered:
        return "executive_budget"
    if "budget summary" in lowered:
        return "budget_summary"
    if "legislative priorit" in lowered:
        return "budget_and_legislative_priorities"
    if "department budget request" in lowered or "dept-request" in lowered or "dept-requests" in lowered:
        return "department_budget_requests"
    if "appropriation" in lowered:
        return "appropriation_bills"
    if "fringe" in lowered:
        return "fringe_estimates"
    if "performance" in lowered or "measure" in lowered or section == "performance_measures":
        return "performance_measure_resource"
    if "census" in lowered or "population" in lowered or "demographic" in lowered or section == "demographic_information":
        return "demographic_resource"
    if "redistrict" in lowered or "map" in lowered or "apportionment" in lowered or section == "redistricting":
        return "redistricting_resource"
    return "budget_planning_resource"


def should_keep_link(label: str, url: str, section: str) -> bool:
    if not label:
        return False
    nav_label = normalize_text(label)
    if nav_label in {
        "BUDGET PLANNING",
        "DIVISION OF BUDGET PLANNING",
        "BUDGET INFORMATION",
        "BUDGET RELATED INFORMATION BY FISCAL YEAR",
        "PERFORMANCE MEASURE RESOURCES",
        "REVENUE INFORMATION",
        "DEMOGRAPHIC INFORMATION",
        "REDISTRICTING OFFICE",
        "MISSOURI ACCOUNTABILITY PORTAL",
    }:
        return False
    lowered = f"{label} {url}".lower()
    if any(skip in lowered for skip in ["skip to main", "facebook", "twitter", "instagram", "linkedin", "youtube", "email us"]):
        return False
    if section == "budget_information":
        return any(
            term in lowered
            for term in [
                "executive budget",
                "budget and legislative",
                "budget summary",
                "department budget request",
                "dept-request",
                "appropriation",
                "fringe",
                "budget-information/fy",
            ]
        )
    if section == "revenue_information":
        return "revenue" in lowered or re.search(r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+20\d{2}\b", lowered)
    if section == "performance_measures":
        return any(term in lowered for term in ["performance", "measure", "budget", "program description", "common functions", "training"])
    if section == "demographic_information":
        return any(term in lowered for term in ["census", "population", "demographic"])
    if section == "redistricting":
        return any(term in lowered for term in ["redistrict", "district", "map", "plan", "apportionment", "congressional", "house", "senate"])
    return False


def month_label(label: str) -> str | None:
    match = re.search(
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})\b",
        label,
        flags=re.I,
    )
    if not match:
        return None
    return f"{match.group(1).title()} {match.group(2)}"


def parse_page(page: dict[str, str], page_text: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for href, label_html in ANCHOR_PATTERN.findall(page_text):
        label = clean_text(label_html)
        url = normalize_url(page["url"], href)
        if not should_keep_link(label, url, page["key"]):
            continue
        key = (page["key"], url, label)
        if key in seen:
            continue
        seen.add(key)
        records.append(
            {
                "section": page["key"],
                "section_label": page["label"],
                "label": label,
                "label_norm": normalize_text(label),
                "url": url,
                "file_type": file_type(url),
                "document_type": document_type(label, url, page["key"]),
                "fiscal_year": fiscal_year(label, url),
                "calendar_year": calendar_year(label, url),
                "month_label": month_label(label),
                "source_page": page["url"],
            }
        )
    return records


def build_oa_budget_index(force: bool = False) -> dict[str, Any]:
    if INDEX_PATH.exists() and not force:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (compatible; MissouriPublicDataAssistant/1.0)",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        }
    )
    start = time.perf_counter()
    all_records: list[dict[str, Any]] = []
    page_stats: list[dict[str, Any]] = []
    combined_text: list[str] = []
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for page in SOURCE_PAGES:
        response = session.get(page["url"], timeout=60)
        response.raise_for_status()
        text = response.text
        combined_text.append(text)
        (RAW_DIR / f"{page['key']}.html").write_text(text, encoding="utf-8")
        records = parse_page(page, text)
        all_records.extend(records)
        page_stats.append(
            {
                "key": page["key"],
                "label": page["label"],
                "url": page["url"],
                "bytes": len(text.encode("utf-8", errors="replace")),
                "record_count": len(records),
            }
        )
    records = sorted(all_records, key=lambda item: (item.get("fiscal_year") or 0, item["section"], item["label"]), reverse=True)
    section_counts = Counter(record["section"] for record in records)
    document_type_counts = Counter(record["document_type"] for record in records)
    fiscal_years = sorted({record["fiscal_year"] for record in records if record.get("fiscal_year")})
    text_blob = "\n".join(combined_text)
    payload = {
        "generated_at_utc": utc_now(),
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "source": "Office of Administration Budget and Planning",
        "landing_page": LANDING_PAGE,
        "budplan_home": BUDPLAN_HOME,
        "index_path": str(INDEX_PATH.relative_to(PROJECT_ROOT)),
        "page_count": len(SOURCE_PAGES),
        "record_count": len(records),
        "bytes": len(text_blob.encode("utf-8", errors="replace")),
        "sha256": sha256_text(text_blob),
        "min_fiscal_year": min(fiscal_years) if fiscal_years else None,
        "max_fiscal_year": max(fiscal_years) if fiscal_years else None,
        "page_stats": page_stats,
        "section_counts": dict(section_counts),
        "document_type_counts": dict(document_type_counts),
        "notes": [
            "This index stores official Budget and Planning page/link metadata only.",
            "It does not download or interpret PDF, Excel, redistricting, or budget-book contents.",
            "Budget questions should distinguish proposed, recommended, enacted, and historical materials.",
        ],
        "records": records,
    }
    write_json(INDEX_PATH, payload)
    write_json(REPORT_PATH, {key: value for key, value in payload.items() if key != "records"})
    return payload


def requested_years(question: str) -> list[int]:
    return [int(year) for year in re.findall(r"\b(19\d{2}|20\d{2})\b", question)]


def requested_fiscal_year(question: str) -> int | None:
    match = re.search(r"\bFY\s*20(\d{2})\b", question, flags=re.I)
    if match:
        return int(f"20{match.group(1)}")
    match = re.search(r"\bfiscal\s+year\s+(20\d{2})\b", question, flags=re.I)
    if match:
        return int(match.group(1))
    years = requested_years(question)
    return years[-1] if years else None


def requested_doc_type(question: str) -> str | None:
    lowered = question.lower()
    if "executive budget" in lowered:
        return "executive_budget"
    if "budget summary" in lowered:
        return "budget_summary"
    if "legislative priorit" in lowered:
        return "budget_and_legislative_priorities"
    if "department budget request" in lowered or "dept request" in lowered:
        return "department_budget_requests"
    if "appropriation" in lowered:
        return "appropriation_bills"
    if "fringe" in lowered:
        return "fringe_estimates"
    if "revenue detail" in lowered:
        return "revenue_detail"
    if "revenue" in lowered:
        return "revenue_press_release"
    if "performance" in lowered or "measure" in lowered:
        return "performance_measure_resource"
    if "demographic" in lowered or "census" in lowered or "population" in lowered:
        return "demographic_resource"
    if "redistrict" in lowered or "house map" in lowered or "senate map" in lowered:
        return "redistricting_resource"
    return None


class OaBudgetIndex:
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
                "dataset": payload.get("source", "Office of Administration Budget and Planning"),
                "category": "Budget and Planning",
                "kind": "OA budget/planning metadata",
                "lookup_table": "oa_budget_index",
                "year": None,
                "year_range": (
                    f"{payload.get('min_fiscal_year')}-{payload.get('max_fiscal_year')}"
                    if payload.get("min_fiscal_year") and payload.get("max_fiscal_year")
                    else None
                ),
                "source_files": [
                    {
                        "category": "oa_budget",
                        "category_label": "Budget and Planning pages",
                        "file_name": payload.get("budplan_home", BUDPLAN_HOME),
                        "row_count": payload.get("record_count"),
                        "bytes": payload.get("bytes"),
                        "sha256": payload.get("sha256"),
                    }
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
                "The OA Budget and Planning metadata index has not been built yet. Run "
                "`python scripts/build_oa_budget_index.py --force` to index the official Budget and Planning pages."
            ),
            "retrieved_context_id": "oa_budget_index:missing",
            "retrieved_source": "oa_budget_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "The OA Budget route exists, but the local ignored index is missing.",
            "citations": [],
            "source_rows": [],
        }

    def summary_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        sections = payload.get("section_counts", {})
        section_text = "; ".join(f"{key}: {value}" for key, value in sorted(sections.items()))
        return {
            "question": question,
            "answer": (
                "The OA Budget and Planning exact lookup layer indexes official page/link metadata from Budget Information, "
                "Revenue Information, Performance Measure Resources, Demographic Information, and Redistricting Office pages. "
                f"It contains {payload.get('record_count', 0):,} indexed link record(s) across {payload.get('page_count', 0)} page(s), "
                f"with fiscal years {payload.get('min_fiscal_year')}-{payload.get('max_fiscal_year')} where labeled. "
                f"Section counts: {section_text}."
            ),
            "retrieved_context_id": "oa_budget_index:summary",
            "retrieved_source": "oa_budget_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local OA Budget and Planning metadata index.",
            "citations": self.citation(matched_rows=payload.get("record_count", 0)),
            "source_rows": [],
        }

    def latest_for_type(self, doc_type: str) -> dict[str, Any] | None:
        rows = [row for row in self.records() if row.get("document_type") == doc_type and row.get("fiscal_year")]
        if not rows:
            return None
        return sorted(rows, key=lambda item: (item.get("fiscal_year") or 0, item.get("label", "")), reverse=True)[0]

    def rows_for_question(self, question: str) -> list[dict[str, Any]]:
        doc_type = requested_doc_type(question)
        fiscal = requested_fiscal_year(question)
        lowered = question.lower()
        rows = self.records()
        if doc_type:
            rows = [row for row in rows if row.get("document_type") == doc_type]
        if fiscal:
            rows = [row for row in rows if row.get("fiscal_year") == fiscal or row.get("calendar_year") == fiscal]
        month_match = re.search(
            r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\b",
            lowered,
        )
        if month_match:
            month = month_match.group(1).title()
            rows = [row for row in rows if row.get("month_label", "").startswith(month)]
        if not doc_type and any(term in lowered for term in ["latest", "newest", "most recent"]):
            rows = [row for row in rows if row.get("fiscal_year") == self.payload().get("max_fiscal_year")]
        return rows

    def rows_answer(self, question: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
        if not rows:
            return self.missing_answer(question)
        matched_count = len(rows)
        rows = rows[:5]
        rendered = "; ".join(
            f"{row['label']} ({row['section_label']}, {row.get('fiscal_year') or row.get('calendar_year') or 'no year'}): {row['url']}"
            for row in rows
        )
        prefix = f"Showing {len(rows)} of {matched_count} matching OA Budget and Planning metadata row(s)"
        return {
            "question": question,
            "answer": f"{prefix}: {rendered}.",
            "retrieved_context_id": "oa_budget_index:match",
            "retrieved_source": "oa_budget_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local OA Budget and Planning metadata index.",
            "citations": self.citation(matched_rows=matched_count),
            "source_rows": [{"source_file": row["source_page"], "values": row} for row in rows],
        }

    def latest_answer(self, question: str, doc_type: str) -> dict[str, Any]:
        row = self.latest_for_type(doc_type)
        if row is None:
            return self.missing_answer(question)
        return {
            "question": question,
            "answer": (
                f"The latest indexed OA Budget and Planning `{doc_type}` row is {row['label']} "
                f"for FY {row.get('fiscal_year')}. Official link: {row['url']}."
            ),
            "retrieved_context_id": f"oa_budget_index:latest:{doc_type}",
            "retrieved_source": "oa_budget_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local OA Budget and Planning metadata index.",
            "citations": self.citation(matched_rows=1),
            "source_rows": [{"source_file": row["source_page"], "values": row}],
        }

    def missing_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "I have indexed OA Budget and Planning metadata, but this question did not match a supported fiscal year, "
                "document type, revenue month, performance-measure resource, demographic resource, or redistricting resource."
            ),
            "retrieved_context_id": "oa_budget_index:no_match",
            "retrieved_source": "oa_budget_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Answered from OA Budget coverage metadata because no exact metadata row matched.",
            "citations": self.citation(),
            "source_rows": [],
        }

    def answer(self, question: str) -> dict[str, Any] | None:
        if not self.available():
            return self.unavailable_answer(question)
        lowered = question.lower()
        if any(term in lowered for term in ["indexed", "connected", "available", "coverage", "data"]) and not requested_doc_type(question):
            return self.summary_answer(question)
        doc_type = requested_doc_type(question)
        if doc_type and any(term in lowered for term in ["latest", "newest", "most recent"]):
            return self.latest_answer(question, doc_type)
        rows = self.rows_for_question(question)
        if rows:
            return self.rows_answer(question, rows)
        return self.missing_answer(question)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    payload = build_oa_budget_index(force=args.force)
    print(json.dumps({key: value for key, value in payload.items() if key != "records"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
