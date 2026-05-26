"""Build and query selected DESE school-finance transfer reports."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from pypdf import PdfReader


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw_public" / "dese_finance"
INDEX_PATH = RAW_DIR / "dese_finance_index.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "dese_finance_index_report.json"
SOURCE_NAME = "DESE School Finance transfer reports"


@dataclass(frozen=True)
class FinanceSource:
    key: str
    label: str
    landing_url: str
    report_type: str
    year_label: str = "2025-2026"


SOURCES: tuple[FinanceSource, ...] = (
    FinanceSource(
        "seven_percent_transfer",
        "2025-2026 $162,326 or 7%",
        "https://dese.mo.gov/media/pdf/2025-2026-162326-or-7-final",
        "seven_percent",
    ),
    FinanceSource(
        "five_percent_transfer",
        "2025-2026 Fiscal Year - 2005-2006 Designated Levy or 5%",
        "https://dese.mo.gov/media/pdf/2025-2026-fiscal-year-2005-2006-designated-levy-or-5-final",
        "five_percent",
    ),
    FinanceSource(
        "transportation_transfer",
        "2025-2026 Transportation Transfer",
        "https://dese.mo.gov/media/pdf/2020-2021-transportation-transfer-preliminary",
        "transportation",
    ),
)

PDF_LINK_RE = re.compile(r"(?:href|data-src)=['\"]([^'\"]+\.pdf)['\"]", re.I)
TRANSFER_LINE_RE = re.compile(
    r"^(\d{3}-\d{3})\s+(.+?)\s+([\d,]+\.\d{4}|#N/A)\s+([\d,]+|#N/A)\s+([\d,]+)$"
)
TRANSPORT_AMOUNT_RE = re.compile(r"\$[\d,]+\.\d{2}")
GENERIC_DISTRICT_WORDS = {
    "AMOUNT",
    "DESE",
    "DISTRICT",
    "FINANCE",
    "FUND",
    "FUNDS",
    "GENERAL",
    "HIGHEST",
    "LARGEST",
    "MAXIMUM",
    "MISSOURI",
    "SCHOOL",
    "THE",
    "TRANSFER",
    "TRANSPORTATION",
    "WHAT",
    "WHICH",
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
    cleaned = re.sub(r"[^A-Z0-9]+", " ", clean_text(value).upper())
    return re.sub(r"\s+", " ", cleaned).strip()


def query_tokens(value: Any) -> set[str]:
    return {
        token
        for token in normalize_text(value).split()
        if len(token) > 1 and token not in GENERIC_DISTRICT_WORDS
    }


def parse_int(value: str | None) -> int | None:
    if not value or value == "#N/A":
        return None
    cleaned = value.replace(",", "").strip()
    return int(cleaned) if cleaned.isdigit() else None


def parse_float(value: str | None) -> float | None:
    if not value or value == "#N/A":
        return None
    return float(value.replace(",", "").strip())


def parse_money(value: str) -> int:
    return int(Decimal(value.replace("$", "").replace(",", "")))


def format_amount(value: int | None) -> str:
    return "not listed" if value is None else f"${value:,.0f}"


def local_pdf_path(source: FinanceSource) -> Path:
    return RAW_DIR / f"{source.key}.pdf"


def discover_pdf_url(source: FinanceSource, landing_html: str) -> str:
    match = PDF_LINK_RE.search(landing_html)
    if match:
        return urljoin(source.landing_url, html.unescape(match.group(1)))
    return source.landing_url


def download_source(source: FinanceSource, session: requests.Session) -> tuple[bytes, str, bytes]:
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


def base_record(source: FinanceSource, pdf_url: str, code: str, name: str) -> dict[str, Any]:
    district_name = clean_text(name)
    return {
        "report_key": source.key,
        "report_type": source.report_type,
        "report_label": source.label,
        "report_year": source.year_label,
        "county_district_code": code,
        "district_name": district_name,
        "district_name_norm": normalize_text(district_name),
        "source_landing_url": source.landing_url,
        "source_pdf_url": pdf_url,
    }


def parse_records(source: FinanceSource, lines: list[str], pdf_url: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in lines:
        if not re.match(r"^\d{3}-\d{3}\s+", line):
            continue
        if source.report_type in {"seven_percent", "five_percent"}:
            match = TRANSFER_LINE_RE.match(line)
            if not match:
                continue
            code, name, combined_wada, calculated, maximum = match.groups()
            row = base_record(source, pdf_url, code, name)
            row.update(
                {
                    "combined_wm_wada": parse_float(combined_wada),
                    "calculated_transfer_amount": parse_int(calculated),
                    "maximum_transfer_amount": parse_int(maximum),
                    "amount_field": "maximum_transfer_amount",
                    "amount_label": "maximum transfer amount",
                    "amount": parse_int(maximum),
                }
            )
            records.append(row)
            continue

        amounts = TRANSPORT_AMOUNT_RE.findall(line)
        if len(amounts) != 10:
            continue
        prefix = line.split(amounts[0], 1)[0].strip()
        code, name = prefix[:7], prefix[8:].strip()
        values = [parse_money(amount) for amount in amounts]
        row = base_record(source, pdf_url, code, name)
        row.update(
            {
                "account_2551": values[0],
                "account_2552": values[1],
                "account_2553": values[2],
                "account_2554": values[3],
                "part_iii_c_sum": values[4],
                "iii_b_6500_6552_coded": values[5],
                "bus_depreciation": values[6],
                "facility_depreciation": values[7],
                "major_tool": values[8],
                "transfer_amount": values[9],
                "amount_field": "transfer_amount",
                "amount_label": "transportation transfer amount",
                "amount": values[9],
            }
        )
        records.append(row)
    return records


def top_rows(records: list[dict[str, Any]], report_type: str, limit: int = 5) -> list[dict[str, Any]]:
    rows = [record for record in records if record.get("report_type") == report_type and record.get("amount") is not None]
    return sorted(rows, key=lambda item: (-int(item["amount"]), item["district_name"]))[:limit]


def build_dese_finance_index(force: bool = False, delay_seconds: float = 0.03) -> dict[str, Any]:
    if INDEX_PATH.exists() and not force:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (compatible; MissouriPublicDataAssistant/1.0)",
            "Accept": "application/pdf,text/html,*/*;q=0.8",
        }
    )
    start = time.perf_counter()
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
                "report_type": source.report_type,
                "landing_url": source.landing_url,
                "pdf_url": pdf_url,
                "local_file": str(pdf_path.relative_to(PROJECT_ROOT)),
                "bytes": len(content),
                "sha256": sha256_bytes(content),
                "record_count": len(source_records),
            }
        )
        time.sleep(delay_seconds)

    report_summaries = []
    for source in SOURCES:
        rows = [record for record in records if record["report_key"] == source.key]
        report_summaries.append(
            {
                "key": source.key,
                "label": source.label,
                "report_type": source.report_type,
                "record_count": len(rows),
                "total_amount": sum(int(row.get("amount") or 0) for row in rows),
                "top_amounts": [
                    {
                        "district_name": row["district_name"],
                        "county_district_code": row["county_district_code"],
                        "amount": row["amount"],
                    }
                    for row in top_rows(records, source.report_type, limit=5)
                ],
            }
        )

    payload = {
        "source": SOURCE_NAME,
        "generated_at_utc": utc_now(),
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "index_path": str(INDEX_PATH.relative_to(PROJECT_ROOT)),
        "report_year": "2025-2026",
        "report_count": len(SOURCES),
        "record_count": len(records),
        "files": files,
        "report_summaries": report_summaries,
        "notes": [
            "This selected parser covers three public DESE school-finance transfer PDFs.",
            "It parses district-level maximum transfer amounts for 7%, 5%, and transportation transfer reports.",
            "It does not parse every DESE finance table, MCDS dashboard value, audit, payment, or district budget document.",
        ],
        "records": sorted(records, key=lambda item: (item["report_key"], item["district_name_norm"])),
    }
    write_json(INDEX_PATH, payload)
    write_json(REPORT_PATH, {key: value for key, value in payload.items() if key != "records"})
    return payload


def asks_for_summary(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["indexed", "coverage", "what data", "available", "summary", "what finance"])


def asks_for_top(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["highest", "largest", "top", "most"])


def report_type_from_question(question: str) -> str | None:
    lowered = question.lower()
    if "transportation transfer" in lowered or "bus depreciation" in lowered or "facility depreciation" in lowered:
        return "transportation"
    if "7%" in lowered or "7 percent" in lowered or "162,326" in lowered or "162326" in lowered:
        return "seven_percent"
    if "5%" in lowered or "5 percent" in lowered or "designated levy" in lowered:
        return "five_percent"
    return None


def report_label(report_type: str) -> str:
    return {
        "seven_percent": "7% transfer",
        "five_percent": "5% transfer",
        "transportation": "transportation transfer",
    }.get(report_type, report_type)


class DeseFinanceIndex:
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

    def citation(self, matched_rows: int = 0, report_types: set[str] | None = None) -> list[dict[str, Any]]:
        payload = self.payload()
        files = [
            file
            for file in payload.get("files", [])
            if report_types is None or file.get("report_type") in report_types
        ]
        return [
            {
                "dataset": payload.get("source", SOURCE_NAME),
                "category": "Education finance",
                "kind": "DESE school-finance transfer lookup",
                "lookup_table": "dese_finance_index",
                "year": payload.get("report_year"),
                "year_range": None,
                "source_files": [
                    {
                        "category": file.get("report_type"),
                        "category_label": file.get("label"),
                        "file_name": file.get("pdf_url"),
                        "source_url": file.get("pdf_url"),
                        "row_count": file.get("record_count"),
                        "bytes": file.get("bytes"),
                        "sha256": file.get("sha256"),
                    }
                    for file in files
                ],
                "source_file_count": len(files),
                "source_rows": payload.get("record_count"),
                "matched_rows": matched_rows,
            }
        ]

    def unavailable_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "The DESE school-finance transfer index has not been built yet. Run "
                "`python scripts/build_dese_finance_index.py --force` to index the selected public transfer PDFs."
            ),
            "retrieved_context_id": "dese_finance_index:missing",
            "retrieved_source": "dese_finance_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "The DESE finance route exists, but the local ignored index is missing.",
            "citations": [],
            "source_rows": [],
        }

    def summary_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        summary_text = "; ".join(
            f"{item['label']}: {item['record_count']:,} district row(s)"
            for item in payload.get("report_summaries", [])
        )
        return {
            "question": question,
            "answer": (
                "The selected DESE school-finance exact lookup layer indexes three public 2025-2026 transfer reports. "
                f"It contains {payload.get('record_count', 0):,} district report row(s): {summary_text}. "
                "It can answer district-level 7%, 5%, and transportation transfer amounts and largest-transfer rankings. "
                "It is not a full MCDS finance parser."
            ),
            "retrieved_context_id": "dese_finance_index:summary",
            "retrieved_source": "dese_finance_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local DESE school-finance transfer index.",
            "citations": self.citation(matched_rows=payload.get("record_count", 0)),
            "source_rows": [],
        }

    def matching_district_records(self, question: str) -> list[dict[str, Any]]:
        q_norm = normalize_text(question)
        q_tokens = query_tokens(question)
        scored: list[tuple[int, dict[str, Any]]] = []
        for record in self.records():
            score = 0
            if record["county_district_code"] in question:
                score += 50
            if record["district_name_norm"] and record["district_name_norm"] in q_norm:
                score += 40
            overlap = q_tokens & query_tokens(record["district_name"])
            score += len(overlap) * 5
            if score:
                scored.append((score, record))
        if not scored:
            return []
        best = max(score for score, _ in scored)
        return [record for score, record in scored if score >= max(5, best - 5)]

    def top_answer(self, question: str, report_type: str) -> dict[str, Any]:
        rows = top_rows(self.records(), report_type, limit=5)
        rendered = "; ".join(
            f"{index}. {row['district_name']} ({row['county_district_code']}): {format_amount(row.get('amount'))}"
            for index, row in enumerate(rows, start=1)
        )
        return {
            "question": question,
            "answer": f"The largest indexed DESE {report_label(report_type)} amounts are: {rendered}.",
            "retrieved_context_id": f"dese_finance_index:top:{report_type}",
            "retrieved_source": "dese_finance_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed by ranking district rows in the local DESE school-finance transfer index.",
            "citations": self.citation(matched_rows=len(rows), report_types={report_type}),
            "source_rows": [{"source_file": row["source_pdf_url"], "values": row} for row in rows],
        }

    def district_answer(self, question: str, rows: list[dict[str, Any]], wanted_report: str | None) -> dict[str, Any]:
        if wanted_report:
            rows = [row for row in rows if row["report_type"] == wanted_report]
        if not rows:
            return self.missing_answer(question)
        rows = sorted(rows, key=lambda item: (item["district_name"], item["report_type"]))
        preview = rows[:5]
        rendered = "; ".join(
            f"{row['district_name']} ({row['county_district_code']}) {report_label(row['report_type'])}: "
            f"{format_amount(row.get('amount'))}"
            for row in preview
        )
        return {
            "question": question,
            "answer": (
                f"Showing {len(preview)} matching DESE school-finance transfer row(s): {rendered}. "
                "Amounts are district-level values from the selected 2025-2026 DESE transfer PDFs."
            ),
            "retrieved_context_id": "dese_finance_index:district_match",
            "retrieved_source": "dese_finance_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local DESE school-finance transfer index.",
            "citations": self.citation(matched_rows=len(rows), report_types={row["report_type"] for row in rows}),
            "source_rows": [{"source_file": row["source_pdf_url"], "values": row} for row in preview],
        }

    def missing_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "I have indexed selected DESE school-finance transfer rows, but this question did not match a supported district or report. "
                "Try `What DESE school finance transfer data is indexed?`, `What is Columbia 93's DESE 7% transfer amount?`, "
                "`What is Columbia 93's DESE transportation transfer amount?`, or `Which district has the highest DESE 7% transfer amount?`."
            ),
            "retrieved_context_id": "dese_finance_index:no_match",
            "retrieved_source": "dese_finance_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Answered from DESE school-finance transfer coverage metadata because no exact row matched.",
            "citations": self.citation(),
            "source_rows": [],
        }

    def answer(self, question: str) -> dict[str, Any] | None:
        if not self.available():
            return self.unavailable_answer(question)
        wanted_report = report_type_from_question(question)
        if asks_for_summary(question):
            return self.summary_answer(question)
        if asks_for_top(question):
            return self.top_answer(question, wanted_report or "seven_percent")
        rows = self.matching_district_records(question)
        if rows:
            return self.district_answer(question, rows, wanted_report)
        return self.missing_answer(question)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--delay-seconds", type=float, default=0.03)
    args = parser.parse_args()
    payload = build_dese_finance_index(force=args.force, delay_seconds=args.delay_seconds)
    print(json.dumps({key: value for key, value in payload.items() if key != "records"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
