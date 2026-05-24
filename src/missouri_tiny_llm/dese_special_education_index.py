"""Build and query selected DESE special-education incidence data."""

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

import requests
from pypdf import PdfReader


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw_public" / "dese_special_education"
INDEX_PATH = RAW_DIR / "dese_special_education_index.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "dese_special_education_index_report.json"
LANDING_PAGE = "https://dese.mo.gov/special-education/data-reports"
PDF_URL = (
    "https://apps.dese.mo.gov/MCDS/FileDownloadWebHandler.ashx?"
    "filename=7d504a44-c2ddIncidence+Rate+90-present.pdf"
)
PDF_NAME = "school_age_incidence_rate_90_present.pdf"
SOURCE_NAME = "DESE Special Education school-age incidence rates"

CATEGORY_INFO: dict[str, dict[str, Any]] = {
    "ID": {
        "label": "Intellectual Disability",
        "synonyms": ("intellectual disability", "intellectual disabilities"),
    },
    "ED": {
        "label": "Emotional Disturbance",
        "synonyms": ("emotional disturbance", "emotional disability", "emotional disabilities"),
    },
    "LI": {
        "label": "Language Impairment",
        "synonyms": ("language impairment", "language impairments"),
    },
    "SP": {
        "label": "Speech Impairment",
        "synonyms": ("speech impairment", "speech impairments", "speech"),
    },
    "OI": {
        "label": "Orthopedic Impairment",
        "synonyms": ("orthopedic impairment", "orthopedic impairments"),
    },
    "VI": {
        "label": "Visual Impairment",
        "synonyms": ("visual impairment", "visual impairments", "vision impairment"),
    },
    "HI": {
        "label": "Hearing Impairment",
        "synonyms": ("hearing impairment", "hearing impairments"),
    },
    "LD": {
        "label": "Specific Learning Disabilities",
        "synonyms": (
            "specific learning disabilities",
            "specific learning disability",
            "learning disabilities",
            "learning disability",
        ),
    },
    "OHI": {
        "label": "Other Health Impaired",
        "synonyms": ("other health impaired", "other health impairment", "ohi"),
    },
    "DB": {
        "label": "Deaf/Blindness",
        "synonyms": ("deaf/blindness", "deaf blindness", "deafblind", "deaf blind"),
    },
    "MD": {
        "label": "Multiple Disabilities",
        "synonyms": ("multiple disabilities", "multiple disability"),
    },
    "AU": {
        "label": "Autism",
        "synonyms": ("autism", "autistic"),
    },
    "TBI": {
        "label": "Traumatic Brain Injury",
        "synonyms": ("traumatic brain injury", "tbi"),
    },
    "YCDD": {
        "label": "Young Child with a Developmental Delay",
        "synonyms": ("young child with a developmental delay", "developmental delay", "ycdd"),
    },
    "Total": {
        "label": "Total child count",
        "synonyms": ("total child count", "total special education", "overall incidence", "all disabilities"),
    },
    "Enrollment": {
        "label": "Total public school September enrollment",
        "synonyms": ("enrollment", "public school september enrollment", "statewide enrollment"),
    },
}

