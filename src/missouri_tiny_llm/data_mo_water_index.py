"""Build and query selected Missouri DNR water data from data.mo.gov."""

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
RAW_DIR = PROJECT_ROOT / "data" / "raw_public" / "data_mo_water"
INDEX_PATH = RAW_DIR / "data_mo_water_index.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "data_mo_water_index_report.json"
DATASET_ID = "3mwf-kse4"
DATASET_NAME = "Consumer Confidence Report"
DATA_URL = f"https://data.mo.gov/resource/{DATASET_ID}.json"
LANDING_PAGE = f"https://data.mo.gov/d/{DATASET_ID}"
METADATA_URL = f"https://data.mo.gov/api/views/{DATASET_ID}.json"

GENERIC_WATER_TOKENS = {
    "CITY",
    "COUNTY",
    "DNR",
    "DRINKING",
    "MISSOURI",
    "MO",
    "PWS",
    "PWSD",
    "PUBLIC",
    "REPORT",
    "SYSTEM",
    "SYSTEMS",
    "THE",
    "UTILITIES",
    "WATER",
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
    return re.sub(r"\s+", " ", cleaned).strip()


def water_tokens(value: str) -> set[str]:
    return {token for token in normalize_text(value).split() if token not in GENERIC_WATER_TOKENS}


def rows_updated_label(value: Any) -> str | None:
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).replace(microsecond=0).isoformat()


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    pwsid = clean_text(row.get("pwsid")).upper()
    name = clean_text(row.get("name"))
    county = clean_text(row.get("county")).upper()
    return {
        "pwsid": pwsid,
        "name": name,
        "name_norm": normalize_text(name),
        "county": county,
        "county_norm": normalize_text(county),
        "source_url": DATA_URL,
        "landing_page": LANDING_PAGE,
    }


def build_data_mo_water_index(force: bool = False) -> dict[str, Any]:
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
    records = sorted(
        [normalize_row(row) for row in raw_rows],
        key=lambda item: (item["county"], item["name"], item["pwsid"]),
    )
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    write_json(RAW_DIR / "consumer_confidence_report.json", raw_rows)
    county_counts = Counter(record["county"] for record in records if record["county"])
    top_counties = [
        {"county": county, "count": count}
        for county, count in sorted(county_counts.items(), key=lambda item: (-item[1], item[0]))[:12]
    ]
    payload = {
        "generated_at_utc": utc_now(),
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "source": DATASET_NAME,
        "source_url": DATA_URL,
        "landing_page": LANDING_PAGE,
        "metadata_url": METADATA_URL,
        "index_path": str(INDEX_PATH.relative_to(PROJECT_ROOT)),
        "dataset_id": DATASET_ID,
        "rows_updated_at_utc": rows_updated_label(metadata.get("rowsUpdatedAt")),
        "bytes": len(raw_text.encode("utf-8")),
        "sha256": sha256_text(raw_text),
        "record_count": len(records),
        "county_count": len(county_counts),
        "columns": [column.get("name") for column in metadata.get("columns", []) if column.get("name")],
        "top_counties": top_counties,
        "records": records,
    }
    write_json(INDEX_PATH, payload)
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
            "rows_updated_at_utc": payload["rows_updated_at_utc"],
            "bytes": payload["bytes"],
            "sha256": payload["sha256"],
            "record_count": payload["record_count"],
            "county_count": payload["county_count"],
            "top_counties": top_counties,
        },
    )
    return payload


def asks_for_count(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["how many", "count", "number of", "total"])


def asks_for_top(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["top", "highest", "largest", "most"])


def pwsid_in_question(question: str) -> str | None:
    match = re.search(r"\bMO\d{7}\b", question.upper())
    return match.group(0) if match else None


