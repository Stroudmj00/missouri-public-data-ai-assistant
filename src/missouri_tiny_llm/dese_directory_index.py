"""Build and query selected DESE School Directory PDF data."""

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


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw_public" / "dese_directory"
INDEX_PATH = RAW_DIR / "dese_directory_index.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "dese_directory_index_report.json"
SOURCE_PAGE = "https://dese.mo.gov/data-system-management/directory"
DATA_DOWNLOADS_PAGE = "https://dese.mo.gov/school-directory/data-downloads"
DISTRICT_PDF_URL = (
    "https://apps.dese.mo.gov/MCDS/FileDownloadWebHandler.ashx?"
    "filename=16262384-5e2cMissouri%20School%20Directory%20by%20District.pdf"
)
DISTRICT_PDF_NAME = "missouri_school_directory_by_district.pdf"

DISTRICT_RE = re.compile(r"^(?P<name>.+?)\s+\((?P<code>\d{3}-\d{3})\)$")
SCHOOL_RE = re.compile(r"^(?P<name>.+?)\s*\((?P<code>\d{4})\)$")
GRADE_SPAN_RE = re.compile(r"Grade Span:\s*([A-Z0-9]{1,2}\s*-\s*[A-Z0-9]{1,2})")
TOTAL_ROW_RE = re.compile(r"^Total\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)$")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_text(value: str) -> str:
    cleaned = re.sub(r"[^A-Z0-9]+", " ", clean_text(value).upper())
    return re.sub(r"\s+", " ", cleaned).strip()


def to_int(value: str) -> int | None:
    cleaned = value.replace(",", "").strip()
    return int(cleaned) if cleaned.isdigit() else None


def parse_date_label(text: str) -> str | None:
    match = re.search(r"Data as of:\s*([0-9/]+(?:\s+[0-9:]+\s+[AP]M)?)", text, flags=re.I)
    return clean_text(match.group(1)) if match else None


def filtered_lines(text: str) -> list[str]:
    skip_prefixes = (
        "Missouri School Directory",
        "(Maps are provided",
        "Maps are provided",
        "Report as of:",
        "Data as of:",
        "Enrollment (Prior Year)",
        "Schools Cert. StaffResidents",
        "Schools Cert. Staff Residents",
        "Name Title Yrs in District",
        "Congressional District:",
        "House District:",
        "Senate District:",
    )
    lines = []
    for raw_line in text.splitlines():
        line = clean_text(raw_line)
        if not line:
            continue
        if any(line.startswith(prefix) for prefix in skip_prefixes):
            continue
        if line.isdigit():
            continue
        lines.append(line)
    return lines


def parse_grade_span(line: str) -> str | None:
    match = GRADE_SPAN_RE.search(line)
    if not match:
        return None
    return re.sub(r"\s+", "", match.group(1)).upper()


def sanitized_district(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "district_name": record.get("district_name"),
        "district_code": record.get("district_code"),
        "county": record.get("county"),
        "msip": record.get("msip"),
        "school_count": record.get("school_count"),
        "certified_staff": record.get("certified_staff"),
        "resident_students": record.get("resident_students"),
        "nonresident_students": record.get("nonresident_students"),
        "total_enrollment": record.get("total_enrollment"),
        "parsed_school_count": record.get("parsed_school_count"),
        "page_start": record.get("page_start"),
    }


def sanitized_school(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "school_name": record.get("school_name"),
        "school_code": record.get("school_code"),
        "grade_span": record.get("grade_span"),
        "district_name": record.get("district_name"),
        "district_code": record.get("district_code"),
        "county": record.get("county"),
        "page": record.get("page"),
    }


