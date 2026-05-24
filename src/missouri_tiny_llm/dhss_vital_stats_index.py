"""Build and query selected DHSS statewide vital-statistics aggregates."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from pypdf import PdfReader


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw_public" / "dhss_vital_stats"
INDEX_PATH = RAW_DIR / "dhss_vital_stats_index.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "dhss_vital_stats_index_report.json"
FOCUS_PAGE = "https://health.mo.gov/data/focus/"
SOURCE_NAME = "DHSS Vital Statistics Focus Report"

MEASURE_ALIASES = {
    "births": ["birth", "births", "live birth", "live births", "infants born"],
    "deaths": ["death", "deaths", "resident deaths"],
    "natural increase": ["natural increase", "births outnumbered deaths"],
    "infant deaths": ["infant death", "infant deaths", "infant mortality"],
    "marriages": ["marriage", "marriages"],
    "divorces": ["divorce", "divorces"],
    "population": ["population"],
}

TABLE_1_MEASURES = tuple(MEASURE_ALIASES.keys())


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def parse_number(value: str) -> float | None:
    cleaned = value.replace(",", "").replace("*", "").strip()
    if re.fullmatch(r"-?\d+(?:\.\d+)?", cleaned):
        return float(cleaned)
    return None


def format_count(value: float | int | None) -> str:
    if value is None:
        return "not listed"
    return f"{int(value):,}" if float(value).is_integer() else f"{float(value):,.1f}"


def format_rate(value: float | int | None) -> str:
    if value is None:
        return "not listed"
    return f"{float(value):.1f}"


def safe_record_id(measure: str, year: int) -> str:
    return hashlib.sha1(f"{measure}:{year}".encode("utf-8")).hexdigest()[:16]


def download_text(url: str, path: Path, force: bool = False) -> str:
    session = requests.Session()
    session.headers.update({"User-Agent": "missouri-tiny-llm-case-study/1.0"})
    if force or not path.exists():
        response = session.get(url, timeout=60)
        response.raise_for_status()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(response.text, encoding="utf-8")
    return path.read_text(encoding="utf-8", errors="replace")


def download_bytes(url: str, path: Path, force: bool = False) -> bytes:
    session = requests.Session()
    session.headers.update({"User-Agent": "missouri-tiny-llm-case-study/1.0"})
    if force or not path.exists():
        response = session.get(url, timeout=90)
        response.raise_for_status()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(response.content)
    return path.read_bytes()


def discover_latest_vital_pdf(page_html: str) -> tuple[int, str, str]:
    candidates: list[tuple[int, str, str]] = []
    for match in re.finditer(
        r'href="(?P<href>[^"]+\.pdf)"[^>]*>\s*(?P<label>(?P<year>20\d{2})\s+Vital Statistics)',
        page_html,
        flags=re.IGNORECASE,
    ):
        year = int(match.group("year"))
        url = urljoin(FOCUS_PAGE, match.group("href"))
        candidates.append((year, match.group("label"), url))
    if not candidates:
        raise ValueError("Could not find a Vital Statistics PDF link on the DHSS FOCUS page")
    return sorted(candidates, key=lambda item: item[0], reverse=True)[0]


def extract_pdf_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def years_from_table_header(text: str, report_year: int) -> list[int]:
    match = re.search(r"Numbers Rates per 1,000 Population\s+((?:\d{4}\s+){5}\d{4})", text)
    if not match:
        return [report_year - 10, report_year - 1, report_year]
    header_years = [int(value) for value in re.findall(r"\d{4}", match.group(1))]
    return header_years[:3] if len(header_years) >= 3 else [report_year - 10, report_year - 1, report_year]


def parse_table_1(text: str, report_year: int, pdf_url: str) -> list[dict[str, Any]]:
    table_text = text.split("continued on page 2", 1)[0]
    years = years_from_table_header(table_text, report_year)
    records: list[dict[str, Any]] = []
    row_pattern = re.compile(
        r"^(Births|Deaths|Natural increase|Marriages|Divorces|Infant deaths|Population \(1,000s\))\s+(.+)$",
        re.MULTILINE,
    )
    for match in row_pattern.finditer(table_text):
        label = match.group(1)
        measure = "population" if label.startswith("Population") else label.lower()
        values = re.findall(r"-?\d[\d,]*(?:\.\d+)?\*?", match.group(2))
        counts = [parse_number(value) for value in values[:3]]
        rates = [parse_number(value) for value in values[3:6]]
        for index, year in enumerate(years):
            count = counts[index] if index < len(counts) else None
            rate = rates[index] if index < len(rates) else None
            if count is None:
                continue
            rate_unit = None
            if measure == "infant deaths":
                rate_unit = "per 1,000 live births"
            elif measure != "population":
                rate_unit = "per 1,000 population"
            records.append(
                {
                    "record_id": safe_record_id(measure, year),
                    "measure": measure,
                    "year": year,
                    "count": count,
                    "rate": rate,
                    "rate_unit": rate_unit,
                    "source_url": pdf_url,
                    "source_table": "Table 1: Vital Statistics for Missouri",
                }
            )
    return records


def build_dhss_vital_stats_index(force: bool = False) -> dict[str, Any]:
    if INDEX_PATH.exists() and not force:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))

    start = time.perf_counter()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    page_path = RAW_DIR / "focus.html"
    page_html = download_text(FOCUS_PAGE, page_path, force=force)
    report_year, label, pdf_url = discover_latest_vital_pdf(page_html)
    pdf_path = RAW_DIR / Path(pdf_url).name
    pdf_bytes = download_bytes(pdf_url, pdf_path, force=force)
    pdf_text = extract_pdf_text(pdf_path)
    records = parse_table_1(pdf_text, report_year, pdf_url)
    years = sorted({record["year"] for record in records})
    measures = sorted({record["measure"] for record in records})
    payload = {
        "generated_at_utc": utc_now(),
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "source": SOURCE_NAME,
        "focus_page": FOCUS_PAGE,
        "report_label": label,
        "report_year": report_year,
        "report_url": pdf_url,
        "index_path": str(INDEX_PATH.relative_to(PROJECT_ROOT)),
        "record_count": len(records),
        "years": years,
        "measures": measures,
        "files": {
            "focus_page": {
                "url": FOCUS_PAGE,
                "local_file": str(page_path.relative_to(PROJECT_ROOT)),
                "bytes": len(page_html.encode("utf-8", errors="replace")),
                "sha256": hashlib.sha256(page_html.encode("utf-8", errors="replace")).hexdigest(),
            },
            "report_pdf": {
                "url": pdf_url,
                "local_file": str(pdf_path.relative_to(PROJECT_ROOT)),
                "bytes": len(pdf_bytes),
                "sha256": sha256_bytes(pdf_bytes),
            },
        },
        "notes": [
            "This index parses Table 1 from the latest DHSS Vital Statistics FOCUS PDF found on the official FOCUS page.",
            "It stores statewide aggregate counts and rates for selected vital-statistics measures only.",
            "It does not parse county-level values, vital-record certificates, patient/person records, or MOPHIMS/MICA query results.",
        ],
        "records": records,
    }
    write_json(INDEX_PATH, payload)
    latest_year = max(years) if years else report_year
    write_json(
        REPORT_PATH,
        {
            key: value
            for key, value in payload.items()
            if key != "records"
        }
        | {
            "latest_year_records": [
                {
                    "measure": record["measure"],
                    "year": record["year"],
                    "count": record["count"],
                    "rate": record["rate"],
                    "rate_unit": record["rate_unit"],
                }
                for record in records
                if record["year"] == latest_year
            ]
        },
    )
    return payload


def asks_for_summary(question: str) -> bool:
    lowered = question.lower()
    if "focus report" in lowered or "focus reports" in lowered:
        return False
    return any(term in lowered for term in ["indexed", "coverage", "what data", "available", "summary"])


def asks_for_source(question: str) -> bool:
    lowered = question.lower()
    return "source" in lowered and any(term in lowered for term in ["aggregate", "index", "indexed"])


def asks_for_latest_year(question: str) -> bool:
    lowered = question.lower()
    return "latest" in lowered and "year" in lowered


class DhssVitalStatsIndex:
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
                "kind": "DHSS vital statistics aggregate lookup",
                "lookup_table": "dhss_vital_stats_index",
                "year": payload.get("report_year"),
                "year_range": (
                    ", ".join(str(year) for year in payload.get("years", []))
                    if payload.get("years")
                    else None
                ),
                "source_files": [
                    {
                        "category": key,
                        "category_label": key.replace("_", " ").title(),
                        "file_name": value.get("url"),
                        "row_count": payload.get("record_count") if key == "report_pdf" else None,
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
                "The DHSS vital-statistics aggregate index has not been built yet. Run "
                "`python scripts/build_dhss_vital_stats_index.py --force` to index the official FOCUS report."
            ),
            "retrieved_context_id": "dhss_vital_stats_index:missing",
            "retrieved_source": "dhss_vital_stats_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "citations": [],
            "source_rows": [],
        }

    def summary_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        measures = ", ".join(payload.get("measures", []))
        years = payload.get("years", [])
        year_text = ", ".join(str(year) for year in years) if years else "the indexed report years"
        return {
            "question": question,
            "answer": (
                f"The DHSS vital-statistics exact aggregate layer indexes {payload.get('record_count', 0)} statewide Table 1 row(s) "
                f"from the {payload.get('report_label')} FOCUS PDF for {year_text}. Measures: {measures}. "
                "It returns aggregate counts and rates only; it does not parse county-level values, vital-record certificates, "
                "person records, or MOPHIMS/MICA query results."
            ),
            "retrieved_context_id": "dhss_vital_stats_index:summary",
            "retrieved_source": "dhss_vital_stats_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local DHSS Vital Statistics FOCUS report index.",
            "citations": self.citation(matched_rows=payload.get("record_count", 0)),
            "source_rows": [],
        }

    def latest_year_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        latest_year = max(payload.get("years", []) or [payload.get("report_year")])
        return {
            "question": question,
            "answer": (
                f"The latest year parsed in the DHSS vital-statistics aggregate index is {latest_year}, "
                f"from the {payload.get('report_label')} FOCUS PDF."
            ),
            "retrieved_context_id": f"dhss_vital_stats_index:latest_year:{latest_year}",
            "retrieved_source": "dhss_vital_stats_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local DHSS Vital Statistics FOCUS report index.",
            "citations": self.citation(matched_rows=0),
            "source_rows": [],
        }

    def match_measure(self, question: str) -> str | None:
        lowered = question.lower()
        for measure, aliases in MEASURE_ALIASES.items():
            if any(alias in lowered for alias in aliases):
                return measure
        return None

    def requested_year(self, question: str) -> int | None:
        years = [int(match) for match in re.findall(r"\b(20\d{2}|19\d{2})\b", question)]
        return years[-1] if years else None

    def record_for(self, measure: str, year: int | None) -> dict[str, Any] | None:
        rows = [record for record in self.records() if record["measure"] == measure]
        if not rows:
            return None
        if year is None:
            return sorted(rows, key=lambda item: item["year"], reverse=True)[0]
        for record in rows:
            if record["year"] == year:
                return record
        return None

    def combined_births_deaths_answer(self, question: str) -> dict[str, Any]:
        year = self.requested_year(question)
        birth = self.record_for("births", year)
        death = self.record_for("deaths", year)
        if birth is None or death is None:
            return self.missing_answer(question)
        natural = self.record_for("natural increase", birth["year"])
        natural_text = f" Natural increase: {format_count(natural['count'])}." if natural else ""
        return {
            "question": question,
            "answer": (
                f"For {birth['year']}, the DHSS Vital Statistics FOCUS report lists {format_count(birth['count'])} Missouri resident live births "
                f"and {format_count(death['count'])} Missouri resident deaths.{natural_text} "
                "These are statewide aggregate counts from Table 1, not person-level vital records."
            ),
            "retrieved_context_id": f"dhss_vital_stats_index:births_deaths:{birth['year']}",
            "retrieved_source": "dhss_vital_stats_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local DHSS Vital Statistics FOCUS report index.",
            "citations": self.citation(matched_rows=2 + int(natural is not None)),
            "source_rows": [
                {"source_file": birth["source_url"], "values": birth},
                {"source_file": death["source_url"], "values": death},
            ]
            + ([{"source_file": natural["source_url"], "values": natural}] if natural else []),
        }

    def measure_answer(self, question: str, measure: str) -> dict[str, Any]:
        record = self.record_for(measure, self.requested_year(question))
        if record is None:
            return self.missing_answer(question)
        rate_sentence = ""
        if record.get("rate") is not None and record.get("rate_unit"):
            rate_sentence = f" Rate: {format_rate(record['rate'])} {record['rate_unit']}."
        return {
            "question": question,
            "answer": (
                f"The DHSS Vital Statistics FOCUS report lists {measure} for Missouri in {record['year']} as "
                f"{format_count(record['count'])}.{rate_sentence} "
                "This is a statewide aggregate Table 1 value, not a person-level vital record."
            ),
            "retrieved_context_id": f"dhss_vital_stats_index:{record['record_id']}",
            "retrieved_source": "dhss_vital_stats_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local DHSS Vital Statistics FOCUS report index.",
            "citations": self.citation(matched_rows=1),
            "source_rows": [{"source_file": record["source_url"], "values": record}],
        }

    def source_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        return {
            "question": question,
            "answer": (
                "The DHSS births/deaths aggregate index uses the official DHSS FOCUS page and the latest "
                f"Vital Statistics FOCUS PDF found there: {payload.get('report_url')}. It parses Table 1 statewide aggregate counts only."
            ),
            "retrieved_context_id": "dhss_vital_stats_index:source",
            "retrieved_source": "dhss_vital_stats_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local DHSS Vital Statistics FOCUS report index.",
            "citations": self.citation(matched_rows=0),
            "source_rows": [],
        }

    def missing_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        year_text = ", ".join(str(year) for year in payload.get("years", []))
        return {
            "question": question,
            "answer": (
                "I could not match that question to a supported DHSS vital-statistics aggregate row. "
                f"Indexed years: {year_text}. Try asking about statewide births, deaths, natural increase, infant deaths, marriages, divorces, or population."
            ),
            "retrieved_context_id": "dhss_vital_stats_index:no_match",
            "retrieved_source": "dhss_vital_stats_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "No row matched the local DHSS Vital Statistics FOCUS report index.",
            "citations": self.citation(matched_rows=0),
            "source_rows": [],
        }

    def answer(self, question: str) -> dict[str, Any] | None:
        if not self.available():
            return self.unavailable_answer(question)
        lowered = question.lower()
        if asks_for_source(question):
            return self.source_answer(question)
        if ("birth" in lowered or "births" in lowered) and "death" in lowered:
            return self.combined_births_deaths_answer(question)
        if asks_for_summary(question):
            return self.summary_answer(question)
        if asks_for_latest_year(question):
            return self.latest_year_answer(question)
        measure = self.match_measure(question)
        if measure is not None:
            return self.measure_answer(question, measure)
        return self.missing_answer(question)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    payload = build_dhss_vital_stats_index(force=args.force)
    print(json.dumps({key: value for key, value in payload.items() if key != "records"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
