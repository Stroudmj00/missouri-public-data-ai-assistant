"""Build and query selected aggregate Missouri public-health data."""

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
RAW_DIR = PROJECT_ROOT / "data" / "raw_public" / "data_mo_health"
INDEX_PATH = RAW_DIR / "data_mo_health_index.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "data_mo_health_index_report.json"
DATASET_ID = "fk75-fa28"
DATASET_NAME = "Missouri Communicable Disease Report (2026)"
DATA_URL = f"https://data.mo.gov/resource/{DATASET_ID}.json"
LANDING_PAGE = f"https://data.mo.gov/d/{DATASET_ID}"
METADATA_URL = f"https://data.mo.gov/api/views/{DATASET_ID}.json"

METRICS = {
    "current_week_ytd": "current week year-to-date count",
    "current_week_minus_1_ytd": "previous week year-to-date count",
    "current_week_minus_2_ytd": "two-weeks-ago year-to-date count",
    "five_year_median": "5-year median",
    "change_from_last_week_to_current_week": "change from previous week to current week",
    "change_from_current_week_to_5_yr_median": "change from current week to 5-year median",
    "rate_per_100k": "rate per 100k",
}

GENERIC_DISEASE_TOKENS = {
    "CONDITION",
    "COUNT",
    "CURRENT",
    "DISEASE",
    "DISEASES",
    "HEALTH",
    "MISSOURI",
    "RATE",
    "REPORT",
    "WEEK",
    "YTD",
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
        "E COLI": "ECOLI",
        "STREP PNEUMONIAE": "STREPTOCOCCUS PNEUMONIAE",
    }
    for source, target in replacements.items():
        cleaned = cleaned.replace(source, target)
    return re.sub(r"\s+", " ", cleaned).strip()


def disease_tokens(value: str) -> set[str]:
    return {token for token in normalize_text(value).split() if token not in GENERIC_DISEASE_TOKENS}


def parse_number(value: Any) -> float | None:
    if value is None:
        return None
    cleaned = str(value).replace(",", "").strip()
    if re.fullmatch(r"-?\d+(?:\.\d+)?", cleaned):
        return float(cleaned)
    return None


def format_number(value: float | int | None, decimals: int | None = None) -> str:
    if value is None:
        return "not listed"
    if decimals is not None:
        return f"{float(value):.{decimals}f}"
    if float(value).is_integer():
        return f"{int(value):,}"
    return f"{float(value):,.4g}"


def rows_updated_label(value: Any) -> str | None:
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).replace(microsecond=0).isoformat()


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    condition = clean_text(row.get("disease_or_condition"))
    record = {
        "disease_or_condition": condition,
        "condition_norm": normalize_text(condition),
        "current_week_ytd": parse_number(row.get("current_week_ytd")),
        "current_week_minus_1_ytd": parse_number(row.get("current_week_minus_1_ytd")),
        "current_week_minus_2_ytd": parse_number(row.get("current_week_minus_2_ytd")),
        "five_year_1st_quartile": parse_number(row.get("_5_yr_1st_quartile")),
        "five_year_median": parse_number(row.get("_5_yr_median")),
        "five_year_3rd_quartile": parse_number(row.get("_5_yr_3rd_quartile")),
        "change_from_last_week_to_current_week": parse_number(row.get("change_from_last_week_to_current_week")),
        "change_from_current_week_to_5_yr_median": parse_number(row.get("change_from_current_week_to_5_yr_median")),
        "rate_per_100k": parse_number(row.get("rate_per_100k")),
        "source_url": DATA_URL,
        "landing_page": LANDING_PAGE,
    }
    record["raw_values"] = {
        "current_week_ytd": clean_text(row.get("current_week_ytd")),
        "current_week_minus_1_ytd": clean_text(row.get("current_week_minus_1_ytd")),
        "current_week_minus_2_ytd": clean_text(row.get("current_week_minus_2_ytd")),
        "5_yr_median": clean_text(row.get("_5_yr_median")),
        "change_from_last_week_to_current_week": clean_text(row.get("change_from_last_week_to_current_week")),
        "change_from_current_week_to_5_yr_median": clean_text(row.get("change_from_current_week_to_5_yr_median")),
        "rate_per_100k": clean_text(row.get("rate_per_100k")),
    }
    return record


