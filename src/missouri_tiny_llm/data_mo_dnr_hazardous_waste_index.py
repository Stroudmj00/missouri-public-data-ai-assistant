"""Build and query selected Missouri DNR hazardous-waste facility data from data.mo.gov."""

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
RAW_DIR = PROJECT_ROOT / "data" / "raw_public" / "data_mo_dnr_hazardous_waste"
INDEX_PATH = RAW_DIR / "data_mo_dnr_hazardous_waste_index.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "data_mo_dnr_hazardous_waste_index_report.json"
DATASET_ID = "m7dn-rv29"
DATASET_NAME = "Hazardous Waste Treatment, Storage and Disposal Facilities"
DATA_URL = f"https://data.mo.gov/resource/{DATASET_ID}.json"
LANDING_PAGE = f"https://data.mo.gov/d/{DATASET_ID}"
METADATA_URL = f"https://data.mo.gov/api/views/{DATASET_ID}.json"

GENERIC_FACILITY_TOKENS = {
    "AND",
    "DATA",
    "DISPOSAL",
    "DNR",
    "FACILITY",
    "FACILITIES",
    "HAZARDOUS",
    "INDEX",
    "INDEXED",
    "MISSOURI",
    "MO",
    "STORAGE",
    "THE",
    "TREATMENT",
    "TSD",
    "WASTE",
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
    cleaned = re.sub(r"[^A-Z0-9&./-]+", " ", clean_text(value).upper())
    return re.sub(r"\s+", " ", cleaned).strip()


def facility_tokens(value: str) -> set[str]:
    return {token for token in normalize_text(value).split() if token not in GENERIC_FACILITY_TOKENS}


def rows_updated_label(value: Any) -> str | None:
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).replace(microsecond=0).isoformat()


def clean_website(value: Any) -> str:
    url = clean_text(value)
    if not url:
        return ""
    if "#" in url:
        first, *_ = url.split("#")
        return first or url.split("#")[-1]
    return url


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    facility_name = clean_text(row.get("facility_name")).upper()
    county = clean_text(row.get("countyname"))
    city = clean_text(row.get("facility_city")).upper()
    status = clean_text(row.get("facilitystatus"))
    return {
        "facility_name": facility_name,
        "facility_norm": normalize_text(facility_name),
        "epa_id": clean_text(row.get("epa_id")).upper(),
        "tsd_universe": clean_text(row.get("tsduniverse")).lower() == "true",
        "website": clean_website(row.get("website")),
        "status": status,
        "status_norm": normalize_text(status),
        "county": county,
        "county_norm": normalize_text(county),
        "city": city,
        "state": clean_text(row.get("facility_state")).upper(),
        "zip_code": clean_text(row.get("facility_zipcode")),
        "address": clean_text(row.get("facility_address")),
        "region": clean_text(row.get("region")).upper(),
        "mo_house_district": clean_text(row.get("morepdist1")),
        "mo_senate_district": clean_text(row.get("mosenatedist1")),
        "us_house_district": clean_text(row.get("usrep")),
        "source_url": DATA_URL,
        "landing_page": LANDING_PAGE,
    }


def top_counts(counter: Counter[str], limit: int = 12) -> list[dict[str, Any]]:
    return [
        {"label": label, "count": count}
        for label, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:limit]
        if label
    ]


def build_data_mo_dnr_hazardous_waste_index(force: bool = False) -> dict[str, Any]:
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
    response = session.get(DATA_URL, params={"$limit": 5000}, timeout=60)
    response.raise_for_status()
    raw_text = response.text
    raw_rows = response.json()
    stored_raw_rows = [{key: value for key, value in row.items() if key != "facility_phone"} for row in raw_rows]
    records = sorted(
        [normalize_row(row) for row in raw_rows],
        key=lambda item: (item["county_norm"], item["facility_norm"], item["epa_id"]),
    )
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    write_json(RAW_DIR / "hazardous_waste_facilities.json", stored_raw_rows)
    county_counts = Counter(record["county"] for record in records if record["county"])
    status_counts = Counter(record["status"] for record in records if record["status"])
    region_counts = Counter(record["region"] for record in records if record["region"])
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
        "status_counts": dict(sorted(status_counts.items())),
        "region_counts": dict(sorted(region_counts.items())),
        "columns": [
            column.get("name")
            for column in metadata.get("columns", [])
            if column.get("name") and "phone" not in column.get("name", "").lower()
        ],
        "top_counties": top_counts(county_counts),
        "top_regions": top_counts(region_counts),
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
            "status_counts": payload["status_counts"],
            "region_counts": payload["region_counts"],
            "top_counties": payload["top_counties"],
            "top_regions": payload["top_regions"],
        },
    )
    return payload