def parse_directory_pdf(pdf_path: Path) -> dict[str, Any]:
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    districts: list[dict[str, Any]] = []
    schools: list[dict[str, Any]] = []
    current_district: dict[str, Any] | None = None
    current_school: dict[str, Any] | None = None
    data_as_of_values: list[str] = []

    for page_index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        data_as_of = parse_date_label(text)
        if data_as_of:
            data_as_of_values.append(data_as_of)
        for line in filtered_lines(text):
            district_match = DISTRICT_RE.match(line)
            if district_match:
                current_district = {
                    "district_name": clean_text(district_match.group("name")),
                    "district_name_norm": normalize_text(district_match.group("name")),
                    "district_code": district_match.group("code"),
                    "county": "",
                    "county_norm": "",
                    "msip": "",
                    "assessed_valuation": "",
                    "tax_levy": "",
                    "school_count": None,
                    "certified_staff": None,
                    "resident_students": None,
                    "nonresident_students": None,
                    "total_enrollment": None,
                    "parsed_school_count": 0,
                    "page_start": page_index,
                }
                districts.append(current_district)
                current_school = None
                continue

            if current_district is None:
                continue

            school_match = SCHOOL_RE.match(line)
            if school_match:
                current_school = {
                    "school_name": clean_text(school_match.group("name")),
                    "school_name_norm": normalize_text(school_match.group("name")),
                    "school_code": school_match.group("code"),
                    "grade_span": None,
                    "district_name": current_district["district_name"],
                    "district_name_norm": current_district["district_name_norm"],
                    "district_code": current_district["district_code"],
                    "county": current_district.get("county", ""),
                    "county_norm": current_district.get("county_norm", ""),
                    "page": page_index,
                }
                schools.append(current_school)
                current_district["parsed_school_count"] += 1
                continue

            if line.startswith("County:"):
                county = clean_text(line.split(":", 1)[1])
                current_district["county"] = county
                current_district["county_norm"] = normalize_text(county)
                continue
            if line.startswith("MSIP:"):
                current_district["msip"] = clean_text(line.split(":", 1)[1])
                continue
            if line.startswith("Assessed Valuation:"):
                current_district["assessed_valuation"] = clean_text(line.split(":", 1)[1])
                continue
            if line.startswith("Tax Levy:"):
                current_district["tax_levy"] = clean_text(line.split(":", 1)[1])
                continue

            total_match = TOTAL_ROW_RE.match(line)
            if total_match:
                current_district["school_count"] = to_int(total_match.group(1))
                current_district["certified_staff"] = to_int(total_match.group(2))
                current_district["resident_students"] = to_int(total_match.group(3))
                current_district["nonresident_students"] = to_int(total_match.group(4))
                current_district["total_enrollment"] = to_int(total_match.group(5))
                continue

            if current_school is not None:
                grade_span = parse_grade_span(line)
                if grade_span:
                    current_school["grade_span"] = grade_span

    district_by_code = {district["district_code"]: district for district in districts}
    for school in schools:
        district = district_by_code.get(school["district_code"])
        if district:
            school["county"] = district.get("county", "")
            school["county_norm"] = district.get("county_norm", "")

    return {
        "page_count": len(reader.pages),
        "data_as_of": data_as_of_values[0] if data_as_of_values else None,
        "districts": districts,
        "schools": schools,
    }


def top_counties(districts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(district.get("county", "") for district in districts if district.get("county"))
    return [
        {"county": county, "district_count": count}
        for county, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:12]
    ]


def build_dese_directory_index(force: bool = False) -> dict[str, Any]:
    if INDEX_PATH.exists() and not force:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (compatible; MissouriPublicDataChat/1.0; +https://github.com/Stroudmj00/missouri-tiny-llm-case-study)",
            "Accept": "application/pdf,text/html,*/*;q=0.8",
        }
    )
    start = time.perf_counter()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    response = session.get(DISTRICT_PDF_URL, timeout=120)
    response.raise_for_status()
    pdf_bytes = response.content
    if not pdf_bytes.startswith(b"%PDF"):
        raise ValueError("DESE School Directory download did not return a PDF")
    pdf_path = RAW_DIR / DISTRICT_PDF_NAME
    pdf_path.write_bytes(pdf_bytes)
    parsed = parse_directory_pdf(pdf_path)
    districts = parsed["districts"]
    schools = parsed["schools"]
    top_enrollment = [
        sanitized_district(district)
        for district in sorted(
            [district for district in districts if isinstance(district.get("total_enrollment"), int)],
            key=lambda item: (-int(item["total_enrollment"]), item["district_name"]),
        )[:12]
    ]
    payload = {
        "generated_at_utc": utc_now(),
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "source": "DESE School Directory",
        "source_page": SOURCE_PAGE,
        "data_downloads_page": DATA_DOWNLOADS_PAGE,
        "source_url": DISTRICT_PDF_URL,
        "index_path": str(INDEX_PATH.relative_to(PROJECT_ROOT)),
        "data_as_of": parsed["data_as_of"],
        "bytes": len(pdf_bytes),
        "sha256": sha256_bytes(pdf_bytes),
        "page_count": parsed["page_count"],
        "district_count": len(districts),
        "school_count": len(schools),
        "county_count": len({district["county"] for district in districts if district.get("county")}),
        "top_counties_by_district_count": top_counties(districts),
        "top_districts_by_enrollment": top_enrollment,
        "districts": districts,
        "schools": schools,
    }
    write_json(INDEX_PATH, payload)
    write_json(
        REPORT_PATH,
        {
            "generated_at_utc": payload["generated_at_utc"],
            "elapsed_seconds": payload["elapsed_seconds"],
            "source": payload["source"],
            "source_page": payload["source_page"],
            "data_downloads_page": payload["data_downloads_page"],
            "source_url": payload["source_url"],
            "index_path": payload["index_path"],
            "data_as_of": payload["data_as_of"],
            "bytes": payload["bytes"],
            "sha256": payload["sha256"],
            "page_count": payload["page_count"],
            "district_count": payload["district_count"],
            "school_count": payload["school_count"],
            "county_count": payload["county_count"],
            "top_counties_by_district_count": payload["top_counties_by_district_count"],
            "top_districts_by_enrollment": payload["top_districts_by_enrollment"],
        },
    )
    return payload


