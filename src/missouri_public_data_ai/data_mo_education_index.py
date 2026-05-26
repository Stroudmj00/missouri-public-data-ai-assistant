"""Build and query selected Missouri education datasets from data.mo.gov."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw_public" / "data_mo_education"
INDEX_PATH = RAW_DIR / "data_mo_education_index.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "data_mo_education_index_report.json"

SOURCES = {
    "high_school_seniors": {
        "dataset": "Total Number of High School Seniors in Missouri",
        "id": "8yaf-xv66",
        "landing_page": "https://data.mo.gov/d/8yaf-xv66",
        "url": "https://data.mo.gov/resource/8yaf-xv66.json",
        "metric_field": "number_of_seniors",
        "metric_label": "high school seniors",
        "value_label": "senior count",
    },
    "fafsa_completions": {
        "dataset": "Completed FAFSAs Reported to MDHE",
        "id": "t9f4-ncza",
        "landing_page": "https://data.mo.gov/d/t9f4-ncza",
        "url": "https://data.mo.gov/resource/t9f4-ncza.json",
        "metric_field": "number_of_applications",
        "metric_label": "completed FAFSA applications",
        "value_label": "application count",
    },
}

GENERIC_SCHOOL_TOKENS = {
    "ACADEMY",
    "HIGH",
    "HS",
    "SCHOOL",
    "SCHOOLS",
    "SENIOR",
    "SR",
    "JR",
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


def normalize_text(value: str) -> str:
    cleaned = re.sub(r"[^A-Z0-9]+", " ", clean_text(value).upper())
    replacements = {
        " SR ": " SENIOR ",
        " JR ": " JUNIOR ",
        " ST ": " SAINT ",
        " STE ": " SAINTE ",
    }
    normalized = f" {cleaned} "
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    return re.sub(r"\s+", " ", normalized).strip()


def school_tokens(value: str) -> set[str]:
    return {token for token in normalize_text(value).split() if token not in GENERIC_SCHOOL_TOKENS}


def parse_int(value: Any) -> int | None:
    if value is None:
        return None
    cleaned = str(value).replace(",", "").strip()
    if re.fullmatch(r"\d+", cleaned):
        return int(cleaned)
    return None


def value_label(value: int | None, suppressed: bool = False) -> str:
    if value is None:
        return "suppressed or not numeric" if suppressed else "not listed"
    return f"{value:,}"


def download_source(session: requests.Session, source_key: str, force: bool = False) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    spec = SOURCES[source_key]
    target = RAW_DIR / f"{source_key}.json"
    if target.exists() and not force:
        rows = json.loads(target.read_text(encoding="utf-8"))
        text = json.dumps(rows, sort_keys=True)
    else:
        response = session.get(spec["url"], params={"$limit": 50000}, timeout=90)
        response.raise_for_status()
        rows = response.json()
        text = response.text
        write_json(target, rows)
    return rows, {
        "key": source_key,
        "dataset": spec["dataset"],
        "id": spec["id"],
        "url": spec["url"],
        "landing_page": spec["landing_page"],
        "local_file": str(target.relative_to(PROJECT_ROOT)),
        "bytes": len(text.encode("utf-8")),
        "sha256": sha256_text(text),
        "row_count": len(rows),
    }


def normalize_row(source_key: str, row: dict[str, Any]) -> dict[str, Any]:
    spec = SOURCES[source_key]
    raw_value = row.get(spec["metric_field"])
    parsed_value = parse_int(raw_value)
    school_name = clean_text(row.get("school_name"))
    return {
        "source_key": source_key,
        "dataset": spec["dataset"],
        "dataset_id": spec["id"],
        "source_url": spec["url"],
        "landing_page": spec["landing_page"],
        "ncessch": clean_text(row.get("ncessch")),
        "school_name": school_name,
        "school_norm": normalize_text(school_name),
        "district": clean_text(row.get("district")),
        "school_year": int(row.get("school_year")),
        "metric_field": spec["metric_field"],
        "metric_label": spec["metric_label"],
        "metric_value": parsed_value,
        "metric_raw": clean_text(raw_value),
        "suppressed": parsed_value is None and bool(clean_text(raw_value)),
        "last_updated": clean_text(row.get("lastupdated")),
        "record_id": clean_text(row.get("recordid")),
    }


def build_data_mo_education_index(force: bool = False) -> dict[str, Any]:
    if INDEX_PATH.exists() and not force:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (compatible; MissouriPublicDataAssistant/1.0)",
            "Accept": "application/json,*/*;q=0.8",
        }
    )
    start = time.perf_counter()
    files: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    for source_key in SOURCES:
        rows, file_info = download_source(session, source_key, force=force)
        parsed = [normalize_row(source_key, row) for row in rows]
        records.extend(parsed)
        file_info["parsed_record_count"] = len(parsed)
        file_info["year_range"] = f"{min(row['school_year'] for row in parsed)}-{max(row['school_year'] for row in parsed)}"
        file_info["suppressed_count"] = sum(1 for row in parsed if row["suppressed"])
        files.append(file_info)

    by_source: dict[str, list[dict[str, Any]]] = {
        source_key: [record for record in records if record["source_key"] == source_key]
        for source_key in SOURCES
    }
    payload = {
        "generated_at_utc": utc_now(),
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "source": "Selected Missouri education datasets from data.mo.gov",
        "index_path": str(INDEX_PATH.relative_to(PROJECT_ROOT)),
        "file_count": len(files),
        "record_count": len(records),
        "school_count": len({record["school_norm"] for record in records}),
        "files": files,
        "source_summaries": {
            source_key: {
                "dataset": SOURCES[source_key]["dataset"],
                "row_count": len(source_records),
                "year_range": f"{min(row['school_year'] for row in source_records)}-{max(row['school_year'] for row in source_records)}",
                "latest_year": max(row["school_year"] for row in source_records),
                "latest_year_rows": sum(1 for row in source_records if row["school_year"] == max(item["school_year"] for item in source_records)),
                "latest_year_total": sum(row["metric_value"] or 0 for row in source_records if row["school_year"] == max(item["school_year"] for item in source_records)),
                "suppressed_count": sum(1 for row in source_records if row["suppressed"]),
            }
            for source_key, source_records in by_source.items()
        },
        "records": records,
    }
    write_json(INDEX_PATH, payload)
    write_json(
        REPORT_PATH,
        {
            "generated_at_utc": payload["generated_at_utc"],
            "elapsed_seconds": payload["elapsed_seconds"],
            "source": payload["source"],
            "index_path": payload["index_path"],
            "file_count": payload["file_count"],
            "record_count": payload["record_count"],
            "school_count": payload["school_count"],
            "files": files,
            "source_summaries": payload["source_summaries"],
        },
    )
    return payload


def years_in_question(question: str) -> list[int]:
    return sorted({int(year) for year in re.findall(r"\b(20\d{2}|19\d{2})\b", question)})


def asks_for_top(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["top", "highest", "largest", "most"])


def asks_for_lowest(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["lowest", "smallest", "fewest"])


def metric_source_for_question(question: str) -> str:
    lowered = question.lower()
    if "fafsa" in lowered or "application" in lowered:
        return "fafsa_completions"
    return "high_school_seniors"


class DataMoEducationIndex:
    def __init__(self, path: Path = INDEX_PATH) -> None:
        self.path = path
        self._payload: dict[str, Any] | None = None

    def available(self) -> bool:
        return self.path.exists() and self.path.stat().st_size > 0

    def payload(self) -> dict[str, Any]:
        if self._payload is None:
            self._payload = json.loads(self.path.read_text(encoding="utf-8")) if self.available() else {}
        return self._payload

    def records(self, source_key: str | None = None) -> list[dict[str, Any]]:
        records = list(self.payload().get("records", []))
        if source_key:
            return [record for record in records if record["source_key"] == source_key]
        return records

    def file_info(self, source_key: str) -> dict[str, Any] | None:
        for item in self.payload().get("files", []):
            if item.get("key") == source_key:
                return item
        return None

    def citation(self, source_key: str, matched_rows: int = 0) -> list[dict[str, Any]]:
        file_info = self.file_info(source_key) or {}
        return [
            {
                "dataset": file_info.get("dataset", SOURCES[source_key]["dataset"]),
                "category": "Education",
                "kind": "data.mo.gov education dataset row",
                "lookup_table": "data_mo_education_index",
                "year": None,
                "year_range": file_info.get("year_range"),
                "source_files": [
                    {
                        "category": source_key,
                        "category_label": file_info.get("dataset"),
                        "file_name": file_info.get("url"),
                        "row_count": file_info.get("row_count"),
                        "bytes": file_info.get("bytes"),
                        "sha256": file_info.get("sha256"),
                    },
                    {
                        "category": source_key,
                        "category_label": "data.mo.gov landing page",
                        "file_name": file_info.get("landing_page"),
                        "row_count": None,
                        "bytes": None,
                        "sha256": None,
                    },
                ],
                "source_file_count": 2,
                "source_rows": file_info.get("row_count"),
                "matched_rows": matched_rows,
            }
        ]

    def coverage_citation(self) -> list[dict[str, Any]]:
        source_files = [
            {
                "category": item.get("key"),
                "category_label": item.get("dataset"),
                "file_name": item.get("url"),
                "row_count": item.get("row_count"),
                "bytes": item.get("bytes"),
                "sha256": item.get("sha256"),
            }
            for item in self.payload().get("files", [])
        ]
        return [
            {
                "dataset": "Selected Missouri education datasets from data.mo.gov",
                "category": "Education",
                "kind": "education dataset coverage",
                "lookup_table": "data_mo_education_index",
                "year": None,
                "year_range": None,
                "source_files": source_files,
                "source_file_count": len(source_files),
                "source_rows": self.payload().get("record_count"),
                "matched_rows": self.payload().get("record_count"),
            }
        ]

    def summary_answer(self, question: str) -> dict[str, Any]:
        summaries = self.payload().get("source_summaries", {})
        senior = summaries.get("high_school_seniors", {})
        fafsa = summaries.get("fafsa_completions", {})
        return {
            "question": question,
            "answer": (
                "The education exact lookup layer indexes two public data.mo.gov education datasets: "
                f"{senior.get('dataset')} ({senior.get('row_count', 0):,} rows, years {senior.get('year_range')}) and "
                f"{fafsa.get('dataset')} ({fafsa.get('row_count', 0):,} rows, years {fafsa.get('year_range')}). "
                f"Total indexed education rows: {self.payload().get('record_count', 0):,} across "
                f"{self.payload().get('school_count', 0):,} unique normalized school names. "
                "It can answer school/year high-school-senior counts, completed FAFSA application counts, and top-school rankings. "
                "FAFSA rows with '*' are treated as suppressed/not numeric."
            ),
            "retrieved_context_id": "data_mo_education_index:summary",
            "retrieved_source": "data_mo_education_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from local copies of selected public data.mo.gov education datasets.",
            "citations": self.coverage_citation(),
            "source_rows": [],
        }

    def unavailable_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "The data.mo.gov education index has not been built yet. Run "
                "`python scripts/build_data_mo_education_index.py --force` to download the public education datasets and build exact lookups."
            ),
            "retrieved_context_id": "data_mo_education_index:missing",
            "retrieved_source": "data_mo_education_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "The education route exists, but the local ignored index is missing.",
            "citations": [],
            "source_rows": [],
        }

    def latest_year(self, source_key: str) -> int | None:
        years = [record["school_year"] for record in self.records(source_key)]
        return max(years) if years else None

    def find_school_rows(self, question: str, source_key: str) -> list[dict[str, Any]]:
        question_norm = normalize_text(question)
        question_tokens = school_tokens(question)
        candidates: list[tuple[int, dict[str, Any]]] = []
        for record in self.records(source_key):
            school_norm = record["school_norm"]
            score = 0
            if school_norm and school_norm in question_norm:
                score += 100 + len(school_norm)
            tokens = school_tokens(record["school_name"])
            if len(tokens) >= 2 and tokens <= question_tokens:
                score += 20 + len(tokens)
            if score:
                candidates.append((score, record))
        if not candidates:
            return []
        best_norm = sorted(candidates, key=lambda item: item[0], reverse=True)[0][1]["school_norm"]
        return [record for _, record in candidates if record["school_norm"] == best_norm]

    def row_answer(self, question: str, source_key: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
        requested_years = years_in_question(question)
        selected_rows = rows
        if requested_years:
            selected_rows = [row for row in rows if row["school_year"] in requested_years]
        else:
            latest = max(row["school_year"] for row in rows)
            selected_rows = [row for row in rows if row["school_year"] == latest]
        if not selected_rows:
            available = sorted({row["school_year"] for row in rows})
            return {
                "question": question,
                "answer": (
                    f"I found {rows[0]['school_name']} in the indexed education source, but not for requested year(s) "
                    f"{', '.join(str(year) for year in requested_years)}. Available years for this school/source: "
                    f"{available[0]}-{available[-1]}."
                ),
                "retrieved_context_id": f"data_mo_education_index:missing_year:{source_key}:{rows[0]['school_norm']}",
                "retrieved_source": "data_mo_education_lookup_index",
                "retrieval_score": 1.0,
                "used_model": False,
                "model": "deterministic_public_lookup",
                "source_note": "Answered from education coverage metadata because no exact school/year row matched.",
                "citations": self.citation(source_key),
                "source_rows": [],
            }
        row = sorted(selected_rows, key=lambda item: item["school_year"], reverse=True)[0]
        value_text = value_label(row["metric_value"], row["suppressed"])
        district_text = f" in district {row['district']}" if row.get("district") else ""
        suppressed_note = " The source value is suppressed or not numeric." if row["suppressed"] else ""
        return {
            "question": question,
            "answer": (
                f"The indexed {row['dataset']} source lists {row['school_name']}{district_text} with "
                f"{value_text} {row['metric_label']} for school year {row['school_year']}. "
                f"Last updated in source: {row['last_updated']}.{suppressed_note}"
            ),
            "retrieved_context_id": f"data_mo_education_index:{source_key}:{row['school_norm']}:{row['school_year']}",
            "retrieved_source": "data_mo_education_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local data.mo.gov education index.",
            "citations": self.citation(source_key, matched_rows=1),
            "source_rows": [{"source_file": SOURCES[source_key]["url"], "values": row}],
        }

    def rank_answer(self, question: str, source_key: str) -> dict[str, Any]:
        requested_years = years_in_question(question)
        year = requested_years[-1] if requested_years else self.latest_year(source_key)
        rows = [row for row in self.records(source_key) if row["school_year"] == year and row["metric_value"] is not None]
        if not rows:
            return {
                "question": question,
                "answer": f"I do not have numeric indexed education rows for {SOURCES[source_key]['dataset']} in {year}.",
                "retrieved_context_id": f"data_mo_education_index:no_rank:{source_key}:{year}",
                "retrieved_source": "data_mo_education_lookup_index",
                "retrieval_score": 1.0,
                "used_model": False,
                "model": "deterministic_public_lookup",
                "source_note": "Answered from education coverage metadata because no numeric rows were available.",
                "citations": self.citation(source_key),
                "source_rows": [],
            }
        reverse = not asks_for_lowest(question)
        ranked = sorted(rows, key=lambda item: item["metric_value"] or 0, reverse=reverse)
        top = ranked[0]
        direction = "highest" if reverse else "lowest"
        rendered = "; ".join(
            f"{row['school_name']}: {row['metric_value']:,}" for row in ranked[:5]
        )
        return {
            "question": question,
            "answer": (
                f"In the indexed {top['dataset']} source for school year {year}, the {direction} listed "
                f"{top['metric_label']} value is {top['school_name']}: {top['metric_value']:,}. "
                f"Top matching schools: {rendered}."
            ),
            "retrieved_context_id": f"data_mo_education_index:rank:{source_key}:{year}:{direction}",
            "retrieved_source": "data_mo_education_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed by ranking numeric rows in the local data.mo.gov education index.",
            "citations": self.citation(source_key, matched_rows=len(rows)),
            "source_rows": [{"source_file": SOURCES[source_key]["url"], "values": top}],
        }

    def missing_answer(self, question: str, source_key: str) -> dict[str, Any]:
        summary = self.payload().get("source_summaries", {}).get(source_key, {})
        return {
            "question": question,
            "answer": (
                f"I have indexed {SOURCES[source_key]['dataset']}, but I could not match a school name or supported ranking request. "
                f"Indexed years: {summary.get('year_range')}; indexed rows: {summary.get('row_count', 0):,}. "
                "Try a specific school and school year, or ask for the highest listed value in a year."
            ),
            "retrieved_context_id": f"data_mo_education_index:no_match:{source_key}",
            "retrieved_source": "data_mo_education_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Answered from education coverage metadata because no exact school/year row matched.",
            "citations": self.citation(source_key),
            "source_rows": [],
        }

    def answer(self, question: str) -> dict[str, Any] | None:
        if not self.available():
            return self.unavailable_answer(question)
        lowered = question.lower()
        if (
            re.search(r"\b(what|which|show|list)\b.*\b(education|school)\b.*\b(data|indexed|connected|sources?)\b", lowered)
            or re.search(r"\beducation\b.*\b(index|indexed|lookup|coverage)\b", lowered)
        ) and not any(term in lowered for term in ["senior", "fafsa", "application", "highest", "top"]):
            return self.summary_answer(question)
        source_key = metric_source_for_question(question)
        if asks_for_top(question) or asks_for_lowest(question):
            return self.rank_answer(question, source_key)
        rows = self.find_school_rows(question, source_key)
        if rows:
            return self.row_answer(question, source_key, rows)
        return self.missing_answer(question, source_key)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    payload = build_data_mo_education_index(force=args.force)
    print(json.dumps({key: value for key, value in payload.items() if key != "records"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
