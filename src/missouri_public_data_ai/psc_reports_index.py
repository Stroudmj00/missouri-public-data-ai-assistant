"""Build and query Missouri Public Service Commission report metadata."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw_public" / "psc_reports"
INDEX_PATH = RAW_DIR / "psc_reports_index.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "psc_reports_index_report.json"
LANDING_PAGE = "https://psc.mo.gov/General/PSC_Reports"

REPORT_LINK_PATTERN = re.compile(r"<a\s+href=['\"]?([^'\" >]+)['\"]?[^>]*>(.*?)</a>", re.I | re.S)
REPORT_TITLE_PATTERN = re.compile(
    r"PSC\s+Reports\s+Vol\s+(?P<volume>\d+)\s+"
    r"(?P<series>MPSC\s+\d+d)\s+"
    r"(?P<start>[A-Za-z]{3,4}\s+\d{1,2},\s+\d{4})\s*-\s*"
    r"(?P<end>[A-Za-z]{3,4}\s+\d{1,2},\s+\d{4})",
    re.I,
)


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
    return re.sub(r"\s+", " ", decoded).strip()


def parse_date_label(value: str) -> str | None:
    normalized = value.replace("Sept", "Sep")
    for date_format in ("%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(normalized, date_format).date().isoformat()
        except ValueError:
            continue
    return None


def parse_report_links(page_text: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for href, label_html in REPORT_LINK_PATTERN.findall(page_text):
        label = clean_text(label_html)
        if not label.lower().startswith("psc reports vol"):
            continue
        match = REPORT_TITLE_PATTERN.search(label)
        if not match:
            continue
        pdf_url = urljoin(LANDING_PAGE, href)
        if pdf_url in seen_urls:
            continue
        seen_urls.add(pdf_url)
        start_date = parse_date_label(match.group("start"))
        end_date = parse_date_label(match.group("end"))
        start_year = int(start_date[:4]) if start_date else None
        end_year = int(end_date[:4]) if end_date else None
        years = list(range(start_year, end_year + 1)) if start_year and end_year else []
        volume = int(match.group("volume"))
        records.append(
            {
                "title": label,
                "volume": volume,
                "volume_label": f"Vol {volume:02d}",
                "series": clean_text(match.group("series")),
                "start_label": clean_text(match.group("start")),
                "end_label": clean_text(match.group("end")),
                "start_date": start_date,
                "end_date": end_date,
                "start_year": start_year,
                "end_year": end_year,
                "years_covered": years,
                "pdf_url": pdf_url,
                "landing_page": LANDING_PAGE,
            }
        )
    return sorted(records, key=lambda item: item["volume"], reverse=True)


def build_psc_reports_index(force: bool = False) -> dict[str, Any]:
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
    response = session.get(LANDING_PAGE, timeout=60)
    response.raise_for_status()
    page_text = response.text
    records = parse_report_links(page_text)
    years = sorted({year for record in records for year in record.get("years_covered", [])})
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_DIR / "psc_reports_page.html").write_text(page_text, encoding="utf-8")
    latest = records[0] if records else None
    payload = {
        "generated_at_utc": utc_now(),
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "source": "Missouri Public Service Commission reports",
        "landing_page": LANDING_PAGE,
        "index_path": str(INDEX_PATH.relative_to(PROJECT_ROOT)),
        "bytes": len(page_text.encode("utf-8", errors="replace")),
        "sha256": sha256_text(page_text),
        "report_count": len(records),
        "min_year": min(years) if years else None,
        "max_year": max(years) if years else None,
        "latest_volume": latest["volume"] if latest else None,
        "latest_title": latest["title"] if latest else None,
        "notes": [
            "This index stores official PSC report metadata and PDF links only.",
            "It does not download report PDFs or interpret regulatory orders.",
            "Questions about case outcomes, rates, or legal conclusions still need a dedicated document parser.",
        ],
        "records": records,
    }
    write_json(INDEX_PATH, payload)
    write_json(
        REPORT_PATH,
        {key: value for key, value in payload.items() if key != "records"},
    )
    return payload


def requested_years(question: str) -> list[int]:
    return [int(year) for year in re.findall(r"\b(19\d{2}|20\d{2})\b", question)]


def requested_volume(question: str) -> int | None:
    match = re.search(r"\b(?:vol(?:ume)?\.?\s*)(\d{1,2})\b", question, flags=re.I)
    return int(match.group(1)) if match else None


class PscReportsIndex:
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
                "dataset": payload.get("source", "Missouri Public Service Commission reports"),
                "category": "Utilities",
                "kind": "PSC report metadata",
                "lookup_table": "psc_reports_index",
                "year": None,
                "year_range": (
                    f"{payload.get('min_year')}-{payload.get('max_year')}"
                    if payload.get("min_year") and payload.get("max_year")
                    else None
                ),
                "source_files": [
                    {
                        "category": "psc_reports",
                        "category_label": "PSC reports landing page",
                        "file_name": payload.get("landing_page", LANDING_PAGE),
                        "row_count": payload.get("report_count"),
                        "bytes": payload.get("bytes"),
                        "sha256": payload.get("sha256"),
                    }
                ],
                "source_file_count": 1,
                "source_rows": payload.get("report_count"),
                "matched_rows": matched_rows,
            }
        ]

    def unavailable_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "The PSC report metadata index has not been built yet. Run "
                "`python scripts/build_psc_reports_index.py --force` to index the official PSC Reports page."
            ),
            "retrieved_context_id": "psc_reports_index:missing",
            "retrieved_source": "psc_reports_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "The PSC route exists, but the local ignored index is missing.",
            "citations": [],
            "source_rows": [],
        }

    def summary_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        latest = self.records()[0] if self.records() else {}
        return {
            "question": question,
            "answer": (
                "The selected PSC exact lookup layer indexes official Missouri Public Service Commission report metadata. "
                f"It contains {payload.get('report_count', 0):,} report PDF link(s), covering "
                f"{payload.get('min_year')} through {payload.get('max_year')}. "
                f"Latest indexed volume: {latest.get('title', 'not available')}. "
                "It can answer which volume covers a year, what period a volume covers, and where the official PDF is linked."
            ),
            "retrieved_context_id": "psc_reports_index:summary",
            "retrieved_source": "psc_reports_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local PSC report metadata index.",
            "citations": self.citation(matched_rows=payload.get("report_count", 0)),
            "source_rows": [],
        }

    def latest_answer(self, question: str) -> dict[str, Any]:
        record = self.records()[0]
        return self.record_answer(question, record, context_id="psc_reports_index:latest")

    def volume_answer(self, question: str, volume: int) -> dict[str, Any]:
        for record in self.records():
            if record.get("volume") == volume:
                return self.record_answer(question, record, context_id=f"psc_reports_index:volume:{volume}")
        return self.missing_answer(question, f"I have PSC report metadata indexed, but not volume {volume}.")

    def year_answer(self, question: str, year: int) -> dict[str, Any]:
        rows = [record for record in self.records() if year in record.get("years_covered", [])]
        if not rows:
            payload = self.payload()
            return self.missing_answer(
                question,
                f"I have PSC report metadata for {payload.get('min_year')}-{payload.get('max_year')}, but no indexed report volume covers {year}.",
            )
        rendered = "; ".join(
            f"{row['volume_label']} ({row['start_label']} - {row['end_label']}): {row['pdf_url']}"
            for row in rows
        )
        return {
            "question": question,
            "answer": f"The indexed PSC report metadata shows {year} is covered by: {rendered}.",
            "retrieved_context_id": f"psc_reports_index:year:{year}",
            "retrieved_source": "psc_reports_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local PSC report metadata index.",
            "citations": self.citation(matched_rows=len(rows)),
            "source_rows": [{"source_file": LANDING_PAGE, "values": row} for row in rows],
        }

    def record_answer(self, question: str, record: dict[str, Any], context_id: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                f"{record['volume_label']} of the Missouri PSC Reports is `{record['title']}`. "
                f"It covers {record['start_label']} through {record['end_label']}. "
                f"Official PDF: {record['pdf_url']}. "
                "This is metadata only; the local index does not interpret cases, rates, or orders inside the PDF."
            ),
            "retrieved_context_id": context_id,
            "retrieved_source": "psc_reports_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local PSC report metadata index.",
            "citations": self.citation(matched_rows=1),
            "source_rows": [{"source_file": LANDING_PAGE, "values": record}],
        }

    def missing_answer(self, question: str, message: str | None = None) -> dict[str, Any]:
        return {
            "question": question,
            "answer": message
            or (
                "I have indexed PSC report metadata, but this question did not match a supported report volume, "
                "year, latest-report, or coverage-summary request."
            ),
            "retrieved_context_id": "psc_reports_index:no_match",
            "retrieved_source": "psc_reports_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Answered from PSC coverage metadata because no exact report row matched.",
            "citations": self.citation(),
            "source_rows": [],
        }

    def answer(self, question: str) -> dict[str, Any] | None:
        if not self.available():
            return self.unavailable_answer(question)
        lowered = question.lower()
        volume = requested_volume(question)
        if volume is not None:
            return self.volume_answer(question, volume)
        if any(term in lowered for term in ["latest", "newest", "most recent"]):
            return self.latest_answer(question)
        years = requested_years(question)
        if years:
            return self.year_answer(question, years[-1])
        if any(term in lowered for term in ["how many", "count", "indexed", "connected", "available", "coverage", "data"]):
            return self.summary_answer(question)
        return self.summary_answer(question)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    payload = build_psc_reports_index(force=args.force)
    print(json.dumps({key: value for key, value in payload.items() if key != "records"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
