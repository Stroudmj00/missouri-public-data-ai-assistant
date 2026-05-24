"""Build and query selected DESE child-care dashboard data."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import time
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin

import requests
from pypdf import PdfReader


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw_public" / "child_care"
INDEX_PATH = RAW_DIR / "child_care_index.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "child_care_index_report.json"
SOURCE_PAGE = "https://dese.mo.gov/childhood/child-care/child-care-data-dashboards"
SOURCE_LABEL = "DESE Child Care Compliance and Regulation dashboards"

METRIC_LABELS = {
    "slots": "total child care slots",
    "pending_facilities": "facilities pending licensure or License-Exempt approval",
    "inspections": "child care inspections completed",
    "complaint_investigations": "complaint investigations completed",
    "child_care_centers": "child care centers",
    "group_child_care_homes": "group child care homes",
    "family_child_care_homes": "family child care homes",
    "license_exempt_religious_nursery": "license-exempt religious organizations and nursery schools",
    "licensed_under_6_months_pct": "licensed in less than 6 months",
    "licensed_6_to_12_months_pct": "licensed in 6 to 12 months",
    "licensed_over_12_months_pct": "licensed in more than 12 months",
}


class LinkParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.links: list[dict[str, str]] = []
        self.resources: list[str] = []
        self._current_href: str | None = None
        self._current_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        if tag == "a" and values.get("href"):
            self._current_href = urljoin(self.base_url, html.unescape(values["href"]))
            self._current_text = []
        for attr in ("src", "href"):
            if values.get(attr):
                self.resources.append(urljoin(self.base_url, html.unescape(values[attr])))

    def handle_data(self, data: str) -> None:
        if self._current_href:
            self._current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._current_href:
            self.links.append(
                {
                    "text": clean_text(" ".join(self._current_text)),
                    "href": self._current_href,
                }
            )
            self._current_href = None
            self._current_text = []


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_text(value: str) -> str:
    cleaned = re.sub(r"[^A-Z0-9&./-]+", " ", clean_text(value).upper())
    return re.sub(r"\s+", " ", cleaned).strip()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def int_value(value: str) -> int:
    cleaned = value.replace(",", "").replace(".00", "")
    return int(float(cleaned))


def extract_first_int(pattern: str, text: str) -> int | None:
    match = re.search(pattern, text, re.IGNORECASE)
    return int_value(match.group(1)) if match else None


def quarter_label(year: int, quarter: int) -> str:
    return f"{year} Q{quarter}"


def discover_dashboard_pages(source_html: str) -> list[dict[str, Any]]:
    parser = LinkParser(SOURCE_PAGE)
    parser.feed(source_html)
    dashboards: list[dict[str, Any]] = []
    seen: set[str] = set()
    for link in parser.links:
        text = link["text"]
        href = link["href"]
        if "dashboard" not in text.lower() and "child-care-compliance" not in href.lower():
            continue
        year_match = re.search(r"\b(20\d{2})\b", href)
        quarter_match = re.search(r"\bq([1-4])\b|([1-4])(?:st|nd|rd|th)\s+quarter", f"{text} {href}", re.IGNORECASE)
        if not year_match or not quarter_match:
            continue
        year = int(year_match.group(1))
        quarter = int(quarter_match.group(1) or quarter_match.group(2))
        key = f"{year}-Q{quarter}"
        if key in seen:
            continue
        seen.add(key)
        dashboards.append(
            {
                "year": year,
                "quarter": quarter,
                "label": quarter_label(year, quarter),
                "page_title": text or f"{quarter_label(year, quarter)} Dashboard",
                "page_url": href,
            }
        )
    return sorted(dashboards, key=lambda item: (item["year"], item["quarter"]), reverse=True)


def find_pdf_url(page_url: str, page_html: str) -> str:
    parser = LinkParser(page_url)
    parser.feed(page_html)
    candidates = [
        url
        for url in parser.resources
        if "/sites/dese/files/media/pdf/" in url and url.lower().endswith(".pdf")
    ]
    for match in re.finditer(r'(?:src|href)="([^"]+)"', page_html):
        candidate = urljoin(page_url, html.unescape(match.group(1)))
        if "/sites/dese/files/media/pdf/" in candidate and candidate.lower().endswith(".pdf"):
            candidates.append(candidate)
        if "viewer.html?file=" in candidate:
            decoded = unquote(candidate.split("file=", 1)[1])
            decoded = unquote(decoded)
            if "/sites/dese/files/media/pdf/" in decoded and decoded.lower().endswith(".pdf"):
                candidates.append(decoded)
    if not candidates:
        raise RuntimeError(f"Could not find embedded PDF on {page_url}")
    return candidates[-1]


def extract_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def parse_dashboard_text(record: dict[str, Any], text: str) -> dict[str, Any]:
    compact = clean_text(text)
    title_match = re.search(r"Child Care Compliance and Regulation\s+(20\d{2})\s+Quarter\s+([1-4])\s+Dashboard", compact)
    if title_match:
        record["year"] = int(title_match.group(1))
        record["quarter"] = int(title_match.group(2))
        record["label"] = quarter_label(record["year"], record["quarter"])
    period_match = re.search(
        r"(January|April|July|October)\s+\d{1,2},\s+20\d{2},?\s+to\s+(March|June|September|December)\s+\d{1,2},\s+20\d{2}",
        compact,
        re.IGNORECASE,
    )
    record["period"] = period_match.group(0) if period_match else None
    as_of_match = re.search(r"\*Data as of\s+([A-Za-z]+\s+\d{1,2},\s+20\d{2})", compact)
    record["data_as_of"] = as_of_match.group(1) if as_of_match else None
    metrics = {
        "slots": extract_first_int(r"([\d,]+(?:\.00)?)\s+Total child care slots", compact),
        "pending_facilities": extract_first_int(r"([\d,]+(?:\.00)?)\s+Facilities pending", compact),
        "inspections": extract_first_int(r"([\d,]+(?:\.00)?)\s+Child care inspections", compact),
        "complaint_investigations": extract_first_int(r"([\d,]+(?:\.00)?)\s+Complaint investigations", compact),
    }
    number_marker = compact.find("Number of Licensed & License-Exempt Child Care Facilities")
    if number_marker >= 0:
        before_marker = compact[:number_marker]
        numeric_tokens = re.findall(r"\b\d{1,4}(?:,\d{3})?(?:\.00)?\b", before_marker)
        facility_counts = [int_value(value) for value in numeric_tokens[-4:]]
        if len(facility_counts) == 4:
            metrics.update(
                {
                    "child_care_centers": facility_counts[0],
                    "group_child_care_homes": facility_counts[1],
                    "family_child_care_homes": facility_counts[2],
                    "license_exempt_religious_nursery": facility_counts[3],
                }
            )
    amount_marker = compact.find("Amount of Time to Get Licensed")
    if amount_marker >= 0:
        percent_window = compact[amount_marker : amount_marker + 420]
        percentages = [int(value) for value in re.findall(r"\b(\d{1,3})%", percent_window)[:3]]
        if len(percentages) == 3:
            metrics.update(
                {
                    "licensed_under_6_months_pct": percentages[0],
                    "licensed_6_to_12_months_pct": percentages[1],
                    "licensed_over_12_months_pct": percentages[2],
                }
            )
    record["metrics"] = {key: value for key, value in metrics.items() if value is not None}
    return record


def top_dashboard(records: list[dict[str, Any]], metric: str) -> dict[str, Any] | None:
    candidates = [record for record in records if metric in record.get("metrics", {})]
    return max(candidates, key=lambda item: (item["metrics"][metric], item["year"], item["quarter"])) if candidates else None


def build_child_care_index(force: bool = False) -> dict[str, Any]:
    if INDEX_PATH.exists() and not force:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (compatible; MissouriPublicDataChat/1.0; +https://github.com/Stroudmj00/missouri-tiny-llm-case-study)",
            "Accept": "text/html,application/pdf,*/*;q=0.8",
        }
    )
    start = time.perf_counter()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    source_response = session.get(SOURCE_PAGE, timeout=60)
    source_response.raise_for_status()
    dashboards = discover_dashboard_pages(source_response.text)
    records: list[dict[str, Any]] = []
    pdf_bytes_total = 0
    pdf_hash_parts: list[bytes] = []
    for dashboard in dashboards:
        page_response = session.get(dashboard["page_url"], timeout=60)
        page_response.raise_for_status()
        pdf_url = find_pdf_url(dashboard["page_url"], page_response.text)
        pdf_response = session.get(pdf_url, timeout=90)
        pdf_response.raise_for_status()
        pdf_bytes = pdf_response.content
        pdf_bytes_total += len(pdf_bytes)
        pdf_hash_parts.append(pdf_bytes)
        pdf_path = RAW_DIR / f"child_care_dashboard_{dashboard['year']}_q{dashboard['quarter']}.pdf"
        pdf_path.write_bytes(pdf_bytes)
        text = extract_pdf_text(pdf_path)
        records.append(
            parse_dashboard_text(
                {
                    **dashboard,
                    "pdf_url": pdf_url,
                    "local_pdf": str(pdf_path.relative_to(PROJECT_ROOT)),
                    "bytes": len(pdf_bytes),
                    "sha256": sha256_bytes(pdf_bytes),
                },
                text,
            )
        )
    records = sorted(records, key=lambda item: (item["year"], item["quarter"]), reverse=True)
    metric_coverage = Counter(metric for record in records for metric in record.get("metrics", {}))
    latest = records[0] if records else {}
    payload = {
        "generated_at_utc": utc_now(),
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "source": SOURCE_LABEL,
        "source_page": SOURCE_PAGE,
        "index_path": str(INDEX_PATH.relative_to(PROJECT_ROOT)),
        "bytes": len(source_response.content) + pdf_bytes_total,
        "sha256": sha256_bytes(source_response.content + json.dumps(records, sort_keys=True).encode("utf-8") + b"".join(pdf_hash_parts)),
        "dashboard_count": len(records),
        "year_quarters": [record["label"] for record in records],
        "latest_year": latest.get("year"),
        "latest_quarter": latest.get("quarter"),
        "latest_label": latest.get("label"),
        "latest_data_as_of": latest.get("data_as_of"),
        "metric_coverage": dict(sorted(metric_coverage.items())),
        "records": records,
    }
    write_json(INDEX_PATH, payload)
    write_json(
        REPORT_PATH,
        {
            "generated_at_utc": payload["generated_at_utc"],
            "elapsed_seconds": payload["elapsed_seconds"],
            "source": payload["source"],
            "source_page": payload["source_page"],
            "index_path": payload["index_path"],
            "bytes": payload["bytes"],
            "sha256": payload["sha256"],
            "dashboard_count": payload["dashboard_count"],
            "year_quarters": payload["year_quarters"],
            "latest_label": payload["latest_label"],
            "latest_data_as_of": payload["latest_data_as_of"],
            "metric_coverage": payload["metric_coverage"],
            "latest_metrics": latest.get("metrics", {}),
        },
    )
    return payload


def year_quarter_in_question(question: str, payload: dict[str, Any]) -> tuple[int, int] | None:
    lowered = question.lower()
    year_match = re.search(r"\b(20\d{2})\b", lowered)
    quarter_match = re.search(r"\bq([1-4])\b|quarter\s+([1-4])|([1-4])(?:st|nd|rd|th)\s+quarter", lowered)
    if "latest" in lowered or "current" in lowered:
        return payload.get("latest_year"), payload.get("latest_quarter")
    if year_match and quarter_match:
        return int(year_match.group(1)), int(quarter_match.group(1) or quarter_match.group(2) or quarter_match.group(3))
    return None


def metric_key_for_question(question: str) -> str | None:
    lowered = question.lower()
    if "slot" in lowered or "capacity" in lowered:
        return "slots"
    if "pending" in lowered:
        return "pending_facilities"
    if "complaint" in lowered:
        return "complaint_investigations"
    if "inspection" in lowered:
        return "inspections"
    if "center" in lowered:
        return "child_care_centers"
    if "group" in lowered and "home" in lowered:
        return "group_child_care_homes"
    if "family" in lowered and "home" in lowered:
        return "family_child_care_homes"
    if "religious" in lowered or "nursery" in lowered or "license-exempt" in lowered:
        return "license_exempt_religious_nursery"
    if "less than 6" in lowered or "under 6" in lowered:
        return "licensed_under_6_months_pct"
    if "6 to 12" in lowered or "6 - 12" in lowered:
        return "licensed_6_to_12_months_pct"
    if "more than 12" in lowered or "over 12" in lowered:
        return "licensed_over_12_months_pct"
    return None


def format_metric_value(key: str, value: int) -> str:
    return f"{value}%" if key.endswith("_pct") else f"{value:,}"


def asks_for_top(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["top", "highest", "largest", "most", "maximum"])


class ChildCareIndex:
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

    def citation(self, matched_rows: int = 0, record: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        payload = self.payload()
        files = [
            {
                "category": "child_care_dashboard_source",
                "category_label": "DESE child care data dashboards",
                "file_name": payload.get("source_page", SOURCE_PAGE),
                "row_count": payload.get("dashboard_count"),
                "bytes": payload.get("bytes"),
                "sha256": payload.get("sha256"),
            }
        ]
        if record:
            files.append(
                {
                    "category": "child_care_dashboard_pdf",
                    "category_label": f"{record.get('label')} child care dashboard PDF",
                    "file_name": record.get("pdf_url"),
                    "row_count": None,
                    "bytes": record.get("bytes"),
                    "sha256": record.get("sha256"),
                }
            )
        return [
            {
                "dataset": payload.get("source", SOURCE_LABEL),
                "category": "Child Care",
                "kind": "quarterly dashboard aggregate",
                "lookup_table": "child_care_index",
                "year": record.get("year") if record else None,
                "year_range": payload.get("year_quarters"),
                "source_files": files,
                "source_file_count": len(files),
                "source_rows": payload.get("dashboard_count"),
                "matched_rows": matched_rows,
            }
        ]

    def unavailable_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "The selected child-care dashboard index has not been built yet. Run "
                "`python scripts/build_child_care_index.py --force` to download the public DESE dashboard PDFs and build exact lookups."
            ),
            "retrieved_context_id": "child_care_index:missing",
            "retrieved_source": "child_care_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "The child-care route exists, but the local ignored index is missing.",
            "citations": [],
            "source_rows": [],
        }

    def summary_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        latest_metrics = payload.get("records", [{}])[0].get("metrics", {}) if payload.get("records") else {}
        metric_text = "; ".join(
            f"{METRIC_LABELS[key]}: {format_metric_value(key, value)}"
            for key, value in latest_metrics.items()
            if key in {"slots", "pending_facilities", "inspections", "complaint_investigations"}
        )
        return {
            "question": question,
            "answer": (
                f"The selected child-care exact lookup layer indexes {payload.get('dashboard_count', 0):,} official DESE "
                f"Child Care Compliance and Regulation dashboard PDF(s): {', '.join(payload.get('year_quarters', []))}. "
                f"Latest indexed dashboard: {payload.get('latest_label')} with data as of {payload.get('latest_data_as_of')}. "
                "It can answer dashboard aggregate questions about slots, pending facilities, inspections, complaint investigations, "
                "facility type counts, and licensing-time percentages. "
                f"Latest key metrics: {metric_text}."
            ),
            "retrieved_context_id": "child_care_index:summary",
            "retrieved_source": "child_care_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local DESE child-care dashboard index.",
            "citations": self.citation(matched_rows=payload.get("dashboard_count", 0)),
            "source_rows": [],
        }

    def find_record(self, year: int, quarter: int) -> dict[str, Any] | None:
        for record in self.records():
            if record.get("year") == year and record.get("quarter") == quarter:
                return record
        return None

    def metric_answer(self, question: str, record: dict[str, Any], key: str) -> dict[str, Any]:
        value = record.get("metrics", {}).get(key)
        if value is None:
            return self.missing_answer(question)
        return {
            "question": question,
            "answer": (
                f"For the {record['label']} DESE child-care dashboard, {METRIC_LABELS[key]} was "
                f"{format_metric_value(key, value)}. Dashboard period: {record.get('period') or 'not parsed'}; "
                f"data as of {record.get('data_as_of') or 'not listed'}."
            ),
            "retrieved_context_id": f"child_care_index:metric:{record['label']}:{key}",
            "retrieved_source": "child_care_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from an official DESE Child Care Compliance and Regulation dashboard PDF.",
            "citations": self.citation(matched_rows=1, record=record),
            "source_rows": [{"source_file": record.get("pdf_url"), "values": {"label": record["label"], key: value}}],
        }

    def rank_answer(self, question: str, key: str) -> dict[str, Any]:
        record = top_dashboard(self.records(), key)
        if not record:
            return self.missing_answer(question)
        value = record["metrics"][key]
        ranked = sorted(
            [item for item in self.records() if key in item.get("metrics", {})],
            key=lambda item: item["metrics"][key],
            reverse=True,
        )
        rendered = "; ".join(f"{item['label']}: {format_metric_value(key, item['metrics'][key])}" for item in ranked[:5])
        return {
            "question": question,
            "answer": (
                f"The indexed DESE child-care dashboard with the highest {METRIC_LABELS[key]} is {record['label']} "
                f"with {format_metric_value(key, value)}. Ranked dashboards: {rendered}."
            ),
            "retrieved_context_id": f"child_care_index:rank:{key}",
            "retrieved_source": "child_care_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed by ranking official DESE child-care dashboard aggregate metrics.",
            "citations": self.citation(matched_rows=len(ranked), record=record),
            "source_rows": [
                {"source_file": item.get("pdf_url"), "values": {"label": item["label"], key: item["metrics"][key]}}
                for item in ranked[:5]
            ],
        }

    def missing_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "The selected child-care dashboard index covers quarterly aggregate metrics, but this question did not match a supported "
                "quarter or metric. Try `What child care dashboard data is indexed?`, `How many child care slots are listed in 2025 Q4?`, "
                "`How many complaint investigations were completed in 2025 Q4?`, or `Which quarter had the most child care inspections?`."
            ),
            "retrieved_context_id": "child_care_index:no_match",
            "retrieved_source": "child_care_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Answered from child-care dashboard coverage metadata because no exact supported lookup matched.",
            "citations": self.citation(),
            "source_rows": [],
        }

    def answer(self, question: str) -> dict[str, Any] | None:
        if not self.available():
            return self.unavailable_answer(question)
        payload = self.payload()
        lowered = question.lower()
        if "indexed" in lowered or "lookup" in lowered or "what child care data" in lowered:
            return self.summary_answer(question)
        key = metric_key_for_question(question)
        if key is None:
            return self.missing_answer(question)
        if asks_for_top(question):
            return self.rank_answer(question, key)
        year_quarter = year_quarter_in_question(question, payload)
        if year_quarter:
            year, quarter = year_quarter
            record = self.find_record(year, quarter)
            return self.metric_answer(question, record, key) if record else self.missing_answer(question)
        latest = self.records()[0] if self.records() else None
        return self.metric_answer(question, latest, key) if latest else self.missing_answer(question)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    payload = build_child_care_index(force=args.force)
    print(json.dumps({key: value for key, value in payload.items() if key != "records"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