def build_data_mo_health_index(force: bool = False) -> dict[str, Any]:
    if INDEX_PATH.exists() and not force:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (compatible; MissouriPublicDataChat/1.0; +https://github.com/Stroudmj00/missouri-tiny-llm-case-study)",
            "Accept": "application/json,*/*;q=0.8",
        }
    )
    start = time.perf_counter()
    metadata_response = session.get(METADATA_URL, timeout=60)
    metadata_response.raise_for_status()
    metadata = metadata_response.json()
    response = session.get(DATA_URL, params={"$limit": 50000}, timeout=90)
    response.raise_for_status()
    raw_text = response.text
    raw_rows = response.json()
    records = [normalize_row(row) for row in raw_rows]
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    write_json(RAW_DIR / "communicable_disease_report_2026.json", raw_rows)
    year_match = re.search(r"\((\d{4})\)", metadata.get("name", DATASET_NAME))
    payload = {
        "generated_at_utc": utc_now(),
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "source": DATASET_NAME,
        "source_url": DATA_URL,
        "landing_page": LANDING_PAGE,
        "metadata_url": METADATA_URL,
        "index_path": str(INDEX_PATH.relative_to(PROJECT_ROOT)),
        "dataset_id": DATASET_ID,
        "report_year": int(year_match.group(1)) if year_match else 2026,
        "rows_updated_at_utc": rows_updated_label(metadata.get("rowsUpdatedAt")),
        "bytes": len(raw_text.encode("utf-8")),
        "sha256": sha256_text(raw_text),
        "record_count": len(records),
        "columns": [column.get("name") for column in metadata.get("columns", []) if column.get("name")],
        "records": records,
    }
    write_json(INDEX_PATH, payload)
    top_current = sorted(
        [record for record in records if record.get("current_week_ytd") is not None],
        key=lambda item: item["current_week_ytd"],
        reverse=True,
    )[:8]
    write_json(
        REPORT_PATH,
        {
            "generated_at_utc": payload["generated_at_utc"],
            "elapsed_seconds": payload["elapsed_seconds"],
            "source": payload["source"],
            "source_url": payload["source_url"],
            "landing_page": payload["landing_page"],
            "index_path": payload["index_path"],
            "dataset_id": payload["dataset_id"],
            "report_year": payload["report_year"],
            "rows_updated_at_utc": payload["rows_updated_at_utc"],
            "bytes": payload["bytes"],
            "sha256": payload["sha256"],
            "record_count": payload["record_count"],
            "top_current_week_ytd": [
                {
                    "disease_or_condition": record["disease_or_condition"],
                    "current_week_ytd": record["current_week_ytd"],
                    "rate_per_100k": record["rate_per_100k"],
                }
                for record in top_current
            ],
        },
    )
    return payload


def metric_for_question(question: str) -> tuple[str, str, int | None]:
    lowered = question.lower()
    if "rate" in lowered or "per 100k" in lowered or "per 100,000" in lowered:
        return "rate_per_100k", METRICS["rate_per_100k"], 2
    if "previous week" in lowered or "last week" in lowered:
        if "change" in lowered:
            return (
                "change_from_last_week_to_current_week",
                METRICS["change_from_last_week_to_current_week"],
                4,
            )
        return "current_week_minus_1_ytd", METRICS["current_week_minus_1_ytd"], None
    if "5-year median" in lowered or "five-year median" in lowered or "5 yr median" in lowered:
        if "change" in lowered:
            return (
                "change_from_current_week_to_5_yr_median",
                METRICS["change_from_current_week_to_5_yr_median"],
                4,
            )
        return "five_year_median", METRICS["five_year_median"], None
    return "current_week_ytd", METRICS["current_week_ytd"], None


def asks_for_top(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["top", "highest", "largest", "most"])


def asks_for_lowest(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["lowest", "smallest", "fewest"])


