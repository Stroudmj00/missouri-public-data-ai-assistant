"""Build and query selected Missouri assessment aggregate rows."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw_public" / "dese_assessment"
INDEX_PATH = RAW_DIR / "dese_assessment_index.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "dese_assessment_index_report.json"

SOURCE_NAME = "Selected 2025 Missouri Assessment Program aggregate rows"
DOWNLOADS_PAGE = "https://moschooldata.org/downloads"
LEARNING_OUTCOMES_PAGE = "https://moschooldata.org/dashboards/proficiency"
DESE_SCHOOL_DATA_PAGE = "https://dese.mo.gov/school-data"
DESE_ASSESSMENT_PAGE = "https://dese.mo.gov/quality-schools/assessment"
GOOGLE_DRIVE_FILE_ID = "1TV9OS-4_QQkD7F0KSYZop0gedc-lvRkx"
GOOGLE_DRIVE_VIEW_URL = f"https://drive.google.com/file/d/{GOOGLE_DRIVE_FILE_ID}/view?usp=sharing"

PERFORMANCE_METRICS = ("% Below Basic", "% Basic", "% Proficient", "% Advanced")
DEFAULT_SELECTED_DISTRICTS = (
    "COLUMBIA 93",
    "SPRINGFIELD R-XII",
    "ST. LOUIS CITY",
    "KANSAS CITY 33",
    "NORTH KANSAS CITY 74",
    "ROCKWOOD R-VI",
)
DEFAULT_SELECTED_SCHOOLS = (
    "ROCK BRIDGE SR. HIGH",
    "DAVID H. HICKMAN HIGH",
    "ELIOT BATTLE ELEMENTARY",
    "ADAIR CO. HIGH",
)

GENERIC_TOKENS = {
    "ALL",
    "AND",
    "ASSESSMENT",
    "ASSESSMENTS",
    "DATA",
    "DESE",
    "DISTRICT",
    "EOC",
    "FOR",
    "GRADE",
    "HIGH",
    "HOW",
    "INDEX",
    "INDEXED",
    "MAP",
    "MISSOURI",
    "PROGRAM",
    "PUBLIC",
    "SCHOOL",
    "SCHOOLS",
    "STATE",
    "STATEWIDE",
    "THE",
    "WHAT",
    "WAS",
    "WERE",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_text(value: Any) -> str:
    cleaned = re.sub(r"[^A-Z0-9]+", " ", clean_text(value).upper())
    replacements = {
        " ST ": " SAINT ",
        " SR ": " SENIOR ",
        " JR ": " JUNIOR ",
    }
    normalized = f" {cleaned} "
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    return re.sub(r"\s+", " ", normalized).strip()


def query_tokens(value: Any) -> set[str]:
    return {token for token in normalize_text(value).split() if len(token) > 1 and token not in GENERIC_TOKENS}


def parse_float(value: Any) -> float | None:
    cleaned = clean_text(value).replace(",", "")
    if not cleaned:
        return None
    try:
        return round(float(cleaned), 4)
    except ValueError:
        return None


def parse_int(value: Any) -> int | None:
    cleaned = clean_text(value).replace(",", "")
    if re.fullmatch(r"\d+", cleaned):
        return int(cleaned)
    return None


def format_percent(value: float | None) -> str:
    if value is None:
        return "suppressed or not listed"
    rendered = f"{value:.1f}" if value == round(value, 1) else f"{value:.2f}"
    rendered = rendered.rstrip("0").rstrip(".")
    return f"{rendered}%"


def format_count(value: int | None) -> str:
    return f"{value:,}" if isinstance(value, int) else "not listed"


def safe_record_id(row: dict[str, Any]) -> str:
    key = "|".join(
        clean_text(row.get(field))
        for field in (
            "entity",
            "county_code",
            "county_district",
            "school_code",
            "student_group",
            "content_area",
            "grade_level",
            "metric",
            "district_name",
            "school_name",
        )
    )
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def parse_google_warning_size_mb(text: str) -> float | None:
    match = re.search(r"\(([\d.]+)\s*([KMG])\)", text, re.I)
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2).upper()
    if unit == "K":
        return round(value / 1024, 3)
    if unit == "G":
        return round(value * 1024, 3)
    return round(value, 3)


def google_drive_confirm_params(session: requests.Session) -> tuple[dict[str, str], dict[str, Any]]:
    response = session.get(
        f"https://drive.google.com/uc?export=download&id={GOOGLE_DRIVE_FILE_ID}",
        timeout=45,
    )
    response.raise_for_status()
    text = response.text
    confirm = re.search(r'name="confirm" value="([^"]+)"', text)
    uuid = re.search(r'name="uuid" value="([^"]+)"', text)
    filename = re.search(r'<a href="/open\?id=[^"]+">([^<]+)</a>', text)
    params = {"id": GOOGLE_DRIVE_FILE_ID, "export": "download"}
    if confirm:
        params["confirm"] = confirm.group(1)
    if uuid:
        params["uuid"] = uuid.group(1)
    metadata = {
        "warning_page_bytes": len(text.encode("utf-8", errors="replace")),
        "warning_page_sha256": sha256_text(text),
        "source_file_name": html.unescape(filename.group(1)) if filename else "mede_map_for_download_2025.csv",
        "source_file_size_mb_estimate": parse_google_warning_size_mb(text),
    }
    return params, metadata


def download_source_page(session: requests.Session, force: bool) -> dict[str, Any]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    target = RAW_DIR / "moschooldata_downloads.html"
    if force or not target.exists():
        response = session.get(DOWNLOADS_PAGE, timeout=60)
        response.raise_for_status()
        target.write_text(response.text, encoding="utf-8")
    text = target.read_text(encoding="utf-8", errors="replace")
    return {
        "url": DOWNLOADS_PAGE,
        "local_file": str(target.relative_to(PROJECT_ROOT)),
        "bytes": len(text.encode("utf-8", errors="replace")),
        "sha256": sha256_text(text),
    }


def normalized_assessment_row(row: dict[str, Any]) -> dict[str, Any]:
    district_name = clean_text(row.get("district_name"))
    school_name = clean_text(row.get("school_name"))
    value = parse_float(row.get("value"))
    normalized = {
        "record_id": safe_record_id(row),
        "entity": clean_text(row.get("entity")),
        "county_code": clean_text(row.get("county_code")),
        "county_district": clean_text(row.get("county_district")),
        "school_code": clean_text(row.get("school_code")),
        "county_name": clean_text(row.get("county_name")),
        "district_name": district_name,
        "district_norm": normalize_text(district_name),
        "school_name": school_name,
        "school_norm": normalize_text(school_name),
        "student_group": clean_text(row.get("student_group")),
        "content_area": clean_text(row.get("content_area")),
        "grade_level": clean_text(row.get("grade_level")),
        "year": parse_int(row.get("year")),
        "n_size": parse_int(row.get("n_size")),
        "metric": clean_text(row.get("metric")),
        "value_percent": value,
        "value_raw": clean_text(row.get("value")),
        "suppressed": value is None,
        "source_url": DOWNLOADS_PAGE,
        "download_url": GOOGLE_DRIVE_VIEW_URL,
        "dashboard_url": LEARNING_OUTCOMES_PAGE,
        "dese_school_data_url": DESE_SCHOOL_DATA_PAGE,
        "dese_assessment_url": DESE_ASSESSMENT_PAGE,
    }
    return normalized


def keep_row(row: dict[str, Any], selected_districts: set[str], selected_schools: set[str]) -> bool:
    if clean_text(row.get("student_group")) != "All Students":
        return False
    if clean_text(row.get("metric")) not in PERFORMANCE_METRICS:
        return False
    entity = clean_text(row.get("entity"))
    district = normalize_text(row.get("district_name"))
    school = normalize_text(row.get("school_name"))
    return entity == "State" or district in selected_districts or school in selected_schools


def stream_assessment_rows(
    session: requests.Session,
    params: dict[str, str],
) -> Iterable[dict[str, str]]:
    with session.get(
        "https://drive.usercontent.google.com/download",
        params=params,
        stream=True,
        timeout=180,
    ) as response:
        response.raise_for_status()
        response.encoding = "utf-8"
        lines = response.iter_lines(decode_unicode=True)
        header = next(lines)
        if isinstance(header, bytes):
            header = header.decode("utf-8", errors="replace")
        fields = next(csv.reader([header]))
        for line in lines:
            if not line:
                continue
            if isinstance(line, bytes):
                line = line.decode("utf-8", errors="replace")
            values = next(csv.reader([line]))
            if len(values) != len(fields):
                continue
            yield dict(zip(fields, values))


def build_dese_assessment_index(
    force: bool = False,
    max_source_mb: float = 250.0,
    selected_districts: tuple[str, ...] = DEFAULT_SELECTED_DISTRICTS,
    selected_schools: tuple[str, ...] = DEFAULT_SELECTED_SCHOOLS,
) -> dict[str, Any]:
    if INDEX_PATH.exists() and not force:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (compatible; MissouriPublicDataChat/1.0; +https://github.com/Stroudmj00/missouri-tiny-llm-case-study)",
            "Accept": "text/csv,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
    )
    start = time.perf_counter()
    source_page = download_source_page(session, force=force)
    params, drive_metadata = google_drive_confirm_params(session)
    size_estimate = drive_metadata.get("source_file_size_mb_estimate")
    if size_estimate is not None and float(size_estimate) > max_source_mb:
        raise ValueError(f"Assessment CSV estimate {size_estimate} MB exceeds max_source_mb={max_source_mb}")

    selected_district_norms = {normalize_text(item) for item in selected_districts}
    selected_school_norms = {normalize_text(item) for item in selected_schools}
    records: list[dict[str, Any]] = []
    source_entity_counts: Counter[str] = Counter()
    kept_entity_counts: Counter[str] = Counter()
    source_row_count = 0

    for raw_row in stream_assessment_rows(session, params):
        source_row_count += 1
        source_entity_counts[clean_text(raw_row.get("entity"))] += 1
        if keep_row(raw_row, selected_district_norms, selected_school_norms):
            record = normalized_assessment_row(raw_row)
            records.append(record)
            kept_entity_counts[record["entity"]] += 1

    years = sorted({row["year"] for row in records if isinstance(row.get("year"), int)})
    selected_district_rows = sorted(
        {
            row["district_name"]
            for row in records
            if row["entity"] == "District" and row.get("district_name")
        }
    )
    selected_school_rows = sorted(
        {
            row["school_name"]
            for row in records
            if row["entity"] == "School" and row.get("school_name")
        }
    )
    content_areas = sorted({row["content_area"] for row in records if row.get("content_area")})
    grade_levels = sorted({row["grade_level"] for row in records if row.get("grade_level")})
    payload = {
        "generated_at_utc": utc_now(),
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "source": SOURCE_NAME,
        "index_path": str(INDEX_PATH.relative_to(PROJECT_ROOT)),
        "source_page": source_page,
        "source_files": {
            "downloads_page": {
                "url": DOWNLOADS_PAGE,
                "local_file": source_page["local_file"],
                "bytes": source_page["bytes"],
                "sha256": source_page["sha256"],
            },
            "assessment_csv": {
                "url": GOOGLE_DRIVE_VIEW_URL,
                "file_id": GOOGLE_DRIVE_FILE_ID,
                "file_name": drive_metadata.get("source_file_name"),
                "source_file_size_mb_estimate": size_estimate,
                "raw_file_saved": False,
                "warning_page_bytes": drive_metadata.get("warning_page_bytes"),
                "warning_page_sha256": drive_metadata.get("warning_page_sha256"),
            },
            "learning_outcomes_page": {"url": LEARNING_OUTCOMES_PAGE},
            "dese_school_data_page": {"url": DESE_SCHOOL_DATA_PAGE},
            "dese_assessment_page": {"url": DESE_ASSESSMENT_PAGE},
        },
        "source_row_count": source_row_count,
        "record_count": len(records),
        "source_entity_counts": dict(source_entity_counts),
        "kept_entity_counts": dict(kept_entity_counts),
        "years": years,
        "latest_year": max(years) if years else None,
        "metrics": list(PERFORMANCE_METRICS),
        "student_group": "All Students",
        "content_areas": content_areas,
        "grade_levels": grade_levels,
        "selected_districts": selected_district_rows,
        "selected_schools": selected_school_rows,
        "notes": [
            "This is a selected aggregate index, not the full 197 MB assessment CSV.",
            "The builder streams the public CSV and stores statewide All Students performance-level rows plus selected district/school rows.",
            "It does not store student-level records or all district/school assessment rows.",
        ],
        "records": records,
    }
    write_json(INDEX_PATH, payload)
    report_payload = {key: value for key, value in payload.items() if key not in {"records", "selected_schools"}}
    report_payload["selected_school_count"] = len(selected_school_rows)
    report_payload["selected_school_examples"] = selected_school_rows[:25]
    write_json(REPORT_PATH, report_payload)
    return payload


def content_area_for_question(question: str) -> str | None:
    lowered = question.lower()
    if any(term in lowered for term in ["english ii", "ela", "english language arts", "reading", "english"]):
        return "Eng. Language Arts"
    if any(term in lowered for term in ["math", "mathematics", "algebra", "geometry"]):
        return "Mathematics"
    if any(term in lowered for term in ["science", "biology"]):
        return "Science"
    if any(term in lowered for term in ["social studies", "government"]):
        return "Social Studies"
    return None


def grade_for_question(question: str) -> str:
    lowered = question.lower()
    grade_words = {
        "third": "03",
        "fourth": "04",
        "fifth": "05",
        "sixth": "06",
        "seventh": "07",
        "eighth": "08",
    }
    for word, grade in grade_words.items():
        if f"{word} grade" in lowered or f"grade {word}" in lowered:
            return grade
    match = re.search(r"\b(?:grade\s*)?([3-8])(?:st|nd|rd|th)?\s*grade\b|\bgrade\s*([3-8])\b", lowered)
    if match:
        digit = match.group(1) or match.group(2)
        return f"0{digit}"
    course_patterns = [
        ("english ii", "English II"),
        ("english 2", "English II"),
        ("algebra ii", "Algebra II"),
        ("algebra 2", "Algebra II"),
        ("algebra i", "Algebra I"),
        ("algebra 1", "Algebra I"),
        ("geometry", "Geometry"),
        ("biology", "Biology I"),
        ("government", "Government"),
    ]
    for token, grade in course_patterns:
        if token in lowered:
            return grade
    return "All"


def metrics_for_question(question: str) -> list[str]:
    lowered = question.lower()
    if "below basic" in lowered:
        return ["% Below Basic"]
    if "basic" in lowered and "below basic" not in lowered:
        return ["% Basic"]
    if "proficient and advanced" in lowered or "proficient or advanced" in lowered:
        return ["% Proficient", "% Advanced"]
    if "advanced" in lowered:
        return ["% Advanced"]
    return ["% Proficient"]


def asks_for_summary(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["indexed", "connected", "coverage", "what data", "what assessment data"])


def best_named_match(question: str, names: Iterable[str]) -> str | None:
    normalized_question = normalize_text(question)
    tokens = query_tokens(question)
    best_name: str | None = None
    best_score = 0.0
    for name in names:
        name_norm = normalize_text(name)
        if name_norm and name_norm in normalized_question:
            return name
        name_tokens = query_tokens(name)
        if not name_tokens:
            continue
        overlap = len(tokens & name_tokens)
        if overlap == 0:
            continue
        score = overlap / len(name_tokens)
        if score > best_score:
            best_score = score
            best_name = name
    return best_name if best_score >= 0.5 else None


class DeseAssessmentIndex:
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
        files = payload.get("source_files", {})
        return [
            {
                "dataset": payload.get("source", SOURCE_NAME),
                "category": "Education",
                "kind": "selected MAP assessment aggregate lookup",
                "lookup_table": "dese_assessment_index",
                "year": payload.get("latest_year"),
                "source_files": [
                    {
                        "category": key,
                        "category_label": key.replace("_", " ").title(),
                        "file_name": value.get("url"),
                        "source_url": value.get("url"),
                        "row_count": payload.get("source_row_count") if key == "assessment_csv" else None,
                        "bytes": value.get("bytes"),
                        "sha256": value.get("sha256"),
                    }
                    for key, value in files.items()
                ],
                "source_file_count": len(files),
                "source_rows": payload.get("record_count"),
                "source_total_rows": payload.get("source_row_count"),
                "matched_rows": matched_rows,
            }
        ]

    def unavailable_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "The DESE assessment index has not been built yet. Run "
                "`python scripts/build_dese_assessment_index.py --force` to stream the public 2025 assessment CSV "
                "and keep a laptop-safe aggregate subset."
            ),
            "retrieved_context_id": "dese_assessment_index:missing",
            "retrieved_source": "dese_assessment_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "citations": [],
            "source_rows": [],
        }

    def summary_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        kept = payload.get("kept_entity_counts", {})
        districts = payload.get("selected_districts", [])
        return {
            "question": question,
            "answer": (
                f"The DESE assessment exact lookup layer indexes {payload.get('record_count', 0):,} selected 2025 "
                f"aggregate assessment row(s) after streaming {payload.get('source_row_count', 0):,} public source row(s). "
                f"Kept rows include {kept.get('State', 0):,} statewide rows, {kept.get('District', 0):,} district rows, "
                f"and {kept.get('School', 0):,} school rows for selected districts/schools. It covers All Students "
                "performance levels: Below Basic, Basic, Proficient, and Advanced. Example selected districts: "
                f"{'; '.join(districts[:4])}. The raw assessment CSV is streamed and not saved locally."
            ),
            "retrieved_context_id": "dese_assessment_index:summary",
            "retrieved_source": "dese_assessment_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the selected local DESE/Missouri assessment aggregate index.",
            "citations": self.citation(matched_rows=payload.get("record_count", 0)),
            "source_rows": [],
        }

    def target_for_question(self, question: str) -> tuple[str, str | None]:
        school = best_named_match(question, self.payload().get("selected_schools", []))
        if school:
            return "School", school
        district = best_named_match(question, self.payload().get("selected_districts", []))
        if district:
            return "District", district
        return "State", None

    def row_for(
        self,
        entity: str,
        name: str | None,
        content_area: str,
        grade_level: str,
        metric: str,
    ) -> dict[str, Any] | None:
        name_norm = normalize_text(name or "")
        for row in self.records():
            if row.get("entity") != entity:
                continue
            if entity == "District" and row.get("district_norm") != name_norm:
                continue
            if entity == "School" and row.get("school_norm") != name_norm:
                continue
            if row.get("content_area") != content_area:
                continue
            if row.get("grade_level") != grade_level:
                continue
            if row.get("metric") != metric:
                continue
            return row
        return None

    def missing_answer(self, question: str, detail: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                f"I have a selected 2025 DESE assessment aggregate index, but {detail}. Try asking `What percent of "
                "Missouri students were proficient in grade 3 ELA in 2025?`, `What percent of Columbia 93 students "
                "were proficient in math in 2025?`, or `What percent of Rock Bridge Sr. High students were proficient "
                "in English II?`"
            ),
            "retrieved_context_id": "dese_assessment_index:no_match",
            "retrieved_source": "dese_assessment_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "No row matched the selected DESE/Missouri assessment aggregate index.",
            "citations": self.citation(matched_rows=0),
            "source_rows": [],
        }

    def exact_answer(
        self,
        question: str,
        entity: str,
        name: str | None,
        content_area: str,
        grade_level: str,
        rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        location = "Missouri statewide" if entity == "State" else clean_text(name)
        if len(rows) == 2:
            proficient = next(row for row in rows if row["metric"] == "% Proficient")
            advanced = next(row for row in rows if row["metric"] == "% Advanced")
            if proficient["value_percent"] is None or advanced["value_percent"] is None:
                value_text = "suppressed or not listed"
            else:
                value_text = format_percent(proficient["value_percent"] + advanced["value_percent"])
            answer = (
                f"The indexed 2025 assessment rows list {location} All Students {content_area}, grade {grade_level}, "
                f"as {format_percent(proficient['value_percent'])} Proficient and "
                f"{format_percent(advanced['value_percent'])} Advanced, or {value_text} Proficient or Advanced combined. "
                f"N-size: {format_count(proficient.get('n_size'))}."
            )
        else:
            row = rows[0]
            metric_label = row["metric"].replace("% ", "")
            answer = (
                f"The indexed 2025 assessment rows list {location} All Students {content_area}, grade {grade_level}, "
                f"as {format_percent(row['value_percent'])} {metric_label}. N-size: {format_count(row.get('n_size'))}."
            )
        answer += " This is an aggregate assessment result, not student-level data."
        return {
            "question": question,
            "answer": answer,
            "retrieved_context_id": f"dese_assessment_index:{entity}:{normalize_text(name or 'state')}:{content_area}:{grade_level}",
            "retrieved_source": "dese_assessment_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the selected local DESE/Missouri assessment aggregate index.",
            "citations": self.citation(matched_rows=len(rows)),
            "source_rows": [{"source_file": row["download_url"], "values": row} for row in rows],
        }

    def answer(self, question: str) -> dict[str, Any] | None:
        if not self.available():
            return self.unavailable_answer(question)
        if asks_for_summary(question):
            return self.summary_answer(question)
        content_area = content_area_for_question(question)
        if content_area is None:
            return self.missing_answer(question, "I could not identify a supported content area such as ELA, math, science, or social studies")
        grade_level = grade_for_question(question)
        entity, name = self.target_for_question(question)
        rows: list[dict[str, Any]] = []
        for metric in metrics_for_question(question):
            row = self.row_for(entity, name, content_area, grade_level, metric)
            if row is None:
                return self.missing_answer(question, f"I could not match {entity.lower()} {name or 'statewide'} / {content_area} / grade {grade_level} / {metric}")
            rows.append(row)
        return self.exact_answer(question, entity, name, content_area, grade_level, rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--max-source-mb", type=float, default=250.0)
    args = parser.parse_args()
    payload = build_dese_assessment_index(force=args.force, max_source_mb=args.max_source_mb)
    print(
        json.dumps(
            {
                "source_row_count": payload.get("source_row_count"),
                "record_count": payload.get("record_count"),
                "kept_entity_counts": payload.get("kept_entity_counts"),
                "source_file_size_mb_estimate": payload.get("source_files", {})
                .get("assessment_csv", {})
                .get("source_file_size_mb_estimate"),
                "elapsed_seconds": payload.get("elapsed_seconds"),
                "index_path": payload.get("index_path"),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