POST_2006_CATEGORIES = ("ID", "ED", "LI", "SP", "OI", "VI", "HI", "LD", "OHI", "DB", "MD", "AU", "TBI", "YCDD")
PRE_2006_CATEGORIES = ("ID", "ED", "LI", "OI", "VI", "HI", "LD", "OHI", "DB", "MD", "AU", "TBI", "YCDD")
GENERIC_TOKENS = {
    "COUNT",
    "COUNTS",
    "DATA",
    "DESE",
    "DISABILITY",
    "DISABILITIES",
    "EDUCATION",
    "FOR",
    "HOW",
    "INCIDENCE",
    "INDEXED",
    "MISSOURI",
    "RATE",
    "SPECIAL",
    "STUDENT",
    "STUDENTS",
    "THE",
    "WHAT",
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


def safe_record_id(school_year: str, category_code: str) -> str:
    return hashlib.sha1(f"{school_year}:{category_code}".encode("utf-8")).hexdigest()[:16]


def parse_school_year(value: str) -> str | None:
    match = re.search(r"\b((?:19|20)\d{2})\s*[-/]\s*(\d{2})\b", value)
    if not match:
        return None
    return f"{match.group(1)}-{match.group(2)}"


def school_year_end(school_year: str) -> int:
    start = int(school_year[:4])
    end_suffix = int(school_year[-2:])
    return 2000 + end_suffix if end_suffix < 80 else 1900 + end_suffix


def parse_numbers(value: str) -> list[int]:
    cleaned = re.sub(r"(\d,\d{3})(\d{2},\d{3})", r"\1 \2", value)
    return [int(item.replace(",", "")) for item in re.findall(r"\d[\d,]*", cleaned)]


def parse_rates(value: str) -> list[float]:
    return [float(item) for item in re.findall(r"(\d+(?:\.\d+)?)%", value)]


def format_count(value: int | None) -> str:
    return f"{value:,}" if isinstance(value, int) else "not listed"


def format_rate(value: float | None) -> str:
    return f"{value:.2f}%" if isinstance(value, float) else "not listed"


def download_sources(force: bool = False) -> dict[str, Any]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    pdf_path = RAW_DIR / PDF_NAME
    landing_path = RAW_DIR / "special_education_data_reports.html"
    session = requests.Session()
    session.headers.update({"User-Agent": "missouri-tiny-llm-case-study/1.0"})

    if force or not pdf_path.exists():
        response = session.get(PDF_URL, timeout=90)
        response.raise_for_status()
        if not response.content.startswith(b"%PDF"):
            raise ValueError("DESE special-education incidence download did not return a PDF")
        pdf_path.write_bytes(response.content)
    pdf_bytes = pdf_path.read_bytes()

    if force or not landing_path.exists():
        page_response = session.get(LANDING_PAGE, timeout=60)
        page_response.raise_for_status()
        landing_path.write_text(page_response.text, encoding="utf-8")
    landing_text = landing_path.read_text(encoding="utf-8", errors="replace")

    return {
        "landing_page": {
            "url": LANDING_PAGE,
            "local_file": str(landing_path.relative_to(PROJECT_ROOT)),
            "bytes": len(landing_text.encode("utf-8", errors="replace")),
            "sha256": hashlib.sha256(landing_text.encode("utf-8", errors="replace")).hexdigest(),
        },
        "pdf": {
            "url": PDF_URL,
            "local_file": str(pdf_path.relative_to(PROJECT_ROOT)),
            "bytes": len(pdf_bytes),
            "sha256": sha256_bytes(pdf_bytes),
        },
    }


def extract_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def source_date_label(text: str) -> str | None:
    match = re.search(r"Incidence Rates\s+((?:19|20)\d{2}-\d{2})\s+data as of\s+([0-9/]+)", text, re.I)
    return clean_text(match.group(2)) if match else None


def make_record(
    school_year: str,
    category_code: str,
    count: int | None,
    rate: float | None,
    enrollment: int | None,
) -> dict[str, Any]:
    info = CATEGORY_INFO[category_code]
    return {
        "record_id": safe_record_id(school_year, category_code),
        "school_year": school_year,
        "year_end": school_year_end(school_year),
        "category_code": category_code,
        "category_label": info["label"],
        "child_count": count,
        "incidence_rate_percent": rate,
        "statewide_enrollment": enrollment,
        "source_url": PDF_URL,
        "landing_page": LANDING_PAGE,
    }


def parse_incidence_records(text: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    lines = [clean_text(line) for line in text.splitlines()]
    for index, line in enumerate(lines):
        school_year = parse_school_year(line)
        if school_year is None or not re.match(r"^(?:19|20)\d{2}-\d{2}\s", line):
            continue
        count_values = parse_numbers(line[len(school_year) :])
        if len(count_values) not in {15, 16}:
            continue
        rate_line = lines[index + 1] if index + 1 < len(lines) and lines[index + 1].startswith("Inc Rate") else ""
        rate_values = parse_rates(rate_line)
        categories = POST_2006_CATEGORIES if len(count_values) == 16 else PRE_2006_CATEGORIES
        category_count = len(categories)
        if len(rate_values) < category_count:
            continue
        enrollment = count_values[-1]
        total = count_values[-2]
        total_rate = rate_values[category_count] if len(rate_values) > category_count else None
        for pos, category_code in enumerate(categories):
            records.append(make_record(school_year, category_code, count_values[pos], rate_values[pos], enrollment))
        records.append(make_record(school_year, "Total", total, total_rate, enrollment))
        records.append(make_record(school_year, "Enrollment", enrollment, None, enrollment))
    return records


def build_dese_special_education_index(force: bool = False) -> dict[str, Any]:
    if INDEX_PATH.exists() and not force:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))

    start = time.perf_counter()
    files = download_sources(force=force)
    pdf_path = RAW_DIR / PDF_NAME
    text = extract_pdf_text(pdf_path)
    records = parse_incidence_records(text)
    years = sorted({record["school_year"] for record in records}, key=school_year_end)
    categories = Counter(record["category_code"] for record in records)
    latest_year = years[-1] if years else None
    latest_rows = [
        record
        for record in records
        if record["school_year"] == latest_year and record["category_code"] not in {"Total", "Enrollment"}
    ]
    latest_top = sorted(latest_rows, key=lambda item: item["child_count"] or 0, reverse=True)[:5]
    payload = {
        "generated_at_utc": utc_now(),
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "source": SOURCE_NAME,
        "landing_page": LANDING_PAGE,
        "pdf_url": PDF_URL,
        "index_path": str(INDEX_PATH.relative_to(PROJECT_ROOT)),
        "record_count": len(records),
        "school_years": years,
        "latest_school_year": latest_year,
        "data_as_of": source_date_label(text),
        "category_counts": dict(sorted(categories.items())),
        "files": files,
        "notes": [
            "This index parses the official DESE statewide school-age child-count and incidence-rate PDF.",
            "It stores aggregate statewide counts and rates by disability category and school year.",
            "It does not store student-level records, district-level profiles, or contact/person data.",
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
            "latest_top_categories": [
                {
                    "category_code": record["category_code"],
                    "category_label": record["category_label"],
                    "child_count": record["child_count"],
                    "incidence_rate_percent": record["incidence_rate_percent"],
                }
                for record in latest_top
            ]
        },
    )
    return payload


