"""Build and query selected Missouri utility data from data.mo.gov."""

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
RAW_DIR = PROJECT_ROOT / "data" / "raw_public" / "data_mo_utility"
INDEX_PATH = RAW_DIR / "data_mo_utility_index.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "data_mo_utility_index_report.json"
DATASET_ID = "yeiz-h2m2"
DATASET_NAME = "Find A Missouri Utility"
DATA_URL = f"https://data.mo.gov/resource/{DATASET_ID}.json"
LANDING_PAGE = f"https://data.mo.gov/d/{DATASET_ID}"
METADATA_URL = f"https://data.mo.gov/api/views/{DATASET_ID}.json"

SERVICE_FIELDS = {
    "electric": ("electric", "electric utility"),
    "gas": ("gas", "gas utility"),
    "water": ("water", "water utility"),
    "telephone": ("telephone", "telephone provider"),
}

GENERIC_UTILITY_TOKENS = {
    "CITY",
    "COUNTY",
    "ELECTRIC",
    "FIND",
    "GAS",
    "MISSOURI",
    "MO",
    "PROVIDER",
    "PROVIDERS",
    "SERVE",
    "SERVES",
    "SERVICE",
    "THE",
    "UTILITY",
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
    cleaned = re.sub(r"[^A-Z0-9&.]+", " ", clean_text(value).upper())
    return re.sub(r"\s+", " ", cleaned).strip()


def utility_tokens(value: str) -> set[str]:
    return {token for token in normalize_text(value).split() if token not in GENERIC_UTILITY_TOKENS}


def rows_updated_label(value: Any) -> str | None:
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).replace(microsecond=0).isoformat()


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    city = clean_text(row.get("city")).upper()
    county = clean_text(row.get("county")).upper()
    return {
        "city": city,
        "city_norm": normalize_text(city),
        "county": county,
        "county_norm": normalize_text(county),
        "map": clean_text(row.get("map")),
        "electric_type": clean_text(row.get("e_type")),
        "electric": clean_text(row.get("electric")).upper(),
        "electric_division": clean_text(row.get("e_division")),
        "gas_type": clean_text(row.get("g_type")),
        "gas": clean_text(row.get("gas")).upper(),
        "gas_area": clean_text(row.get("area")),
        "gas_division": clean_text(row.get("g_division")),
        "gas_district": clean_text(row.get("g_district")),
        "water": clean_text(row.get("water")).upper(),
        "telephone": clean_text(row.get("telephone")).upper(),
        "source_url": DATA_URL,
        "landing_page": LANDING_PAGE,
    }


def service_counts(records: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    counts = Counter(record[field] for record in records if record.get(field))
    return [
        {"provider": provider, "count": count}
        for provider, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:12]
    ]


def build_data_mo_utility_index(force: bool = False) -> dict[str, Any]:
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
        key=lambda item: (item["county"], item["city"], item["electric"], item["gas"], item["water"]),
    )
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    write_json(RAW_DIR / "find_a_missouri_utility.json", raw_rows)
    county_counts = Counter(record["county"] for record in records if record["county"])
    top_counties = [
        {"county": county, "count": count}
        for county, count in sorted(county_counts.items(), key=lambda item: (-item[1], item[0]))[:12]
    ]
    service_summary = {
        service_key: service_counts(records, field)
        for service_key, (field, _label) in SERVICE_FIELDS.items()
    }
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
        "city_count": len({(record["city"], record["county"]) for record in records}),
        "columns": [column.get("name") for column in metadata.get("columns", []) if column.get("name")],
        "top_counties": top_counties,
        "service_summary": service_summary,
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
            "city_count": payload["city_count"],
            "top_counties": top_counties,
            "service_summary": service_summary,
        },
    )
    return payload


def asks_for_count(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["how many", "count", "number of", "total"])


def asks_for_top(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["top", "highest", "largest", "most"])


def service_key_for_question(question: str) -> str | None:
    lowered = question.lower()
    for service_key in ("electric", "gas", "water", "telephone"):
        if service_key in lowered:
            return service_key
    if "phone" in lowered or "telecom" in lowered:
        return "telephone"
    return None


