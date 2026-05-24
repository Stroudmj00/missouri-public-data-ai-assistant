"""Build and query Missouri State Auditor report metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw_public" / "state_auditor"
INDEX_PATH = RAW_DIR / "state_auditor_index.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "state_auditor_index_report.json"
SEARCH_URL = "https://auditor.mo.gov/AuditReport/SearchAudits"
LANDING_PAGE = "https://auditor.mo.gov/AuditReport/Reports"
VIEW_REPORT_URL = "https://auditor.mo.gov/AuditReport/ViewReport"
DEFAULT_START_YEAR = 1999
GENERIC_AUDIT_TOKENS = {
    "AN",
    "AND",
    "AUDIT",
    "AUDITOR",
    "COUNTY",
    "DATA",
    "FIND",
    "FOR",
    "IN",
    "ME",
    "MISSOURI",
    "MO",
    "OF",
    "REPORT",
    "REPORTS",
    "SHOW",
    "STATE",
    "THE",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_text(value: Any) -> str:
    cleaned = re.sub(r"[^A-Z0-9&]+", " ", clean_text(value).upper())
    return re.sub(r"\s+", " ", cleaned).strip()


def report_number(value: Any) -> str:
    return re.sub(r"\s+", "", clean_text(value))


def display_report_number(value: Any, fallback: str) -> str:
    text = clean_text(value)
    return text if text else fallback


def date_part(value: Any) -> str | None:
    text = clean_text(value)
    if not text or text.startswith("9999-"):
        return None
    return text.split("T", 1)[0]


def year_from_date(value: str | None) -> int | None:
    if not value:
        return None
    match = re.match(r"(\d{4})", value)
    return int(match.group(1)) if match else None


def relative_report_url(path: Any) -> str | None:
    text = clean_text(path)
    if not text:
        return None
    if text.startswith("http://") or text.startswith("https://"):
        return text
    if text.startswith("~/"):
        return urljoin("https://auditor.mo.gov/", text[2:])
    return urljoin("https://auditor.mo.gov/", text.lstrip("/"))


def title_tokens(value: str) -> set[str]:
    return {token for token in normalize_text(value).split() if token not in GENERIC_AUDIT_TOKENS and len(token) > 2}


def infer_topics(title: str) -> list[str]:
    lowered = title.lower()
    topics: list[str] = []
    if "financial statement" in lowered:
        topics.append("financial statements")
    if "follow-up" in lowered or "follow up" in lowered:
        topics.append("follow-up")
    if "tax increment" in lowered or "tif" in lowered:
        topics.append("tax increment financing")
    if "data security" in lowered or "cyber" in lowered:
        topics.append("data security")
    if "single audit" in lowered:
        topics.append("single audit")
    if "city of" in lowered or "village of" in lowered:
        topics.append("local government")
    if "county" in lowered:
        topics.append("county")
    if "/" in title:
        topics.append("state agency or division")
    return topics or ["audit report"]


def search_params(year: int, page: int = 1, rows: int = 1000) -> dict[str, str | int]:
    return {
        "SearchAuditTitle": "",
        "SearchYearStart": str(year),
        "SearchYearEnd": str(year),
        "SearchLocalState": "",
        "SearchStateAgency": "",
        "SearchRegion": "",
        "SearchCounty": "",
        "page": page,
        "rows": rows,
        "sidx": "release_datetime",
        "sord": "desc",
    }


def fetch_year(session: requests.Session, year: int) -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
    all_rows: list[dict[str, Any]] = []
    texts: list[str] = []
    pages = 0
    for page in range(1, 20):
        response = session.get(SEARCH_URL, params=search_params(year, page=page), timeout=90)
        response.raise_for_status()
        texts.append(response.text)
        payload = response.json()
        rows = payload.get("data") or []
        if not rows:
            break
        all_rows.extend(rows)
        pages = page
        if len(rows) < 1000:
            break
    return all_rows, "\n".join(texts), {"year": year, "rows": len(all_rows), "pages": pages}


def normalize_report(row: dict[str, Any]) -> dict[str, Any]:
    rpt_number = report_number(row.get("rpt_number"))
    display = display_report_number(row.get("ReportNumberDisplay"), rpt_number)
    title = clean_text(row.get("title"))
    release_date = date_part(row.get("release_datetime"))
    end_date = date_part(row.get("end_date"))
    view_url = clean_text(row.get("FullReportLinkExternal")) or clean_text(row.get("AuditReportsGridReportLink"))
    if not view_url and rpt_number:
        view_url = f"{VIEW_REPORT_URL}?report={rpt_number}"
    pdf_url = relative_report_url(row.get("full_rpt_link"))
    summary_url = clean_text(row.get("CitizensSummaryPageLink")) or relative_report_url(row.get("static_citz_summary_link"))
    return {
        "report_number": rpt_number,
        "report_number_display": display,
        "title": title,
        "title_norm": normalize_text(title),
        "release_datetime": clean_text(row.get("release_datetime")) or None,
        "release_date": release_date,
        "release_year": year_from_date(release_date),
        "end_date": end_date,
        "topics": infer_topics(title),
        "view_report_url": view_url,
        "pdf_url": pdf_url,
        "citizens_summary_url": summary_url or None,
        "has_custom_report_link": bool(row.get("HasCustomReportLink")),
    }


def build_state_auditor_index(force: bool = False, start_year: int = DEFAULT_START_YEAR, end_year: int | None = None) -> dict[str, Any]:
    if INDEX_PATH.exists() and not force:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))

    resolved_end_year = end_year or datetime.now(timezone.utc).year
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (compatible; MissouriPublicDataChat/1.0; +https://github.com/Stroudmj00/missouri-tiny-llm-case-study)",
            "Accept": "application/json,*/*;q=0.8",
        }
    )
    start = time.perf_counter()
    source_texts: list[str] = []
    fetch_stats: list[dict[str, Any]] = []
    deduped: dict[str, dict[str, Any]] = {}
    for year in range(start_year, resolved_end_year + 1):
        rows, text, stats = fetch_year(session, year)
        source_texts.append(text)
        fetch_stats.append(stats)
        for row in rows:
            record = normalize_report(row)
            key = record["report_number"] or f"{record['title_norm']}:{record.get('release_datetime')}"
            if record["report_number"]:
                deduped[key] = record

    records = sorted(
        deduped.values(),
        key=lambda item: (item.get("release_datetime") or "", item.get("report_number") or ""),
        reverse=True,
    )
    year_counts = Counter(record["release_year"] for record in records if record.get("release_year"))
    topic_counts = Counter(topic for record in records for topic in record.get("topics", []))
    source_text = "\n".join(source_texts)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    write_json(RAW_DIR / "state_auditor_raw_year_fetch_stats.json", fetch_stats)
    payload = {
        "generated_at_utc": utc_now(),
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "source": "Missouri State Auditor report search",
        "source_url": SEARCH_URL,
        "landing_page": LANDING_PAGE,
        "index_path": str(INDEX_PATH.relative_to(PROJECT_ROOT)),
        "start_year": start_year,
        "end_year": resolved_end_year,
        "bytes": len(source_text.encode("utf-8")),
        "sha256": sha256_text(source_text),
        "record_count": len(records),
        "year_counts": {str(year): count for year, count in sorted(year_counts.items(), reverse=True)},
        "topic_counts": dict(topic_counts.most_common(12)),
        "fetch_stats": fetch_stats,
        "sanitization_note": (
            "This index stores report metadata and official links only. It does not download report PDFs or summarize audit findings."
        ),
        "records": records,
    }
    write_json(INDEX_PATH, payload)
    write_json(
        REPORT_PATH,
        {
            "generated_at_utc": payload["generated_at_utc"],
            "elapsed_seconds": payload["elapsed_seconds"],
            "source": payload["source"],
            "source_url": payload["source_url"],
            "landing_page": payload["landing_page"],
            "index_path": payload["index_path"],
            "start_year": payload["start_year"],
            "end_year": payload["end_year"],
            "bytes": payload["bytes"],
            "sha256": payload["sha256"],
            "record_count": payload["record_count"],
            "year_counts": payload["year_counts"],
            "topic_counts": payload["topic_counts"],
            "latest_reports": records[:10],
            "fetch_stats": payload["fetch_stats"],
            "sanitization_note": payload["sanitization_note"],
        },
    )
    return payload


def requested_years(question: str) -> list[int]:
    years = [int(match) for match in re.findall(r"\b(19\d{2}|20\d{2})\b", question)]
    return sorted(set(years))


def requested_limit(question: str, default: int = 5, maximum: int = 10) -> int:
    lowered = question.lower()
    match = re.search(r"\b(?:top|first|latest|recent|show(?: me)?|list)\s+(\d{1,2})\b", lowered)
    if match:
        return max(1, min(maximum, int(match.group(1))))
    return default


class StateAuditorIndex:
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
                "dataset": payload.get("source", "Missouri State Auditor report search"),
                "category": "Audits and accountability",
                "kind": "report metadata rows",
                "lookup_table": "state_auditor_index",
                "year": None,
                "year_range": f"{payload.get('start_year')}-{payload.get('end_year')}",
                "source_files": [
                    {
                        "category": "state_auditor",
                        "category_label": "Missouri State Auditor report search API",
                        "file_name": payload.get("source_url", SEARCH_URL),
                        "row_count": payload.get("record_count"),
                        "bytes": payload.get("bytes"),
                        "sha256": payload.get("sha256"),
                    },
                    {
                        "category": "state_auditor",
                        "category_label": "Missouri State Auditor report search page",
                        "file_name": payload.get("landing_page", LANDING_PAGE),
                        "row_count": None,
                        "bytes": None,
                        "sha256": None,
                    },
                ],
                "source_file_count": 2,
                "source_rows": payload.get("record_count"),
                "matched_rows": matched_rows,
            }
        ]

    def unavailable_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "The Missouri State Auditor metadata index has not been built yet. Run "
                "`python scripts/build_state_auditor_index.py --force` to build report-title/date/link lookup."
            ),
            "retrieved_context_id": "state_auditor_index:missing",
            "retrieved_source": "state_auditor_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "The Auditor route exists, but the local ignored index is missing.",
            "citations": [],
            "source_rows": [],
        }

    def summary_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        year_counts = payload.get("year_counts", {})
        recent_years = "; ".join(
            f"{year}: {year_counts[str(year)]}"
            for year in sorted((int(year) for year in year_counts), reverse=True)[:5]
        )
        latest = "; ".join(f"{row['report_number_display'].strip()} {row['title']}" for row in self.records()[:5])
        return {
            "question": question,
            "answer": (
                "The Missouri State Auditor exact metadata layer indexes official report search records from "
                f"{payload.get('start_year')} through {payload.get('end_year')}. It contains "
                f"{payload.get('record_count', 0):,} report metadata row(s) with titles, report numbers, release dates, "
                "topics, official view links, and PDF links when listed. It does not download PDFs or interpret audit findings. "
                f"Recent year counts: {recent_years}. Latest indexed reports: {latest}."
            ),
            "retrieved_context_id": "state_auditor_index:summary",
            "retrieved_source": "state_auditor_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": payload.get("sanitization_note"),
            "citations": self.citation(matched_rows=payload.get("record_count", 0)),
            "source_rows": [],
        }

    def records_for_year(self, year: int) -> list[dict[str, Any]]:
        return [record for record in self.records() if record.get("release_year") == year]

    def find_by_report_number(self, question: str) -> dict[str, Any] | None:
        compact_question = re.sub(r"[^0-9]", "", question)
        candidates = []
        for record in self.records():
            number = re.sub(r"[^0-9]", "", record.get("report_number", ""))
            display_number = re.sub(r"[^0-9]", "", record.get("report_number_display", ""))
            if number and number in compact_question:
                candidates.append(record)
            elif display_number and display_number in compact_question:
                candidates.append(record)
        if not candidates:
            return None
        return sorted(candidates, key=lambda item: item.get("release_datetime") or "", reverse=True)[0]

    def keyword_matches(self, question: str) -> list[dict[str, Any]]:
        question_tokens = title_tokens(question)
        years = requested_years(question)
        matches: list[tuple[int, str, dict[str, Any]]] = []
        for record in self.records():
            if years and record.get("release_year") not in years:
                continue
            tokens = title_tokens(record.get("title", ""))
            score = len(tokens & question_tokens)
            if score:
                matches.append((score, record.get("release_datetime") or "", record))
        return [item[2] for item in sorted(matches, key=lambda item: (item[0], item[1]), reverse=True)]

    def report_answer(self, question: str, record: dict[str, Any]) -> dict[str, Any]:
        topics = ", ".join(record.get("topics", []))
        pdf_text = f" PDF: {record['pdf_url']}." if record.get("pdf_url") else ""
        summary_text = f" Citizen summary: {record['citizens_summary_url']}." if record.get("citizens_summary_url") else ""
        return {
            "question": question,
            "answer": (
                f"Auditor report {record['report_number_display'].strip()} is `{record['title']}`, released "
                f"{record.get('release_date') or 'date not listed'}. Topics inferred from title: {topics}. "
                f"Official report page: {record.get('view_report_url')}.{pdf_text}{summary_text} "
                "This is metadata only; the local index does not interpret the report findings."
            ),
            "retrieved_context_id": f"state_auditor_index:report:{record.get('report_number')}",
            "retrieved_source": "state_auditor_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": self.payload().get("sanitization_note"),
            "citations": self.citation(matched_rows=1),
            "source_rows": [{"source_file": SEARCH_URL, "values": record}],
        }

    def year_answer(self, question: str, year: int) -> dict[str, Any]:
        rows = self.records_for_year(year)
        rendered = "; ".join(f"{row['report_number_display'].strip()} {row['title']}" for row in rows[: requested_limit(question)])
        return {
            "question": question,
            "answer": (
                f"The indexed Missouri State Auditor metadata contains {len(rows):,} report(s) released in {year}. "
                f"Latest examples: {rendered}."
            ),
            "retrieved_context_id": f"state_auditor_index:year:{year}",
            "retrieved_source": "state_auditor_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": self.payload().get("sanitization_note"),
            "citations": self.citation(matched_rows=len(rows)),
            "source_rows": [{"source_file": SEARCH_URL, "values": row} for row in rows[:5]],
        }

    def latest_answer(self, question: str) -> dict[str, Any]:
        rows = self.records()[: requested_limit(question)]
        rendered = "\n".join(
            f"{index}. {row['report_number_display'].strip()} - {row['title']} ({row.get('release_date')}); {row.get('view_report_url')}"
            for index, row in enumerate(rows, 1)
        )
        return {
            "question": question,
            "answer": "Latest indexed Missouri State Auditor report metadata:\n" + rendered,
            "retrieved_context_id": "state_auditor_index:latest",
            "retrieved_source": "state_auditor_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": self.payload().get("sanitization_note"),
            "citations": self.citation(matched_rows=len(rows)),
            "source_rows": [{"source_file": SEARCH_URL, "values": row} for row in rows[:5]],
        }

    def search_answer(self, question: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
        limit = requested_limit(question)
        rendered = "\n".join(
            f"{index}. {row['report_number_display'].strip()} - {row['title']} ({row.get('release_date')}); {row.get('view_report_url')}"
            for index, row in enumerate(rows[:limit], 1)
        )
        return {
            "question": question,
            "answer": f"I found {len(rows):,} indexed Auditor report(s) matching the question terms. Best matches:\n{rendered}",
            "retrieved_context_id": "state_auditor_index:search",
            "retrieved_source": "state_auditor_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": self.payload().get("sanitization_note"),
            "citations": self.citation(matched_rows=len(rows)),
            "source_rows": [{"source_file": SEARCH_URL, "values": row} for row in rows[:5]],
        }

    def missing_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "I have indexed Missouri State Auditor report metadata, but this question did not match a supported report number, "
                "release year, latest-report request, or title keyword search. Try `What Auditor report data is indexed?`, "
                "`What are the latest Missouri Auditor reports?`, or `Find Auditor reports about Cedar County`."
            ),
            "retrieved_context_id": "state_auditor_index:no_match",
            "retrieved_source": "state_auditor_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Answered from Auditor metadata coverage because no exact record matched.",
            "citations": self.citation(),
            "source_rows": [],
        }

    def answer(self, question: str) -> dict[str, Any] | None:
        if not self.available():
            return self.unavailable_answer(question)
        lowered = question.lower()
        if re.search(r"\b(auditor|audit reports?|state auditor)\b.*\b(indexed|lookup|metadata|data)\b", lowered):
            return self.summary_answer(question)
        report = self.find_by_report_number(question)
        if report is not None:
            return self.report_answer(question, report)
        if any(term in lowered for term in ["latest", "recent", "newest"]):
            return self.latest_answer(question)
        matches = self.keyword_matches(question)
        if matches and (
            any(term in lowered for term in ["about", "mention", "mentions", "matching", "search", "find"])
            or "financial statement" in lowered
            or "data security" in lowered
        ):
            return self.search_answer(question, matches)
        years = requested_years(question)
        if years and any(term in lowered for term in ["how many", "count", "released", "reports"]):
            return self.year_answer(question, years[-1])
        if matches:
            return self.search_answer(question, matches)
        return self.missing_answer(question)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--start-year", type=int, default=DEFAULT_START_YEAR)
    parser.add_argument("--end-year", type=int, default=None)
    args = parser.parse_args()
    payload = build_state_auditor_index(force=args.force, start_year=args.start_year, end_year=args.end_year)
    print(json.dumps({key: value for key, value in payload.items() if key != "records"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
