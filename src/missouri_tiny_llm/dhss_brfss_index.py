"""Build and query selected DHSS BRFSS aggregate prevalence data."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import openpyxl
import requests


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw_public" / "dhss_brfss"
INDEX_PATH = RAW_DIR / "dhss_brfss_index.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "dhss_brfss_index_report.json"
LANDING_PAGE = "https://health.mo.gov/data/brfss/index.php"
XLSX_URL = "https://health.mo.gov/data/brfss/libs/Maindowna.xlsx"
SOURCE_NAME = "DHSS Behavioral Risk Factor Surveillance System (BRFSS)"

GENERIC_TOKENS = {
    "ADULT",
    "ADULTS",
    "AGE",
    "AGES",
    "AND",
    "BEHAVIORAL",
    "BRFSS",
    "DATA",
    "DHSS",
    "FACTOR",
    "FOR",
    "HEALTH",
    "INDEXED",
    "MISSOURI",
    "PERCENT",
    "PREVALENCE",
    "RATE",
    "RISK",
    "SYSTEM",
    "WHAT",
    "WITH",
    "YEAR",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_text(value: Any) -> str:
    cleaned = re.sub(r"[^A-Z0-9]+", " ", clean_text(value).upper())
    return re.sub(r"\s+", " ", cleaned).strip()


def indicator_tokens(value: Any) -> set[str]:
    return {
        token
        for token in normalize_text(value).split()
        if len(token) > 2 and token not in GENERIC_TOKENS
    }


def parse_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return None


def parse_year(value: Any) -> int | None:
    number = parse_float(value)
    if number is None:
        return None
    year = int(number)
    return year if 1900 <= year <= 2100 else None


def section_label(value: str) -> str:
    lowered = value.lower()
    if "health conditions" in lowered:
        return "health conditions"
    if "risk factors" in lowered:
        return "health risk factors"
    if "preventive practices" in lowered:
        return "preventive practices"
    return clean_text(value)


def safe_record_id(indicator: str, year: int) -> str:
    return hashlib.sha1(f"{indicator}:{year}".encode("utf-8")).hexdigest()[:16]


def download_sources(force: bool = False) -> tuple[bytes, str, dict[str, Any]]:
    xlsx_path = RAW_DIR / "Maindowna.xlsx"
    page_path = RAW_DIR / "brfss_index.html"
    session = requests.Session()
    session.headers.update({"User-Agent": "missouri-tiny-llm-case-study/1.0"})
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    if force or not xlsx_path.exists():
        xlsx_response = session.get(XLSX_URL, timeout=60)
        xlsx_response.raise_for_status()
        xlsx_path.write_bytes(xlsx_response.content)
    xlsx_bytes = xlsx_path.read_bytes()

    if force or not page_path.exists():
        page_response = session.get(LANDING_PAGE, timeout=60)
        page_response.raise_for_status()
        page_path.write_text(page_response.text, encoding="utf-8")
    page_text = page_path.read_text(encoding="utf-8", errors="replace")

    files = {
        "landing_page": {
            "url": LANDING_PAGE,
            "local_file": str(page_path.relative_to(PROJECT_ROOT)),
            "bytes": len(page_text.encode("utf-8", errors="replace")),
            "sha256": hashlib.sha256(page_text.encode("utf-8", errors="replace")).hexdigest(),
        },
        "workbook": {
            "url": XLSX_URL,
            "local_file": str(xlsx_path.relative_to(PROJECT_ROOT)),
            "bytes": len(xlsx_bytes),
            "sha256": sha256_bytes(xlsx_bytes),
        },
    }
    return xlsx_bytes, page_text, files


def parse_workbook(xlsx_path: Path) -> list[dict[str, Any]]:
    workbook = openpyxl.load_workbook(xlsx_path, data_only=True, read_only=True)
    worksheet = workbook.active
    records: list[dict[str, Any]] = []
    section = ""
    category = ""
    for row in worksheet.iter_rows(values_only=True):
        first = clean_text(row[0] if row else "")
        second = clean_text(row[1] if len(row) > 1 else "")
        third = clean_text(row[2] if len(row) > 2 else "")
        year = parse_year(row[1] if len(row) > 1 else None)
        prevalence = parse_float(row[2] if len(row) > 2 else None)
        lower_ci = parse_float(row[3] if len(row) > 3 else None)
        upper_ci = parse_float(row[4] if len(row) > 4 else None)

        if first.startswith("Percent of Missouri adults"):
            section = section_label(first)
            category = section
            continue
        if second == "Data" and third == "Prevalence":
            if first:
                category = first
            continue
        if not first or year is None or prevalence is None:
            continue
        records.append(
            {
                "record_id": safe_record_id(first, year),
                "indicator": first,
                "indicator_norm": normalize_text(first),
                "section": section or category,
                "category": category or section,
                "data_year": year,
                "prevalence_percent": prevalence,
                "lower_ci": lower_ci,
                "upper_ci": upper_ci,
                "source_url": XLSX_URL,
                "landing_page": LANDING_PAGE,
            }
        )
    return records


def build_dhss_brfss_index(force: bool = False) -> dict[str, Any]:
    if INDEX_PATH.exists() and not force:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))

    start = time.perf_counter()
    _, _, files = download_sources(force=force)
    records = parse_workbook(RAW_DIR / "Maindowna.xlsx")
    years = sorted({record["data_year"] for record in records})
    sections = sorted({record["section"] for record in records if record["section"]})
    top_prevalence = sorted(records, key=lambda item: item["prevalence_percent"], reverse=True)[:8]
    payload = {
        "generated_at_utc": utc_now(),
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "source": SOURCE_NAME,
        "landing_page": LANDING_PAGE,
        "workbook_url": XLSX_URL,
        "index_path": str(INDEX_PATH.relative_to(PROJECT_ROOT)),
        "record_count": len(records),
        "years": years,
        "sections": sections,
        "files": files,
        "notes": [
            "This index parses the official DHSS BRFSS front-page workbook of statewide aggregate prevalence percentages.",
            "It stores indicator, data year, prevalence percent, and confidence interval bounds.",
            "It does not parse respondent-level survey data, county-level BRFSS values, or MOPHIMS/MICA query results.",
        ],
        "records": records,
    }
    write_json(INDEX_PATH, payload)
    write_json(
        REPORT_PATH,
        {
            key: value
            for key, value in payload.items()
            if key != "records"
        }
        | {
            "top_prevalence": [
                {
                    "indicator": record["indicator"],
                    "data_year": record["data_year"],
                    "prevalence_percent": record["prevalence_percent"],
                    "lower_ci": record["lower_ci"],
                    "upper_ci": record["upper_ci"],
                }
                for record in top_prevalence
            ]
        },
    )
    return payload


def format_percent(value: float | None) -> str:
    if value is None:
        return "not listed"
    return f"{value:.1f}%"


def asks_for_summary(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["indexed", "coverage", "what data", "summary", "available"])


def asks_for_top(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["highest", "largest", "top", "most prevalent"])


def asks_for_lowest(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["lowest", "smallest", "least prevalent"])


class DhssBrfssIndex:
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
        files = payload.get("files", {})
        return [
            {
                "dataset": payload.get("source", SOURCE_NAME),
                "category": "Public health",
                "kind": "DHSS BRFSS aggregate prevalence lookup",
                "lookup_table": "dhss_brfss_index",
                "year": None,
                "year_range": (
                    f"{min(payload.get('years', []))}-{max(payload.get('years', []))}"
                    if payload.get("years")
                    else None
                ),
                "source_files": [
                    {
                        "category": key,
                        "category_label": key.replace("_", " ").title(),
                        "file_name": value.get("url"),
                        "row_count": payload.get("record_count") if key == "workbook" else None,
                        "bytes": value.get("bytes"),
                        "sha256": value.get("sha256"),
                    }
                    for key, value in files.items()
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
                "The DHSS BRFSS aggregate index has not been built yet. Run "
                "`python scripts/build_dhss_brfss_index.py --force` to index the official BRFSS workbook."
            ),
            "retrieved_context_id": "dhss_brfss_index:missing",
            "retrieved_source": "dhss_brfss_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "citations": [],
            "source_rows": [],
        }

    def summary_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        years = payload.get("years", [])
        year_text = f"{min(years)}-{max(years)}" if years else "the indexed workbook years"
        sections = ", ".join(payload.get("sections", []))
        return {
            "question": question,
            "answer": (
                f"The DHSS BRFSS exact aggregate layer indexes {payload.get('record_count', 0)} statewide prevalence indicator(s) "
                f"from the official BRFSS front-page workbook for {year_text}. Sections: {sections}. "
                "It returns prevalence percent and confidence interval bounds. It does not parse respondent-level data, "
                "county-level BRFSS values, or MOPHIMS/MICA query results."
            ),
            "retrieved_context_id": "dhss_brfss_index:summary",
            "retrieved_source": "dhss_brfss_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local DHSS BRFSS aggregate workbook index.",
            "citations": self.citation(matched_rows=payload.get("record_count", 0)),
            "source_rows": [],
        }

    def find_indicator(self, question: str) -> dict[str, Any] | None:
        tokens = indicator_tokens(question)
        if not tokens:
            return None
        ranked: list[tuple[int, dict[str, Any]]] = []
        question_norm = normalize_text(question)
        for record in self.records():
            record_tokens = indicator_tokens(record["indicator"])
            score = len(tokens & record_tokens)
            if record["indicator_norm"] and record["indicator_norm"] in question_norm:
                score += 10
            if score:
                ranked.append((score, record))
        if not ranked:
            return None
        ranked.sort(key=lambda item: (-item[0], item[1]["indicator"]))
        return ranked[0][1]

    def indicator_answer(self, question: str, record: dict[str, Any]) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                f"The DHSS BRFSS workbook lists {record['indicator']} at {format_percent(record['prevalence_percent'])} "
                f"for data year {record['data_year']} among Missouri adults. "
                f"Confidence interval: {format_percent(record.get('lower_ci'))} to {format_percent(record.get('upper_ci'))}. "
                "This is a statewide aggregate prevalence estimate, not medical advice."
            ),
            "retrieved_context_id": f"dhss_brfss_index:{record['record_id']}",
            "retrieved_source": "dhss_brfss_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local DHSS BRFSS aggregate workbook index.",
            "citations": self.citation(matched_rows=1),
            "source_rows": [{"source_file": record["source_url"], "values": record}],
        }

    def ranking_answer(self, question: str, reverse: bool) -> dict[str, Any]:
        rows = sorted(self.records(), key=lambda item: item["prevalence_percent"], reverse=reverse)[:5]
        label = "highest" if reverse else "lowest"
        rendered = "; ".join(
            f"{index}. {row['indicator']} ({row['data_year']}): {format_percent(row['prevalence_percent'])}"
            for index, row in enumerate(rows, start=1)
        )
        return {
            "question": question,
            "answer": f"The {label} DHSS BRFSS prevalence indicators in the indexed workbook are: {rendered}.",
            "retrieved_context_id": f"dhss_brfss_index:{label}",
            "retrieved_source": "dhss_brfss_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local DHSS BRFSS aggregate workbook index.",
            "citations": self.citation(matched_rows=len(rows)),
            "source_rows": [{"source_file": row["source_url"], "values": row} for row in rows],
        }

    def missing_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "I could not match that question to a BRFSS indicator in the indexed DHSS workbook. "
                "Try asking about obesity, diabetes, current asthma, current cigarette smoking, no health care coverage, "
                "binge drinking, influenza vaccination, mammogram screening, or dentist visits."
            ),
            "retrieved_context_id": "dhss_brfss_index:no_match",
            "retrieved_source": "dhss_brfss_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "No indicator matched the local DHSS BRFSS aggregate workbook index.",
            "citations": self.citation(matched_rows=0),
            "source_rows": [],
        }

    def answer(self, question: str) -> dict[str, Any] | None:
        if not self.available():
            return self.unavailable_answer(question)
        if asks_for_summary(question):
            return self.summary_answer(question)
        if asks_for_top(question):
            return self.ranking_answer(question, reverse=True)
        if asks_for_lowest(question):
            return self.ranking_answer(question, reverse=False)
        record = self.find_indicator(question)
        if record is not None:
            return self.indicator_answer(question, record)
        return self.missing_answer(question)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    payload = build_dhss_brfss_index(force=args.force)
    print(json.dumps({key: value for key, value in payload.items() if key != "records"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