class DataMoUtilityIndex:
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
                "category": "Utilities",
                "kind": "city utility provider row",
                "lookup_table": "data_mo_utility_index",
                "year": None,
                "year_range": None,
                "source_files": [
                    {
                        "category": "find_a_missouri_utility",
                        "category_label": payload.get("source", DATASET_NAME),
                        "file_name": payload.get("source_url", DATA_URL),
                        "row_count": payload.get("record_count"),
                        "bytes": payload.get("bytes"),
                        "sha256": payload.get("sha256"),
                    },
                    {
                        "category": "find_a_missouri_utility",
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
                "The selected data.mo.gov utility index has not been built yet. Run "
                "`python scripts/build_data_mo_utility_index.py --force` to download the public utility table and build exact lookups."
            ),
            "retrieved_context_id": "data_mo_utility_index:missing",
            "retrieved_source": "data_mo_utility_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "The utility route exists, but the local ignored index is missing.",
            "citations": [],
            "source_rows": [],
        }

    def summary_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        electric_top = payload.get("service_summary", {}).get("electric", [])
        top = "; ".join(f"{item['provider']}: {item['count']}" for item in electric_top[:3])
        return {
            "question": question,
            "answer": (
                f"The selected utility exact lookup layer indexes the data.mo.gov {payload.get('source', DATASET_NAME)} table. "
                f"It contains {payload.get('record_count', 0):,} city/county utility rows across "
                f"{payload.get('county_count', 0):,} counties and {payload.get('city_count', 0):,} city/county entries. "
                f"Rows updated at: {payload.get('rows_updated_at_utc')}. It can answer city/county electric, gas, water, "
                f"and telephone provider questions plus provider rankings. Top electric providers by listed rows: {top}."
            ),
            "retrieved_context_id": "data_mo_utility_index:summary",
            "retrieved_source": "data_mo_utility_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local data.mo.gov utility index.",
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

    def city_from_question(self, question: str, county: str | None = None) -> str | None:
        question_norm = normalize_text(question)
        cities = sorted(
            {
                record["city"]
                for record in self.records()
                if record.get("city") and (county is None or record.get("county") == county)
            },
            key=len,
            reverse=True,
        )
        for city in cities:
            city_norm = normalize_text(city)
            if re.search(rf"\b{re.escape(city_norm)}\b", question_norm):
                return city
        return None

    def records_for_location(self, city: str | None = None, county: str | None = None) -> list[dict[str, Any]]:
        records = self.records()
        if city:
            records = [record for record in records if record.get("city") == city]
        if county:
            records = [record for record in records if record.get("county") == county]
        return records

    def find_by_provider(self, question: str) -> dict[str, Any] | None:
        question_tokens = utility_tokens(question)
        candidates: list[tuple[int, dict[str, Any]]] = []
        for record in self.records():
            provider_text = " ".join(record.get(field, "") for field in ("electric", "gas", "water", "telephone"))
            tokens = utility_tokens(provider_text)
            score = len(tokens & question_tokens)
            if score >= 2:
                candidates.append((score, record))
        if not candidates:
            return None
        return sorted(candidates, key=lambda item: item[0], reverse=True)[0][1]

    def location_answer(self, question: str, records: list[dict[str, Any]], city: str | None, county: str | None) -> dict[str, Any]:
        if not records:
            return self.missing_answer(question)
        if asks_for_count(question) and city is None and county:
            examples = "; ".join(record["city"] for record in records[:8])
            answer = f"The indexed {DATASET_NAME} table lists {len(records):,} utility row(s) in {county} County. Example cities: {examples}."
        else:
            record = records[0]
            answer = (
                f"The indexed {DATASET_NAME} table lists utilities for {record['city']}, {record['county']} County: "
                f"electric: {record['electric'] or 'not listed'}"
            )
            if record.get("electric_type"):
                answer += f" ({record['electric_type']})"
            answer += f"; gas: {record['gas'] or 'not listed'}"
            if record.get("gas_type"):
                answer += f" ({record['gas_type']})"
            answer += f"; water: {record['water'] or 'not listed'}; telephone: {record['telephone'] or 'not listed'}."
        location_id = ":".join(part for part in [county, city] if part)
        return {
            "question": question,
            "answer": answer,
            "retrieved_context_id": f"data_mo_utility_index:location:{location_id}",
            "retrieved_source": "data_mo_utility_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local data.mo.gov utility index.",
            "citations": self.citation(matched_rows=len(records)),
            "source_rows": [{"source_file": DATA_URL, "values": record} for record in records[:5]],
        }

    def rank_answer(self, question: str) -> dict[str, Any]:
        service_key = service_key_for_question(question) or "electric"
        field, label = SERVICE_FIELDS[service_key]
        rows = self.payload().get("service_summary", {}).get(service_key, [])
        winner = rows[0] if rows else {"provider": "unknown", "count": 0}
        rendered = "; ".join(f"{item['provider']}: {item['count']}" for item in rows[:5])
        return {
            "question": question,
            "answer": (
                f"In the indexed {DATASET_NAME} table, the most frequent listed {label} is "
                f"{winner['provider']}: {winner['count']} row(s). Top providers: {rendered}."
            ),
            "retrieved_context_id": f"data_mo_utility_index:rank:{field}",
            "retrieved_source": "data_mo_utility_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed by ranking provider counts in the local data.mo.gov utility index.",
            "citations": self.citation(matched_rows=self.payload().get("record_count", 0)),
            "source_rows": [{"source_file": DATA_URL, "values": item} for item in rows[:5]],
        }

    def missing_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                f"I have indexed {DATASET_NAME}, but this question did not match a listed city/county utility row or supported provider ranking. "
                "Try `What utilities serve Columbia in Boone County?` or `Which electric utility appears most often?`."
            ),
            "retrieved_context_id": "data_mo_utility_index:no_match",
            "retrieved_source": "data_mo_utility_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Answered from utility coverage metadata because no exact row matched.",
            "citations": self.citation(),
            "source_rows": [],
        }

    def answer(self, question: str) -> dict[str, Any] | None:
        if not self.available():
            return self.unavailable_answer(question)
        lowered = question.lower()
        if (
            re.search(r"\b(utility|utilities|psc)\b.*\b(indexed|lookup|data)\b", lowered)
            and not asks_for_top(question)
        ):
            county = self.county_from_question(question)
            city = self.city_from_question(question, county)
            if city is None and county is None:
                return self.summary_answer(question)
        if asks_for_top(question):
            return self.rank_answer(question)
        county = self.county_from_question(question)
        city = self.city_from_question(question, county)
        if city or county:
            return self.location_answer(question, self.records_for_location(city=city, county=county), city, county)
        provider_match = self.find_by_provider(question)
        if provider_match:
            return self.location_answer(question, [provider_match], provider_match["city"], provider_match["county"])
        return self.missing_answer(question)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    payload = build_data_mo_utility_index(force=args.force)
    print(json.dumps({key: value for key, value in payload.items() if key != "records"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
