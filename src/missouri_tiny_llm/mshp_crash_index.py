"""Build and query aggregate MSHP crash-statistics tables."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw_public" / "mshp_crash"
INDEX_PATH = RAW_DIR / "mshp_crash_index.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "mshp_crash_index_report.json"
BASE_URL = "https://www.mshp.dps.mo.gov/MSHPWeb/SAC/"


@dataclass(frozen=True)
class CrashFileSpec:
    key: str
    label: str
    file_name: str
    estimated_kb: int

    @property
    def url(self) -> str:
        return f"{BASE_URL}{self.file_name}"


CRASH_FILES: tuple[CrashFileSpec, ...] = (
    CrashFileSpec(
        "severity",
        "Number of Persons Killed/Injured, Fatal/Personal Injury and Property Damage Crashes by Year",
        "CrashesSeverity.xls",
        41,
    ),
    CrashFileSpec("rates", "Death and Injury Rate by Year", "CrashesRates.xls", 32),
    CrashFileSpec("circumstances", "Circumstances Involved in Crash by Year", "CrashesCircumstances.xls", 78),
    CrashFileSpec("speed", "Crashes by Speed Involvement", "CrashesSpeed.xls", 34),
    CrashFileSpec("alcohol", "Crash by Alcohol Involvement", "CrashesAlcohol.xls", 31),
    CrashFileSpec("young_driver", "Crash by Young Driver Involvement (Under 21 Years Old)", "CrashesYoung.xls", 34),
    CrashFileSpec("older_driver", "Crash by Older Driver Involvement (55 Years Old and Up)", "CrashesOlder.xls", 38),
    CrashFileSpec("motorcycle", "Motorcycle Crashes", "CrashesMotorcycle.xls", 38),
    CrashFileSpec("commercial_vehicle", "Crashes by Commercial Motor Vehicle Involvement", "CrashesCMV.xls", 34),
)

SOURCE_TERMS = {
    "alcohol": ("alcohol", "drunk", "dui", "dwi"),
    "speed": ("speed", "speeding"),
    "young_driver": ("young", "under 21", "under twenty one"),
    "older_driver": ("older", "mature", "55", "fifty five"),
    "motorcycle": ("motorcycle", "motorcyclist"),
    "commercial_vehicle": ("commercial", "cmv", "truck"),
    "rates": ("rate", "death rate", "injury rate"),
    "circumstances": ("circumstance", "factor", "involved"),
    "severity": ("person", "killed", "injured", "fatal/pi", "property damage"),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def clean_label(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def normalize_key(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return re.sub(r"_+", "_", cleaned)


def numeric_year(value: Any) -> int | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, str) and not re.fullmatch(r"\d{4}(?:\.0)?", value.strip()):
        return None
    try:
        year = int(float(value))
    except (TypeError, ValueError):
        return None
    return year if 1900 <= year <= 2100 else None


def numeric_value(value: Any) -> int | float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        number = float(str(value).replace(",", ""))
    except ValueError:
        return None
    if number.is_integer():
        return int(number)
    return round(number, 4)


def nearest_title(df: pd.DataFrame, header_row: int) -> str:
    for row_index in range(header_row - 1, -1, -1):
        labels = [clean_label(value) for value in df.iloc[row_index].tolist()]
        labels = [label for label in labels if label]
        if labels and not labels[0].lower().startswith("year") and ":" not in labels[0]:
            return labels[0]
    return "MSHP crash statistics"


def is_header_row(df: pd.DataFrame, row_index: int) -> bool:
    if row_index + 1 >= len(df):
        return False
    next_year = numeric_year(df.iloc[row_index + 1, 0])
    if next_year is None:
        return False
    labels = [clean_label(value) for value in df.iloc[row_index].tolist()]
    nonempty = [label for label in labels if label]
    if len(nonempty) < 2:
        return False
    return any(re.search(r"\b(year|crashes|persons|rate|damage|involved)\b", label, flags=re.I) for label in nonempty)


def parse_workbook(path: Path, spec: CrashFileSpec) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    workbook = pd.ExcelFile(path)
    for sheet_name in workbook.sheet_names:
        df = pd.read_excel(path, sheet_name=sheet_name, header=None)
        if df.empty:
            continue
        for header_row in range(len(df) - 1):
            if not is_header_row(df, header_row):
                continue
            headers = [clean_label(value) for value in df.iloc[header_row].tolist()]
            if not headers or not headers[0]:
                headers[0] = "Year"
            table_label = nearest_title(df, header_row)
            for data_row in range(header_row + 1, len(df)):
                year = numeric_year(df.iloc[data_row, 0])
                if year is None:
                    break
                for column_index, metric_label in enumerate(headers[1:], start=1):
                    if not metric_label:
                        continue
                    value = numeric_value(df.iloc[data_row, column_index])
                    if value is None:
                        continue
                    records.append(
                        {
                            "source_key": spec.key,
                            "source_label": spec.label,
                            "file_name": spec.file_name,
                            "url": spec.url,
                            "sheet_name": sheet_name,
                            "table_label": table_label,
                            "year": year,
                            "metric_key": normalize_key(metric_label),
                            "metric_label": metric_label,
                            "value": value,
                        }
                    )
    return records


def download_file(session: requests.Session, spec: CrashFileSpec, force: bool = False) -> Path:
    path = RAW_DIR / spec.file_name
    if path.exists() and not force:
        return path
    response = session.get(spec.url, timeout=60)
    response.raise_for_status()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(response.content)
    return path


def build_mshp_crash_index(force: bool = False, delay_seconds: float = 0.05) -> dict[str, Any]:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (compatible; MissouriPublicDataChat/1.0; +https://github.com/Stroudmj00/missouri-tiny-llm-case-study)",
            "Accept": "application/vnd.ms-excel,text/html;q=0.8,*/*;q=0.7",
        }
    )
    start = time.perf_counter()
    all_records: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []
    for spec in CRASH_FILES:
        path = download_file(session, spec, force=force)
        records = parse_workbook(path, spec)
        all_records.extend(records)
        years = sorted({record["year"] for record in records})
        files.append(
            {
                "key": spec.key,
                "label": spec.label,
                "file_name": spec.file_name,
                "url": spec.url,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "record_count": len(records),
                "min_year": years[0] if years else None,
                "max_year": years[-1] if years else None,
                "metric_count": len({record["metric_key"] for record in records}),
            }
        )
        if delay_seconds > 0:
            time.sleep(delay_seconds)
    payload = {
        "generated_at_utc": utc_now(),
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "source": "Missouri State Highway Patrol Statistical Analysis Center",
        "source_url": "https://www.mshp.dps.mo.gov/MSHPWeb/SAC/data_960grid.html",
        "index_path": str(INDEX_PATH.relative_to(PROJECT_ROOT)),
        "file_count": len(files),
        "record_count": len(all_records),
        "files": files,
        "records": all_records,
    }
    write_json(INDEX_PATH, payload)
    write_json(
        REPORT_PATH,
        {
            "generated_at_utc": payload["generated_at_utc"],
            "elapsed_seconds": payload["elapsed_seconds"],
            "source": payload["source"],
            "source_url": payload["source_url"],
            "index_path": payload["index_path"],
            "file_count": payload["file_count"],
            "record_count": payload["record_count"],
            "files": files,
        },
    )
    return payload


def value_label(value: int | float) -> str:
    if isinstance(value, int):
        return f"{value:,}"
    return f"{value:,.4f}".rstrip("0").rstrip(".")


def question_terms(question: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", question.lower()) if len(token) > 1}


def years_in_text(question: str) -> list[int]:
    return [int(match) for match in re.findall(r"\b((?:19|20)\d{2})\b", question)]


def direct_metric_bonus(record: dict[str, Any], lowered: str) -> int:
    metric = record["metric_label"].lower()
    table = record["table_label"].lower()
    source = record["source_key"]
    score = 0
    if "fatal crash" in lowered and metric == "fatal crashes":
        score += 130
    elif "fatal crash" in lowered and metric != "fatal crashes":
        score -= 60
    if ("personal injury" in lowered or "injury crash" in lowered) and metric == "personal injury crashes":
        score += 130
    elif ("personal injury" in lowered or "injury crash" in lowered) and metric != "personal injury crashes":
        score -= 60
    if "property damage" in lowered and metric == "property damage":
        score += 80
    if ("death rate" in lowered or "fatality rate" in lowered) and metric == "death rate":
        score += 90
    if "injury rate" in lowered and metric == "injury rate":
        score += 90
    if any(term in lowered for term in ["killed", "fatalities", "fatality", "deaths", "people died", "persons killed"]) and metric == "persons killed":
        score += 75
    if any(term in lowered for term in ["injured", "injuries", "persons injured", "people hurt"]) and metric == "persons injured":
        score += 75
    if "alcohol" in lowered and metric == "alcohol involved":
        score += 85
    if "speed" in lowered and metric == "speed involved":
        score += 85
    if "young" in lowered and metric == "young driver involved":
        score += 85
    if ("older" in lowered or "mature" in lowered) and metric == "older driver involved":
        score += 85
    if ("commercial" in lowered or "cmv" in lowered) and metric == "commercial vehicle involved":
        score += 85
    if "motorcycle" in lowered and metric == "motorcycle involved":
        score += 85
    for term in SOURCE_TERMS.get(source, ()):
        if term in lowered:
            score += 20
    if source in {"severity", "rates", "circumstances"} and source in lowered:
        score += 20
    if "crash" in lowered and "crash" in table:
        score += 10
    return score


def record_score(record: dict[str, Any], question: str) -> int:
    lowered = question.lower()
    q_tokens = question_terms(question)
    label_tokens = question_terms(
        f"{record['source_key']} {record['source_label']} {record['table_label']} {record['metric_label']}"
    )
    return len(q_tokens & label_tokens) * 8 + direct_metric_bonus(record, lowered)


def should_rank_factors(question: str) -> bool:
    lowered = question.lower()
    return bool(
        re.search(r"\b(which|what)\b.*\b(factor|circumstance)\b", lowered)
        and any(word in lowered for word in ["highest", "largest", "most", "top"])
    )


class MshpCrashIndex:
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

    def file_info(self, file_name: str) -> dict[str, Any] | None:
        for item in self.payload().get("files", []):
            if item.get("file_name") == file_name:
                return item
        return None

    def year_span(self) -> tuple[int | None, int | None]:
        years = [record["year"] for record in self.records()]
        if not years:
            return None, None
        return min(years), max(years)

    def coverage_citation(self) -> list[dict[str, Any]]:
        files = self.payload().get("files", [])
        source_files = [
            {
                "category": item.get("key"),
                "category_label": item.get("label"),
                "file_name": item.get("url"),
                "row_count": item.get("record_count"),
                "bytes": item.get("bytes"),
                "sha256": item.get("sha256"),
            }
            for item in files[:5]
        ]
        min_year, max_year = self.year_span()
        return [
            {
                "dataset": "MSHP Statistical Analysis Center data files",
                "category": "Traffic safety",
                "kind": "aggregate crash statistics coverage",
                "lookup_table": "mshp_crash_index",
                "year": None,
                "year_range": f"{min_year}-{max_year}" if min_year and max_year else None,
                "source_files": source_files,
                "source_file_count": len(files),
                "source_rows": sum(item.get("record_count") or 0 for item in files),
                "matched_rows": 0,
            }
        ]

    def citation(self, record: dict[str, Any], matched_rows: int = 1) -> list[dict[str, Any]]:
        file_info = self.file_info(record["file_name"]) or {}
        return [
            {
                "dataset": "MSHP Statistical Analysis Center data files",
                "category": "Traffic safety",
                "kind": "aggregate crash statistics",
                "lookup_table": "mshp_crash_index",
                "year": record["year"],
                "year_range": f"{file_info.get('min_year')}-{file_info.get('max_year')}",
                "source_files": [
                    {
                        "category": record["source_key"],
                        "category_label": record["source_label"],
                        "file_name": record["url"],
                        "row_count": file_info.get("record_count"),
                        "bytes": file_info.get("bytes"),
                        "sha256": file_info.get("sha256"),
                    }
                ],
                "source_file_count": 1,
                "source_rows": file_info.get("record_count"),
                "matched_rows": matched_rows,
            }
        ]

    def rank_factor_answer(self, question: str, year: int) -> dict[str, Any] | None:
        rows = [
            record
            for record in self.records()
            if record["year"] == year and record["source_key"] == "circumstances"
        ]
        if not rows:
            return None
        rows.sort(key=lambda item: float(item["value"]), reverse=True)
        top = rows[0]
        rendered = "; ".join(f"{row['metric_label']}: {value_label(row['value'])}" for row in rows[:6])
        return {
            "question": question,
            "answer": (
                f"In the indexed MSHP crash circumstances table for {year}, the highest listed factor is "
                f"{top['metric_label']} with {value_label(top['value'])} crashes. Other indexed factors: {rendered}."
            ),
            "retrieved_context_id": f"mshp_crash_index:circumstances:{year}:top_factor",
            "retrieved_source": "mshp_crash_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from local MSHP Statistical Analysis Center aggregate crash files.",
            "citations": self.citation(top, matched_rows=len(rows)),
            "source_rows": [{"source_file": top["file_name"], "values": {row["metric_label"]: row["value"] for row in rows}}],
        }

    def answer(self, question: str) -> dict[str, Any] | None:
        years = years_in_text(question)
        if not years:
            return None
        year = years[0]
        if should_rank_factors(question):
            return self.rank_factor_answer(question, year)
        candidates = [record for record in self.records() if record["year"] == year]
        if not candidates:
            min_year, max_year = self.year_span()
            if min_year is None or max_year is None:
                return None
            return {
                "question": question,
                "answer": (
                    f"I have an indexed MSHP aggregate crash-statistics source, but not for requested year {year}. "
                    f"The local MSHP crash index currently covers official aggregate files with years ranging from "
                    f"{min_year} to {max_year}; coverage varies by source file."
                ),
                "retrieved_context_id": f"mshp_crash_index:missing_year:{year}",
                "retrieved_source": "mshp_crash_lookup_index",
                "retrieval_score": 1.0,
                "used_model": False,
                "model": "deterministic_public_lookup",
                "source_note": "Answered from local MSHP crash-index coverage metadata.",
                "citations": self.coverage_citation(),
                "source_rows": [],
            }
        ranked = sorted(
            ((record_score(record, question), record) for record in candidates),
            key=lambda item: item[0],
            reverse=True,
        )
        score, record = ranked[0]
        if score < 25:
            return None
        return {
            "question": question,
            "answer": (
                f"The indexed MSHP crash data lists {value_label(record['value'])} for "
                f"{record['metric_label']} in {year}. Table: {record['table_label']}. "
                f"Source file: {record['file_name']}."
            ),
            "retrieved_context_id": f"mshp_crash_index:{record['source_key']}:{year}:{record['metric_key']}",
            "retrieved_source": "mshp_crash_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from local MSHP Statistical Analysis Center aggregate crash files.",
            "citations": self.citation(record),
            "source_rows": [
                {
                    "source_file": record["file_name"],
                    "source_row_number": None,
                    "values": {
                        "Year": record["year"],
                        "Table": record["table_label"],
                        "Metric": record["metric_label"],
                        "Value": record["value"],
                    },
                }
            ],
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--delay-seconds", type=float, default=0.05)
    args = parser.parse_args()
    payload = build_mshp_crash_index(force=args.force, delay_seconds=args.delay_seconds)
    print(json.dumps({key: value for key, value in payload.items() if key != "records"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