def asks_for_top(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["top", "highest", "largest", "most", "biggest"])


def asks_for_count(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["how many", "count", "number of", "total"])


class DeseDirectoryIndex:
    def __init__(self, path: Path = INDEX_PATH) -> None:
        self.path = path
        self._payload: dict[str, Any] | None = None

    def available(self) -> bool:
        return self.path.exists() and self.path.stat().st_size > 0

    def payload(self) -> dict[str, Any]:
        if self._payload is None:
            self._payload = json.loads(self.path.read_text(encoding="utf-8")) if self.available() else {}
        return self._payload

    def districts(self) -> list[dict[str, Any]]:
        return list(self.payload().get("districts", []))

    def schools(self) -> list[dict[str, Any]]:
        return list(self.payload().get("schools", []))

    def citation(self, matched_rows: int = 0) -> list[dict[str, Any]]:
        payload = self.payload()
        return [
            {
                "dataset": payload.get("source", "DESE School Directory"),
                "category": "Education",
                "kind": "school directory PDF row",
                "lookup_table": "dese_directory_index",
                "year": None,
                "year_range": None,
                "source_files": [
                    {
                        "category": "dese_school_directory",
                        "category_label": "DESE School Directory page",
                        "file_name": payload.get("source_page", SOURCE_PAGE),
                        "row_count": None,
                        "bytes": None,
                        "sha256": None,
                    },
                    {
                        "category": "dese_school_directory",
                        "category_label": "School Directory by District PDF",
                        "file_name": payload.get("source_url", DISTRICT_PDF_URL),
                        "row_count": payload.get("district_count"),
                        "bytes": payload.get("bytes"),
                        "sha256": payload.get("sha256"),
                    },
                ],
                "source_file_count": 2,
                "source_rows": payload.get("district_count"),
                "matched_rows": matched_rows,
            }
        ]

    def unavailable_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "The selected DESE School Directory index has not been built yet. Run "
                "`python scripts/build_dese_directory_index.py --force` to download the public directory PDF and build exact lookups."
            ),
            "retrieved_context_id": "dese_directory_index:missing",
            "retrieved_source": "dese_directory_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "The DESE directory route exists, but the local ignored index is missing.",
            "citations": [],
            "source_rows": [],
        }

    def summary_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        top = "; ".join(
            f"{item['district_name']}: {item['total_enrollment']:,}"
            for item in payload.get("top_districts_by_enrollment", [])[:5]
            if item.get("total_enrollment") is not None
        )
        return {
            "question": question,
            "answer": (
                f"The selected DESE School Directory exact lookup layer indexes the public School Directory by District PDF. "
                f"It contains {payload.get('district_count', 0):,} district row(s) and {payload.get('school_count', 0):,} school/building row(s) "
                f"across {payload.get('county_count', 0):,} counties. Data as of: {payload.get('data_as_of')}. "
                "It can answer district county/MSIP/enrollment, school counts, top enrollment rankings, and school grade-span lookup. "
                f"Top districts by prior-year enrollment: {top}."
            ),
            "retrieved_context_id": "dese_directory_index:summary",
            "retrieved_source": "dese_directory_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local DESE School Directory PDF index.",
            "citations": self.citation(matched_rows=payload.get("district_count", 0)),
            "source_rows": [],
        }

    def district_from_question(self, question: str) -> dict[str, Any] | None:
        question_norm = normalize_text(question)
        code_match = re.search(r"\b\d{3}-\d{3}\b", question)
        if code_match:
            code = code_match.group(0)
            for district in self.districts():
                if district.get("district_code") == code:
                    return district
        for district in sorted(self.districts(), key=lambda item: len(item.get("district_name_norm", "")), reverse=True):
            name_norm = district.get("district_name_norm", "")
            if name_norm and re.search(rf"\b{re.escape(name_norm)}\b", question_norm):
                return district
        return None

    def school_from_question(self, question: str) -> dict[str, Any] | None:
        question_norm = normalize_text(question)
        for school in sorted(self.schools(), key=lambda item: len(item.get("school_name_norm", "")), reverse=True):
            name_norm = school.get("school_name_norm", "")
            if name_norm and re.search(rf"\b{re.escape(name_norm)}\b", question_norm):
                return school
        return None

    def can_answer(self, question: str) -> bool:
        if not self.available():
            return False
        lowered = question.lower()
        if re.search(r"\b\d{3}-\d{3}\b", question):
            return True
        if any(term in lowered for term in ["grade span", "msip", "county-district", "school directory"]):
            return True
        if asks_for_top(question) and any(term in lowered for term in ["enrollment", "students", "largest district"]):
            return True
        return self.school_from_question(question) is not None or self.district_from_question(question) is not None

    def district_answer(self, question: str, district: dict[str, Any]) -> dict[str, Any]:
        school_count = district.get("school_count") or district.get("parsed_school_count")
        if asks_for_count(question) and "school" in question.lower():
            answer = (
                f"The indexed DESE School Directory lists {school_count:,} school/building row(s) for "
                f"{district['district_name']} ({district['district_code']}) in {district['county']} County."
            )
        else:
            enrollment = district.get("total_enrollment")
            enrollment_text = f"{enrollment:,}" if isinstance(enrollment, int) else "not listed"
            answer = (
                f"The indexed DESE School Directory lists {district['district_name']} ({district['district_code']}) "
                f"in {district['county']} County. MSIP: {district.get('msip') or 'not listed'}. "
                f"Prior-year total enrollment: {enrollment_text}; school/building rows: {school_count}."
            )
        return {
            "question": question,
            "answer": answer,
            "retrieved_context_id": f"dese_directory_index:district:{district['district_code']}",
            "retrieved_source": "dese_directory_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local DESE School Directory PDF index.",
            "citations": self.citation(matched_rows=1),
            "source_rows": [{"source_file": DISTRICT_PDF_URL, "values": sanitized_district(district)}],
        }

    def school_answer(self, question: str, school: dict[str, Any]) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                f"The indexed DESE School Directory lists {school['school_name']} ({school['school_code']}) "
                f"in {school['district_name']} ({school['district_code']}), {school.get('county') or 'county not listed'} County. "
                f"Grade span: {school.get('grade_span') or 'not listed'}."
            ),
            "retrieved_context_id": f"dese_directory_index:school:{school['district_code']}:{school['school_code']}",
            "retrieved_source": "dese_directory_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local DESE School Directory PDF index.",
            "citations": self.citation(matched_rows=1),
            "source_rows": [{"source_file": DISTRICT_PDF_URL, "values": sanitized_school(school)}],
        }

    def top_enrollment_answer(self, question: str) -> dict[str, Any]:
        rows = self.payload().get("top_districts_by_enrollment", [])
        rendered = "; ".join(f"{item['district_name']}: {item['total_enrollment']:,}" for item in rows[:5])
        winner = rows[0] if rows else {"district_name": "unknown", "total_enrollment": 0}
        return {
            "question": question,
            "answer": (
                f"In the indexed DESE School Directory, the district with the largest prior-year enrollment is "
                f"{winner['district_name']}: {winner['total_enrollment']:,}. Top districts: {rendered}."
            ),
            "retrieved_context_id": "dese_directory_index:rank:total_enrollment",
            "retrieved_source": "dese_directory_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed by ranking prior-year total enrollment in the local DESE School Directory index.",
            "citations": self.citation(matched_rows=self.payload().get("district_count", 0)),
            "source_rows": [{"source_file": DISTRICT_PDF_URL, "values": item} for item in rows[:5]],
        }

    def missing_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "I have indexed the selected DESE School Directory PDF, but this question did not match a listed district, "
                "school/building, or supported directory ranking. Try `What DESE school directory data is indexed?`, "
                "`What county is Columbia 93 in?`, or `What grade span is Rock Bridge Sr. High?`."
            ),
            "retrieved_context_id": "dese_directory_index:no_match",
            "retrieved_source": "dese_directory_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Answered from DESE directory coverage metadata because no exact row matched.",
            "citations": self.citation(),
            "source_rows": [],
        }

    def answer(self, question: str) -> dict[str, Any] | None:
        if not self.available():
            return self.unavailable_answer(question)
        lowered = question.lower()
        if re.search(r"\b(dese|school)\b.*\bdirectory\b.*\b(indexed|lookup|data)\b", lowered):
            return self.summary_answer(question)
        if asks_for_top(question) and any(term in lowered for term in ["enrollment", "students", "largest district"]):
            return self.top_enrollment_answer(question)
        school = self.school_from_question(question)
        if school:
            return self.school_answer(question, school)
        district = self.district_from_question(question)
        if district:
            return self.district_answer(question, district)
        return self.missing_answer(question)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    payload = build_dese_directory_index(force=args.force)
    print(json.dumps({key: value for key, value in payload.items() if key not in {"districts", "schools"}}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