def asks_for_count(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["how many", "count", "number of", "total"])


def asks_for_top(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["top", "highest", "largest", "most"])


def epa_id_in_question(question: str) -> str | None:
    match = re.search(r"\bMOD\d{9}\b", question.upper())
    return match.group(0) if match else None


def status_in_question(question: str) -> str | None:
    lowered = question.lower()
    if "interim" in lowered:
        return "Interim Status"
    if "permitted" in lowered or "permit status" in lowered:
        return "Permitted"
    if "other" in lowered:
        return "Other"
    return None


class DataMoDnrHazardousWasteIndex:
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

    def citation(self, matched_rows: int = 0, record: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        payload = self.payload()
        source_files = [
            {
                "category": "hazardous_waste_facilities",
                "category_label": payload.get("source", DATASET_NAME),
                "file_name": payload.get("source_url", DATA_URL),
                "source_url": payload.get("source_url", DATA_URL),
                "row_count": payload.get("record_count"),
                "bytes": payload.get("bytes"),
                "sha256": payload.get("sha256"),
            },
            {
                "category": "hazardous_waste_facilities",
                "category_label": "data.mo.gov landing page",
                "file_name": payload.get("landing_page", LANDING_PAGE),
                "source_url": payload.get("landing_page", LANDING_PAGE),
                "row_count": None,
                "bytes": None,
                "sha256": None,
            },
        ]
        if record and record.get("website"):
            source_files.insert(
                0,
                {
                    "category": "dnr_facility_page",
                    "category_label": "DNR facility page",
                    "file_name": record["website"],
                    "source_url": record["website"],
                    "row_count": 1,
                    "bytes": None,
                    "sha256": None,
                },
            )
        return [
            {
                "dataset": payload.get("source", DATASET_NAME),
                "category": "DNR hazardous waste facilities",
                "kind": "hazardous waste TSD facility row",
                "lookup_table": "data_mo_dnr_hazardous_waste_index",
                "year": None,
                "year_range": None,
                "source_files": source_files,
                "source_file_count": len(source_files),
                "source_rows": payload.get("record_count"),
                "matched_rows": matched_rows,
            }
        ]

    def unavailable_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "The selected data.mo.gov DNR hazardous-waste facility index has not been built yet. Run "
                "`python scripts/build_data_mo_dnr_hazardous_waste_index.py --force` to download the public facility table and build exact lookups."
            ),
            "retrieved_context_id": "data_mo_dnr_hazardous_waste_index:missing",
            "retrieved_source": "data_mo_dnr_hazardous_waste_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "The DNR hazardous-waste facility route exists, but the local ignored index is missing.",
            "citations": [],
            "source_rows": [],
        }

    def source_rows(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows = []
        for record in records[:5]:
            rows.append(
                {
                    "source_file": DATA_URL,
                    "source_row_number": record.get("epa_id") or record.get("facility_name"),
                    "values": {
                        "Facility": record.get("facility_name"),
                        "EPA ID": record.get("epa_id"),
                        "County": record.get("county"),
                        "City": record.get("city"),
                        "Status": record.get("status"),
                        "DNR region": record.get("region"),
                        "Address": record.get("address"),
                        "ZIP": record.get("zip_code"),
                        "Facility page": record.get("website"),
                    },
                }
            )
        return rows

    def summary_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        top_counties = "; ".join(f"{item['label']}: {item['count']}" for item in payload.get("top_counties", [])[:5])
        statuses = "; ".join(f"{label}: {count}" for label, count in payload.get("status_counts", {}).items())
        regions = "; ".join(f"{item['label']}: {item['count']}" for item in payload.get("top_regions", [])[:5])
        return {
            "question": question,
            "answer": (
                f"The selected DNR hazardous-waste exact lookup layer indexes the data.mo.gov {payload.get('source', DATASET_NAME)} table. "
                f"It contains {payload.get('record_count', 0):,} public facility rows across {payload.get('county_count', 0):,} counties. "
                f"Rows updated at: {payload.get('rows_updated_at_utc')}. It can answer EPA ID lookups, facility-name lookups, county counts, "
                f"status counts, county rankings, and DNR region summaries. Top counties: {top_counties}. Status counts: {statuses}. Regions: {regions}."
            ),
            "retrieved_context_id": "data_mo_dnr_hazardous_waste_index:summary",
            "retrieved_source": "data_mo_dnr_hazardous_waste_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local data.mo.gov DNR hazardous-waste facility index.",
            "citations": self.citation(),
            "source_rows": [],
        }

    def county_from_question(self, question: str) -> str | None:
        normalized_question = normalize_text(question)
        for county in sorted({record["county"] for record in self.records() if record.get("county")}, key=len, reverse=True):
            if re.search(rf"\b{re.escape(normalize_text(county))}\b", normalized_question):
                return county
        return None

    def matching_facility_records(self, question: str) -> list[dict[str, Any]]:
        epa_id = epa_id_in_question(question)
        if epa_id:
            return [record for record in self.records() if record.get("epa_id") == epa_id]
        question_tokens = facility_tokens(question)
        if not question_tokens:
            return []
        scored: list[tuple[float, str, dict[str, Any]]] = []
        for record in self.records():
            tokens = facility_tokens(record.get("facility_name", ""))
            if not tokens:
                continue
            overlap = len(question_tokens & tokens)
            if overlap >= min(2, len(tokens)):
                scored.append((overlap / len(tokens), record.get("facility_name", ""), record))
        if not scored:
            return []
        scored.sort(key=lambda item: (-item[0], item[1], item[2].get("epa_id", "")))
        best_facility = scored[0][1]
        return [record for _, facility, record in scored if facility == best_facility]

    def answer(self, question: str) -> dict[str, Any] | None:
        if not self.available():
            return self.unavailable_answer(question)

        payload = self.payload()
        records = self.records()
        facility_matches = self.matching_facility_records(question)
        if facility_matches:
            record = facility_matches[0]
            return {
                "question": question,
                "answer": (
                    f"{record['facility_name']} is listed in the DNR hazardous-waste facility table with EPA ID {record['epa_id']}. "
                    f"It is in {record['city']}, {record['county']} County, DNR region {record['region']}. "
                    f"Status: {record['status']}. Facility page: {record.get('website') or 'not listed'}."
                ),
                "retrieved_context_id": f"data_mo_dnr_hazardous_waste_index:facility:{record['epa_id']}",
                "retrieved_source": "data_mo_dnr_hazardous_waste_lookup_index",
                "retrieval_score": 1.0,
                "used_model": False,
                "model": "deterministic_public_lookup",
                "source_note": "Computed from the local data.mo.gov DNR hazardous-waste facility index.",
                "citations": self.citation(matched_rows=1, record=record),
                "source_rows": self.source_rows([record]),
            }

        county = self.county_from_question(question)
        status = status_in_question(question)
        if asks_for_count(question) and (county or status):
            matches = records
            detail_parts = []
            if county:
                matches = [record for record in matches if record.get("county") == county]
                detail_parts.append(f"in {county} County")
            if status:
                matches = [record for record in matches if record.get("status") == status]
                detail_parts.append(f"with {status} status")
            detail = " ".join(detail_parts) or "in the index"
            return {
                "question": question,
                "answer": f"The indexed data.mo.gov DNR hazardous-waste facility table lists {len(matches):,} facility row(s) {detail}.",
                "retrieved_context_id": f"data_mo_dnr_hazardous_waste_index:count:{county or 'all'}:{status or 'all'}",
                "retrieved_source": "data_mo_dnr_hazardous_waste_lookup_index",
                "retrieval_score": 1.0,
                "used_model": False,
                "model": "deterministic_public_lookup",
                "source_note": "Computed from the local data.mo.gov DNR hazardous-waste facility index.",
                "citations": self.citation(matched_rows=len(matches)),
                "source_rows": self.source_rows(matches),
            }

        if asks_for_top(question):
            top = payload.get("top_counties", [])[:8]
            rendered = "; ".join(f"{item['label']}: {item['count']}" for item in top)
            return {
                "question": question,
                "answer": f"Top indexed counties by DNR hazardous-waste facility rows: {rendered}.",
                "retrieved_context_id": "data_mo_dnr_hazardous_waste_index:top_counties",
                "retrieved_source": "data_mo_dnr_hazardous_waste_lookup_index",
                "retrieval_score": 1.0,
                "used_model": False,
                "model": "deterministic_public_lookup",
                "source_note": "Computed from the local data.mo.gov DNR hazardous-waste facility index.",
                "citations": self.citation(),
                "source_rows": [],
            }

        return self.summary_answer(question)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build selected data.mo.gov DNR hazardous-waste facility lookup index.")
    parser.add_argument("--force", action="store_true", help="Rebuild even when the local index already exists.")
    args = parser.parse_args()
    payload = build_data_mo_dnr_hazardous_waste_index(force=args.force)
    print(
        json.dumps(
            {
                "index_path": payload["index_path"],
                "records": payload["record_count"],
                "counties": payload["county_count"],
                "rows_updated_at_utc": payload["rows_updated_at_utc"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
