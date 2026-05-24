"""Build and query selected DESE Annual Performance Report ranking data."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from pypdf import PdfReader


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw_public" / "dese_apr"
INDEX_PATH = RAW_DIR / "dese_apr_index.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "dese_apr_index_report.json"
SOURCE_NAME = "DESE 2025 APR ranking reports"


@dataclass(frozen=True)
class AprSource:
    key: str
    label: str
    landing_url: str
    record_type: str


SOURCES: tuple[AprSource, ...] = (
    AprSource(
        "lea_rankings",
        "2025 Ranking for APR - LEAs",
        "https://dese.mo.gov/media/pdf/2025-ranking-apr-leas",
        "lea",
    ),
    AprSource(
        "school_rankings",
        "2025 Ranking for APR - Schools Final",
        "https://dese.mo.gov/media/pdf/2025-ranking-apr-schools-final",
        "school",
    ),
)

LEA_LINE_PATTERN = re.compile(
    r"^(\d+)\s+(\d{6})\s+(.+?)\s+(PK-\d+|PK-12|K-\d+|K-12|\d+-\d+)\s+(\d+(?:\.\d+)?)%\s*$"
)
SCHOOL_LINE_PATTERN = re.compile(r"^(\d+)\s+(\d{6})\s+(.+?)\s+(\d{4})\s+(.+?)\s+(\d+(?:\.\d+)?)%\s*$")
DATA_SRC_PATTERN = re.compile(r"data-src=['\"]([^'\"]+\.pdf)['\"]", re.I)
DATE_PATTERN = re.compile(r"\b(\d{1,2}/\d{1,2}/(?:\d{2}|20\d{2}))\b")

GENERIC_QUERY_TOKENS = {
    "ABOUT",
    "ACCOUNTABILITY",
    "ANNUAL",
    "APR",
    "DATA",
    "DESE",
    "DISTRICT",
    "FOR",
    "INDEX",
    "INDEXED",
    "LEA",
    "LEAS",
    "LIST",
    "MISSOURI",
    "PERFORMANCE",
    "RANK",
    "RANKING",
    "REPORT",
    "SCHOOL",
    "SCHOOLS",
    "SCORE",
    "THE",
    "WHAT",
    "WHICH",
    "WHO",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def clean_text(value: Any) -> str:
    decoded = html.unescape(str(value or "")).replace("\xa0", " ")
    return re.sub(r"\s+", " ", decoded).strip()


def normalize_text(value: Any) -> str:
    cleaned = re.sub(r"[^A-Z0-9.-]+", " ", clean_text(value).upper())
    return re.sub(r"\s+", " ", cleaned).strip()


def query_tokens(value: Any) -> set[str]:
    return {
        token.strip(".,")
        for token in normalize_text(value).replace("-", " ").split()
        if len(token.strip(".,()")) > 2 and token.strip(".,()") not in GENERIC_QUERY_TOKENS
    }


def local_pdf_path(source: AprSource) -> Path:
    return RAW_DIR / f"{source.key}.pdf"


def report_date_iso(value: str | None) -> str | None:
    if not value:
        return None
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return value


def discover_pdf_url(source: AprSource, html_text: str) -> str:
    match = DATA_SRC_PATTERN.search(html_text)
    if match:
        return urljoin(source.landing_url, html.unescape(match.group(1)))
    return source.landing_url


def download_source(source: AprSource, session: requests.Session) -> tuple[bytes, str, bytes]:
    landing_response = session.get(source.landing_url, timeout=60)
    landing_response.raise_for_status()
    pdf_url = discover_pdf_url(source, landing_response.text)
    pdf_response = session.get(pdf_url, timeout=60)
    pdf_response.raise_for_status()
    return pdf_response.content, pdf_url, landing_response.content


def extract_pdf_lines(path: Path) -> list[str]:
    reader = PdfReader(str(path))
    lines: list[str] = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        for line in page_text.splitlines():
            cleaned = clean_text(line)
            if cleaned:
                lines.append(cleaned)
    return lines


def parse_records(source: AprSource, lines: list[str], pdf_url: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    report_date = report_date_iso(next((match.group(1) for line in lines if (match := DATE_PATTERN.search(line))), None))
    for line in lines:
        if source.record_type == "lea":
            match = LEA_LINE_PATTERN.match(line)
            if not match:
                continue
            rank, county_district_code, lea_name, grade_span, apr_score = match.groups()
            key = (source.record_type, county_district_code, lea_name, grade_span, apr_score)
            if key in seen:
                continue
            seen.add(key)
            records.append(
                {
                    "record_type": "lea",
                    "rank": int(rank),
                    "county_district_code": county_district_code,
                    "lea_name": lea_name,
                    "grade_span": grade_span,
                    "single_year_apr_percent_score": float(apr_score),
                    "report_year": 2025,
                    "report_date": report_date,
                    "source_label": source.label,
                    "source_landing_url": source.landing_url,
                    "source_pdf_url": pdf_url,
                }
            )
        else:
            match = SCHOOL_LINE_PATTERN.match(line)
            if not match:
                continue
            rank, county_district_code, lea_name, building_number, building_name, apr_score = match.groups()
            key = (source.record_type, county_district_code, building_number, building_name, apr_score)
            if key in seen:
                continue
            seen.add(key)
            records.append(
                {
                    "record_type": "school",
                    "rank": int(rank),
                    "county_district_code": county_district_code,
                    "lea_name": lea_name,
                    "building_number": building_number,
                    "building_name": building_name,
                    "single_year_apr_percent_score": float(apr_score),
                    "report_year": 2025,
                    "report_date": report_date,
                    "source_label": source.label,
                    "source_landing_url": source.landing_url,
                    "source_pdf_url": pdf_url,
                }
            )
    return records


def build_dese_apr_index(force: bool = False, delay_seconds: float = 0.03) -> dict[str, Any]:
    if INDEX_PATH.exists() and not force:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))

    session = requests.Session()
    session.headers.update({"User-Agent": "missouri-tiny-llm-case-study/1.0"})
    records: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []
    for source in SOURCES:
        content, pdf_url, landing_content = download_source(source, session)
        pdf_path = local_pdf_path(source)
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(content)
        landing_path = RAW_DIR / f"{source.key}_landing.html"
        landing_path.write_bytes(landing_content)
        source_records = parse_records(source, extract_pdf_lines(pdf_path), pdf_url)
        records.extend(source_records)
        files.append(
            {
                "key": source.key,
                "label": source.label,
                "landing_url": source.landing_url,
                "pdf_url": pdf_url,
                "local_file": str(pdf_path.relative_to(PROJECT_ROOT)),
                "bytes": len(content),
                "sha256": sha256_bytes(content),
                "record_type": source.record_type,
                "record_count": len(source_records),
            }
        )
        time.sleep(delay_seconds)

    lea_records = [record for record in records if record["record_type"] == "lea"]
    school_records = [record for record in records if record["record_type"] == "school"]
    payload = {
        "source": SOURCE_NAME,
        "generated_at_utc": utc_now(),
        "index_path": str(INDEX_PATH.relative_to(PROJECT_ROOT)),
        "report_year": 2025,
        "record_count": len(records),
        "lea_record_count": len(lea_records),
        "school_record_count": len(school_records),
        "files": files,
        "notes": [
            "This selected parser covers DESE 2025 APR lowest-5% ranking PDFs for LEAs and school buildings.",
            "It stores ranks, county-district codes, LEA/building names, grade span or building number, and single-year APR percent scores.",
            "It is not a full MCDS/accountability parser and does not compute APR scores.",
        ],
        "lowest_lea_score": min((record["single_year_apr_percent_score"] for record in lea_records), default=None),
        "lowest_school_score": min((record["single_year_apr_percent_score"] for record in school_records), default=None),
        "records": sorted(records, key=lambda item: (item["record_type"], item["rank"], item.get("lea_name", ""))),
    }
    write_json(INDEX_PATH, payload)
    write_json(REPORT_PATH, {key: value for key, value in payload.items() if key != "records"})
    return payload


def asks_for_summary(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["indexed", "coverage", "what data", "what apr", "summary", "available"])


def asks_for_lowest(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["lowest", "worst", "bottom", "lowest 5", "lowest five"])


def asks_for_highest(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["highest", "best", "top"]) and "lowest" not in lowered


def wants_lea(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["lea", "leas", "district", "districts", "school system"])


def wants_school(question: str) -> bool:
    lowered = question.lower()
    return any(
        term in lowered
        for term in ["building", "school building", "which school", "what school", "high", "elementary", "elem", "middle"]
    )


class DeseAprIndex:
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
                "kind": "DESE APR ranking lookup",
                "lookup_table": "dese_apr_index",
                "year": payload.get("report_year"),
                "year_range": None,
                "source_files": [
                    {
                        "category": file.get("record_type"),
                        "category_label": file.get("label"),
                        "file_name": file.get("pdf_url"),
                        "row_count": file.get("record_count"),
                        "bytes": file.get("bytes"),
                        "sha256": file.get("sha256"),
                    }
                    for file in payload.get("files", [])
                ],
                "source_file_count": len(payload.get("files", [])),
                "source_rows": payload.get("record_count"),
                "matched_rows": matched_rows,
            }
        ]

    def unavailable_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "The DESE APR ranking index has not been built yet. Run "
                "`python scripts/build_dese_apr_index.py --force` to index the selected public APR ranking PDFs."
            ),
            "retrieved_context_id": "dese_apr_index:missing",
            "retrieved_source": "dese_apr_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "The DESE APR route exists, but the local ignored index is missing.",
            "citations": [],
            "source_rows": [],
        }

    def summary_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        return {
            "question": question,
            "answer": (
                "The selected DESE APR exact lookup layer indexes the 2025 public APR lowest-5% ranking PDFs. "
                f"It contains {payload.get('lea_record_count', 0):,} LEA row(s) and {payload.get('school_record_count', 0):,} school-building row(s). "
                f"Lowest indexed LEA single-year APR score: {payload.get('lowest_lea_score')}%. "
                f"Lowest indexed school single-year APR score: {payload.get('lowest_school_score')}%. "
                "It can answer whether a listed LEA or school appears in the selected 2025 APR ranking reports, its rank, and its single-year APR percent score. "
                "It does not compute APR or cover every MCDS accountability value."
            ),
            "retrieved_context_id": "dese_apr_index:summary",
            "retrieved_source": "dese_apr_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local DESE APR ranking index.",
            "citations": self.citation(matched_rows=payload.get("record_count", 0)),
            "source_rows": [],
        }

    def filtered_records(self, question: str) -> list[dict[str, Any]]:
        records = self.records()
        if wants_lea(question) and not wants_school(question):
            records = [record for record in records if record["record_type"] == "lea"]
        elif wants_school(question) and not wants_lea(question):
            records = [record for record in records if record["record_type"] == "school"]

        code_matches = set(re.findall(r"\b\d{6}\b", question))
        building_matches = set(re.findall(r"\b\d{4}\b", question))
        if code_matches:
            records = [record for record in records if record.get("county_district_code") in code_matches]
        if building_matches and wants_school(question):
            records = [record for record in records if record.get("building_number") in building_matches]

        q_tokens = query_tokens(question)
        if q_tokens:
            scored: list[tuple[int, dict[str, Any]]] = []
            q_norm = normalize_text(question)
            for record in records:
                blob = " ".join(
                    str(record.get(key, ""))
                    for key in ["lea_name", "building_name", "county_district_code", "building_number", "grade_span"]
                )
                tokens = query_tokens(blob)
                score = len(q_tokens & tokens)
                for key in ["lea_name", "building_name"]:
                    value_norm = normalize_text(record.get(key, ""))
                    if value_norm and value_norm in q_norm:
                        score += 20
                if score:
                    scored.append((score, record))
            if scored:
                ranked = sorted(scored, key=lambda item: (-item[0], item[1]["record_type"], item[1]["rank"]))
                best = ranked[0][0]
                records = [record for score, record in ranked if score >= max(1, best - 1)]
        return records

    def ranked_answer(self, question: str, records: list[dict[str, Any]]) -> dict[str, Any]:
        if asks_for_highest(question):
            rows = sorted(records, key=lambda item: (-item["single_year_apr_percent_score"], item["rank"]))[:5]
            direction = "highest"
        else:
            rows = sorted(records, key=lambda item: (item["single_year_apr_percent_score"], -item["rank"]))[:5]
            direction = "lowest"
        rendered = "; ".join(self.render_row(row) for row in rows)
        return {
            "question": question,
            "answer": f"The {direction} indexed DESE APR row(s) in the selected 2025 lowest-5% reports are: {rendered}.",
            "retrieved_context_id": "dese_apr_index:ranked",
            "retrieved_source": "dese_apr_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local DESE APR ranking index.",
            "citations": self.citation(matched_rows=len(rows)),
            "source_rows": [{"source_file": row["source_pdf_url"], "values": row} for row in rows[:5]],
        }

    def render_row(self, row: dict[str, Any]) -> str:
        score = f"{row['single_year_apr_percent_score']:.1f}%"
        if row["record_type"] == "lea":
            return (
                f"{row['lea_name']} ({row['county_district_code']}, {row['grade_span']}) "
                f"rank {row['rank']} with single-year APR score {score}"
            )
        return (
            f"{row['building_name']} ({row['lea_name']} {row['county_district_code']}, building {row['building_number']}) "
            f"rank {row['rank']} with single-year APR score {score}"
        )

    def rows_answer(self, question: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
        if not rows:
            return self.missing_answer(question)
        if asks_for_lowest(question) or asks_for_highest(question):
            return self.ranked_answer(question, rows)
        preview = sorted(rows, key=lambda item: (item["record_type"], item["rank"]))[:10]
        rendered = "; ".join(self.render_row(row) for row in preview)
        return {
            "question": question,
            "answer": (
                f"Showing {len(preview)} of {len(rows)} matching DESE 2025 APR ranking row(s): {rendered}. "
                "These rows come from the selected public lowest-5% APR ranking PDFs."
            ),
            "retrieved_context_id": "dese_apr_index:match",
            "retrieved_source": "dese_apr_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local DESE APR ranking index.",
            "citations": self.citation(matched_rows=len(rows)),
            "source_rows": [{"source_file": row["source_pdf_url"], "values": row} for row in preview[:5]],
        }

    def missing_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "I have indexed the selected DESE 2025 APR lowest-5% ranking PDFs, but this question did not match a listed LEA or school. "
                "Try `What DESE APR data is indexed?`, `Which school had the lowest APR score in 2025?`, "
                "`What is the APR ranking for Normandy High?`, or `What is the APR score for Atlas Public Schools?`."
            ),
            "retrieved_context_id": "dese_apr_index:no_match",
            "retrieved_source": "dese_apr_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Answered from DESE APR ranking coverage metadata because no exact row matched.",
            "citations": self.citation(),
            "source_rows": [],
        }

    def answer(self, question: str) -> dict[str, Any] | None:
        if not self.available():
            return self.unavailable_answer(question)
        if asks_for_summary(question):
            return self.summary_answer(question)
        rows = self.filtered_records(question)
        if rows:
            return self.rows_answer(question, rows)
        if asks_for_lowest(question) or asks_for_highest(question):
            return self.ranked_answer(question, self.records())
        return self.missing_answer(question)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--delay-seconds", type=float, default=0.03)
    args = parser.parse_args()
    payload = build_dese_apr_index(force=args.force, delay_seconds=args.delay_seconds)
    print(json.dumps({key: value for key, value in payload.items() if key != "records"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