def asks_for_summary(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["indexed", "coverage", "what data", "available", "summary"])


def asks_for_ranking(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["highest", "largest", "top", "most"]) and not any(
        term in lowered for term in ["total", "overall"]
    )


def asks_for_trend(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["change", "changed", "increase", "increased", "decrease", "decreased", "trend"])


def category_for_question(question: str) -> str | None:
    lowered = question.lower()
    if "enrollment" in lowered:
        return "Enrollment"
    if any(term in lowered for term in ["total child", "total special education", "overall incidence", "all disabilities"]):
        return "Total"
    for code, info in CATEGORY_INFO.items():
        if code in {"Total", "Enrollment"}:
            continue
        for synonym in info["synonyms"]:
            if re.search(rf"\b{re.escape(synonym)}\b", lowered):
                return code
    for code in sorted(CATEGORY_INFO, key=len, reverse=True):
        if code in {"ID", "ED", "LI", "SP", "OI", "VI", "HI", "LD", "DB", "MD"}:
            continue
        if re.search(rf"\b{re.escape(code.lower())}\b", lowered):
            return code
    return None


class DeseSpecialEducationIndex:
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
        years = payload.get("school_years", [])
        return [
            {
                "dataset": payload.get("source", SOURCE_NAME),
                "category": "Education",
                "kind": "DESE special-education incidence aggregate lookup",
                "lookup_table": "dese_special_education_index",
                "year": payload.get("latest_school_year"),
                "year_range": f"{years[0]}-{years[-1]}" if years else None,
                "source_files": [
                    {
                        "category": key,
                        "category_label": "Official PDF" if key == "pdf" else "DESE Special Education Data Reports",
                        "file_name": value.get("url"),
                        "source_url": value.get("url"),
                        "row_count": payload.get("record_count") if key == "pdf" else None,
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
                "The DESE special-education incidence index has not been built yet. Run "
                "`python scripts/build_dese_special_education_index.py --force` to index the official public PDF."
            ),
            "retrieved_context_id": "dese_special_education_index:missing",
            "retrieved_source": "dese_special_education_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "citations": [],
            "source_rows": [],
        }

    def summary_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        years = payload.get("school_years", [])
        year_text = f"{years[0]} through {years[-1]}" if years else "the indexed PDF years"
        return {
            "question": question,
            "answer": (
                f"The DESE special-education incidence layer indexes {payload.get('record_count', 0):,} statewide "
                f"aggregate row(s) from the official school-age incidence-rate PDF, covering {year_text}. "
                f"The latest indexed school year is {payload.get('latest_school_year')} with data as of "
                f"{payload.get('data_as_of') or 'the source PDF date'}. It can answer statewide child counts, "
                "incidence rates by disability category, total child count, public-school enrollment, and top-category rankings. "
                "It does not include student-level or district-level records."
            ),
            "retrieved_context_id": "dese_special_education_index:summary",
            "retrieved_source": "dese_special_education_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local DESE special-education incidence PDF index.",
            "citations": self.citation(matched_rows=payload.get("record_count", 0)),
            "source_rows": [],
        }

    def school_year_for_question(self, question: str) -> str | None:
        requested = parse_school_year(question)
        if requested:
            return requested
        if any(term in question.lower() for term in ["latest", "newest", "current", "most recent"]):
            return self.payload().get("latest_school_year")
        return self.payload().get("latest_school_year")

    def row_for(self, school_year: str, category_code: str) -> dict[str, Any] | None:
        for record in self.records():
            if record["school_year"] == school_year and record["category_code"] == category_code:
                return record
        return None

    def rows_for_year(self, school_year: str) -> list[dict[str, Any]]:
        return [
            record
            for record in self.records()
            if record["school_year"] == school_year and record["category_code"] not in {"Total", "Enrollment"}
        ]

    def category_answer(self, question: str, record: dict[str, Any]) -> dict[str, Any]:
        if record["category_code"] == "Enrollment":
            answer = (
                f"For {record['school_year']}, DESE lists statewide public-school September enrollment as "
                f"{format_count(record['child_count'])}."
            )
        elif record["category_code"] == "Total":
            answer = (
                f"For {record['school_year']}, DESE lists {format_count(record['child_count'])} school-age children "
                f"counted in special education statewide, with an overall incidence rate of "
                f"{format_rate(record['incidence_rate_percent'])}. Statewide public-school enrollment was "
                f"{format_count(record['statewide_enrollment'])}."
            )
        else:
            answer = (
                f"For {record['school_year']}, DESE lists {format_count(record['child_count'])} school-age student(s) "
                f"in the {record['category_label']} ({record['category_code']}) category statewide. "
                f"The incidence rate is {format_rate(record['incidence_rate_percent'])} of total public-school "
                f"September enrollment ({format_count(record['statewide_enrollment'])})."
            )
        return {
            "question": question,
            "answer": answer,
            "retrieved_context_id": f"dese_special_education_index:{record['school_year']}:{record['category_code']}",
            "retrieved_source": "dese_special_education_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local DESE special-education incidence PDF index.",
            "citations": self.citation(matched_rows=1),
            "source_rows": [{"source_file": record["source_url"], "values": record}],
        }

    def ranking_answer(self, question: str, school_year: str) -> dict[str, Any]:
        rows = sorted(self.rows_for_year(school_year), key=lambda item: item["child_count"] or 0, reverse=True)[:5]
        rendered = "; ".join(
            f"{index}. {row['category_label']} ({row['category_code']}): "
            f"{format_count(row['child_count'])}, {format_rate(row['incidence_rate_percent'])}"
            for index, row in enumerate(rows, start=1)
        )
        return {
            "question": question,
            "answer": f"The largest DESE special-education school-age categories in {school_year} are: {rendered}.",
            "retrieved_context_id": f"dese_special_education_index:ranking:{school_year}",
            "retrieved_source": "dese_special_education_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed by ranking category rows in the local DESE special-education incidence PDF index.",
            "citations": self.citation(matched_rows=len(rows)),
            "source_rows": [{"source_file": row["source_url"], "values": row} for row in rows],
        }

    def trend_answer(self, question: str, category_code: str, school_year: str) -> dict[str, Any] | None:
        rows = sorted(
            [record for record in self.records() if record["category_code"] == category_code],
            key=lambda item: item["year_end"],
        )
        current = next((record for record in rows if record["school_year"] == school_year), None)
        if current is None:
            return None
        previous_rows = [record for record in rows if record["year_end"] < current["year_end"]]
        if not previous_rows:
            return None
        previous = previous_rows[-1]
        count_delta = (current["child_count"] or 0) - (previous["child_count"] or 0)
        rate_delta: float | None = None
        if current.get("incidence_rate_percent") is not None and previous.get("incidence_rate_percent") is not None:
            rate_delta = current["incidence_rate_percent"] - previous["incidence_rate_percent"]
        direction = "increased" if count_delta > 0 else "decreased" if count_delta < 0 else "did not change"
        answer = (
            f"DESE {CATEGORY_INFO[category_code]['label']} ({category_code}) child count {direction} from "
            f"{format_count(previous['child_count'])} in {previous['school_year']} to "
            f"{format_count(current['child_count'])} in {current['school_year']} "
            f"({count_delta:+,})."
        )
        if rate_delta is not None:
            answer += (
                f" The incidence rate moved from {format_rate(previous['incidence_rate_percent'])} to "
                f"{format_rate(current['incidence_rate_percent'])} ({rate_delta:+.2f} percentage points)."
            )
        return {
            "question": question,
            "answer": answer,
            "retrieved_context_id": f"dese_special_education_index:trend:{category_code}:{school_year}",
            "retrieved_source": "dese_special_education_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed by comparing adjacent school-year rows in the local DESE special-education incidence PDF index.",
            "citations": self.citation(matched_rows=2),
            "source_rows": [
                {"source_file": previous["source_url"], "values": previous},
                {"source_file": current["source_url"], "values": current},
            ],
        }

    def missing_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "I have indexed DESE statewide special-education incidence rows, but this question did not match a supported "
                "school year or disability category. Try asking `How many Missouri students were in the Autism category in 2024-25?`, "
                "`What was the total DESE special education incidence rate in 2024-25?`, or "
                "`Which DESE special education category had the highest count in 2024-25?`"
            ),
            "retrieved_context_id": "dese_special_education_index:no_match",
            "retrieved_source": "dese_special_education_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "No category/year matched the local DESE special-education incidence PDF index.",
            "citations": self.citation(matched_rows=0),
            "source_rows": [],
        }

    def answer(self, question: str) -> dict[str, Any] | None:
        if not self.available():
            return self.unavailable_answer(question)
        if asks_for_summary(question):
            return self.summary_answer(question)
        school_year = self.school_year_for_question(question)
        if not school_year:
            return self.missing_answer(question)
        if asks_for_ranking(question):
            return self.ranking_answer(question, school_year)
        category_code = category_for_question(question)
        if category_code is None:
            return self.missing_answer(question)
        if asks_for_trend(question) and category_code not in {"Enrollment"}:
            trend = self.trend_answer(question, category_code, school_year)
            if trend is not None:
                return trend
        record = self.row_for(school_year, category_code)
        if record is None:
            return self.missing_answer(question)
        return self.category_answer(question, record)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    payload = build_dese_special_education_index(force=args.force)
    print(json.dumps({key: value for key, value in payload.items() if key != "records"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