class DataMoWaterIndex:
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
                "category": "DNR water",
                "kind": "public drinking water system row",
                "lookup_table": "data_mo_water_index",
                "year": None,
                "year_range": None,
                "source_files": [
                    {
                        "category": "consumer_confidence_report",
                        "category_label": payload.get("source", DATASET_NAME),
                        "file_name": payload.get("source_url", DATA_URL),
                        "row_count": payload.get("record_count"),
                        "bytes": payload.get("bytes"),
                        "sha256": payload.get("sha256"),
                    },
                    {
                        "category": "consumer_confidence_report",
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

    def unavailable_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "The selected data.mo.gov DNR water index has not been built yet. Run "
                "`python scripts/build_data_mo_water_index.py --force` to download the public Consumer Confidence Report dataset and build exact lookups."
            ),
            "retrieved_context_id": "data_mo_water_index:missing",
            "retrieved_source": "data_mo_water_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "The DNR water route exists, but the local ignored index is missing.",
            "citations": [],
            "source_rows": [],
        }

    def summary_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        top = "; ".join(f"{item['county']}: {item['count']}" for item in payload.get("top_counties", [])[:5])
        return {
            "question": question,
            "answer": (
                f"The selected DNR/water exact lookup layer indexes the data.mo.gov {payload.get('source', DATASET_NAME)}. "
                f"It contains {payload.get('record_count', 0):,} public drinking water system rows across "
                f"{payload.get('county_count', 0):,} counties. Rows updated at: {payload.get('rows_updated_at_utc')}. "
                f"It can answer county water-system counts, PWSID lookups, system-name lookups, and county rankings. "
                f"Top counties by listed systems: {top}."
            ),
            "retrieved_context_id": "data_mo_water_index:summary",
            "retrieved_source": "data_mo_water_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local data.mo.gov DNR water index.",
            "citations": self.citation(matched_rows=payload.get("record_count", 0)),
            "source_rows": [],
        }

    def county_from_question(self, question: str) -> str | None:
        question_norm = normalize_text(question)
        counties = sorted({record["county"] for record in self.records() if record.get("county")}, key=len, reverse=True)
        for county in counties:
            county_norm = normalize_text(county)
            if re.search(rf"\b{re.escape(county_norm)}\b(?:\s+COUNTY)?", question_norm):
                return county
        return None

    def records_for_county(self, county: str) -> list[dict[str, Any]]:
        return [record for record in self.records() if record.get("county") == county]

    def find_by_pwsid(self, pwsid: str) -> dict[str, Any] | None:
        for record in self.records():
            if record.get("pwsid") == pwsid:
                return record
        return None

    def find_by_name(self, question: str) -> dict[str, Any] | None:
        question_norm = normalize_text(question)
        question_tokens = water_tokens(question)
        candidates: list[tuple[int, dict[str, Any]]] = []
        for record in self.records():
            name_norm = record["name_norm"]
            tokens = water_tokens(record["name"])
            score = 0
            if name_norm and name_norm in question_norm:
                score += 100 + len(name_norm)
            if tokens and tokens <= question_tokens:
                score += 40 + len(tokens)
            if tokens & question_tokens:
                score += len(tokens & question_tokens)
            if score >= 3:
                candidates.append((score, record))
        if not candidates:
            return None
        return sorted(candidates, key=lambda item: item[0], reverse=True)[0][1]

    def record_answer(self, question: str, record: dict[str, Any]) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                f"The indexed {DATASET_NAME} lists {record['name']} in {record['county']} County with PWSID {record['pwsid']}. "
                "This is a public drinking-water system listing from data.mo.gov; use the cited source for the official record."
            ),
            "retrieved_context_id": f"data_mo_water_index:record:{record['pwsid']}",
            "retrieved_source": "data_mo_water_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local data.mo.gov DNR water index.",
            "citations": self.citation(matched_rows=1),
            "source_rows": [{"source_file": DATA_URL, "values": record}],
        }

    def county_answer(self, question: str, county: str) -> dict[str, Any]:
        records = self.records_for_county(county)
        examples = "; ".join(f"{record['name']} ({record['pwsid']})" for record in records[:8])
        if asks_for_count(question):
            lead = f"The indexed {DATASET_NAME} lists {len(records):,} public drinking water system row(s) in {county} County."
        else:
            lead = f"Indexed public drinking water systems in {county} County include {examples}."
        return {
            "question": question,
            "answer": f"{lead} Examples: {examples}.",
            "retrieved_context_id": f"data_mo_water_index:county:{county}",
            "retrieved_source": "data_mo_water_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local data.mo.gov DNR water index.",
            "citations": self.citation(matched_rows=len(records)),
            "source_rows": [{"source_file": DATA_URL, "values": record} for record in records[:5]],
        }

    def rank_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        top = payload.get("top_counties", [])
        rendered = "; ".join(f"{item['county']}: {item['count']}" for item in top[:5])
        winner = top[0] if top else {"county": "unknown", "count": 0}
        return {
            "question": question,
            "answer": (
                f"In the indexed {DATASET_NAME}, {winner['county']} County has the most listed public drinking water systems: "
                f"{winner['count']}. Top counties: {rendered}."
            ),
            "retrieved_context_id": "data_mo_water_index:rank:county_count",
            "retrieved_source": "data_mo_water_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed by ranking county counts in the local data.mo.gov DNR water index.",
            "citations": self.citation(matched_rows=payload.get("record_count", 0)),
            "source_rows": [{"source_file": DATA_URL, "values": item} for item in top[:5]],
        }

    def missing_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                f"I have indexed {DATASET_NAME}, but this question did not match a county, PWSID, or listed water-system name. "
                "Try a question like `How many public water systems are listed in Boone County?` or `What is the PWSID for City of Columbia Utilities?`."
            ),
            "retrieved_context_id": "data_mo_water_index:no_match",
            "retrieved_source": "data_mo_water_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Answered from DNR water coverage metadata because no exact row matched.",
            "citations": self.citation(),
            "source_rows": [],
        }

    def answer(self, question: str) -> dict[str, Any] | None:
        if not self.available():
            return self.unavailable_answer(question)
        lowered = question.lower()
        if (
            re.search(r"\b(dnr|water|drinking water|consumer confidence)\b.*\b(indexed|lookup|data)\b", lowered)
            and not asks_for_top(question)
        ):
            county = self.county_from_question(question)
            if county is None and pwsid_in_question(question) is None and self.find_by_name(question) is None:
                return self.summary_answer(question)
        pwsid = pwsid_in_question(question)
        if pwsid:
            record = self.find_by_pwsid(pwsid)
            return self.record_answer(question, record) if record else self.missing_answer(question)
        if asks_for_top(question):
            return self.rank_answer(question)
        county = self.county_from_question(question)
        if county:
            return self.county_answer(question, county)
        record = self.find_by_name(question)
        if record:
            return self.record_answer(question, record)
        return self.missing_answer(question)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    payload = build_data_mo_water_index(force=args.force)
    print(json.dumps({key: value for key, value in payload.items() if key != "records"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