class DataMoHealthIndex:
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
                "dataset": payload.get("source", DATASET_NAME),
                "category": "Public health",
                "kind": "aggregate communicable-disease report row",
                "lookup_table": "data_mo_health_index",
                "year": payload.get("report_year"),
                "year_range": str(payload.get("report_year")),
                "source_files": [
                    {
                        "category": "communicable_disease_report",
                        "category_label": payload.get("source", DATASET_NAME),
                        "file_name": payload.get("source_url", DATA_URL),
                        "row_count": payload.get("record_count"),
                        "bytes": payload.get("bytes"),
                        "sha256": payload.get("sha256"),
                    },
                    {
                        "category": "communicable_disease_report",
                        "category_label": "data.mo.gov landing page",
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

    def summary_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        return {
            "question": question,
            "answer": (
                f"The selected public-health exact lookup layer indexes {payload.get('source', DATASET_NAME)} from data.mo.gov. "
                f"It contains {payload.get('record_count', 0):,} aggregate disease/condition rows for report year "
                f"{payload.get('report_year')}. Rows updated at: {payload.get('rows_updated_at_utc')}. "
                "It can answer current-week YTD counts, previous-week YTD counts, 5-year median values, rate per 100k, "
                "and ranked aggregate condition questions. It is aggregate public-health reporting, not medical advice."
            ),
            "retrieved_context_id": "data_mo_health_index:summary",
            "retrieved_source": "data_mo_health_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local data.mo.gov public-health index.",
            "citations": self.citation(matched_rows=payload.get("record_count", 0)),
            "source_rows": [],
        }

    def unavailable_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "The selected data.mo.gov health index has not been built yet. Run "
                "`python scripts/build_data_mo_health_index.py --force` to download the public aggregate health dataset and build exact lookups."
            ),
            "retrieved_context_id": "data_mo_health_index:missing",
            "retrieved_source": "data_mo_health_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "The health route exists, but the local ignored index is missing.",
            "citations": [],
            "source_rows": [],
        }

    def find_condition(self, question: str) -> dict[str, Any] | None:
        question_norm = normalize_text(question)
        question_tokens = disease_tokens(question)
        candidates: list[tuple[int, dict[str, Any]]] = []
        for record in self.records():
            condition_norm = record["condition_norm"]
            score = 0
            if condition_norm and condition_norm in question_norm:
                score += 100 + len(condition_norm)
            tokens = disease_tokens(record["disease_or_condition"])
            if tokens and tokens <= question_tokens:
                score += 30 + len(tokens)
            if any(token in question_tokens for token in tokens):
                score += len(tokens & question_tokens)
            if score:
                candidates.append((score, record))
        if not candidates:
            return None
        return sorted(candidates, key=lambda item: item[0], reverse=True)[0][1]

    def condition_answer(self, question: str, record: dict[str, Any]) -> dict[str, Any]:
        metric, metric_label, decimals = metric_for_question(question)
        value = record.get(metric)
        value_text = format_number(value, decimals)
        return {
            "question": question,
            "answer": (
                f"The indexed {DATASET_NAME} lists {record['disease_or_condition']} {metric_label} as {value_text}. "
                f"Current week YTD: {format_number(record.get('current_week_ytd'))}; previous week YTD: "
                f"{format_number(record.get('current_week_minus_1_ytd'))}; 5-year median: {format_number(record.get('five_year_median'))}; "
                f"rate per 100k: {format_number(record.get('rate_per_100k'), 2)}. "
                "This is aggregate surveillance reporting, not medical advice."
            ),
            "retrieved_context_id": f"data_mo_health_index:condition:{record['condition_norm']}:{metric}",
            "retrieved_source": "data_mo_health_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local data.mo.gov public-health index.",
            "citations": self.citation(matched_rows=1),
            "source_rows": [{"source_file": DATA_URL, "values": record}],
        }

    def rank_answer(self, question: str) -> dict[str, Any]:
        metric, metric_label, decimals = metric_for_question(question)
        rows = [record for record in self.records() if record.get(metric) is not None]
        reverse = not asks_for_lowest(question)
        ranked = sorted(rows, key=lambda item: item[metric], reverse=reverse)
        top = ranked[0]
        direction = "highest" if reverse else "lowest"
        rendered = "; ".join(
            f"{record['disease_or_condition']}: {format_number(record.get(metric), decimals)}"
            for record in ranked[:5]
        )
        return {
            "question": question,
            "answer": (
                f"In the indexed {DATASET_NAME}, the {direction} listed {metric_label} is "
                f"{top['disease_or_condition']}: {format_number(top.get(metric), decimals)}. "
                f"Top matching conditions: {rendered}."
            ),
            "retrieved_context_id": f"data_mo_health_index:rank:{metric}:{direction}",
            "retrieved_source": "data_mo_health_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed by ranking aggregate rows in the local data.mo.gov public-health index.",
            "citations": self.citation(matched_rows=len(rows)),
            "source_rows": [{"source_file": DATA_URL, "values": top}],
        }

    def missing_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                f"I have indexed {DATASET_NAME}, but this question did not match a listed disease/condition row or supported ranking. "
                "If you asked about a specific condition, that condition was not found in the indexed report snapshot. "
                "Try a condition name such as anaplasmosis, salmonellosis, pertussis, campylobacteriosis, ehrlichiosis, or ask for the highest current-week YTD count."
            ),
            "retrieved_context_id": "data_mo_health_index:no_match",
            "retrieved_source": "data_mo_health_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Answered from public-health coverage metadata because no exact condition row matched.",
            "citations": self.citation(),
            "source_rows": [],
        }

    def answer(self, question: str) -> dict[str, Any] | None:
        if not self.available():
            return self.unavailable_answer(question)
        lowered = question.lower()
        if (
            re.search(r"\b(public health|health|communicable disease|disease report)\b.*\b(indexed|lookup|data)\b", lowered)
            and not asks_for_top(question)
        ):
            condition = self.find_condition(question)
            if condition is None:
                return self.summary_answer(question)
        if asks_for_top(question) or asks_for_lowest(question):
            return self.rank_answer(question)
        condition = self.find_condition(question)
        if condition is not None:
            return self.condition_answer(question, condition)
        return self.missing_answer(question)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    payload = build_data_mo_health_index(force=args.force)
    print(json.dumps({key: value for key, value in payload.items() if key != "records"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
