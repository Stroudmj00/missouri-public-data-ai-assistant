"""Build and query selected Missouri long-term-care data from data.mo.gov."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw_public" / "data_mo_ltc"
INDEX_PATH = RAW_DIR / "data_mo_ltc_index.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "data_mo_ltc_index_report.json"

DIRECTORY_ID = "fenu-sipv"
DIRECTORY_NAME = "LTC DIRECTORY"
DIRECTORY_URL = f"https://data.mo.gov/resource/{DIRECTORY_ID}.json"
DIRECTORY_LANDING_PAGE = f"https://data.mo.gov/d/{DIRECTORY_ID}"
DIRECTORY_METADATA_URL = f"https://data.mo.gov/api/views/{DIRECTORY_ID}.json"

CENSUS_ID = "bf8b-a47t"
CENSUS_NAME = "LTC CENSUS REPORT"
CENSUS_URL = f"https://data.mo.gov/resource/{CENSUS_ID}.json"
CENSUS_LANDING_PAGE = f"https://data.mo.gov/d/{CENSUS_ID}"
CENSUS_METADATA_URL = f"https://data.mo.gov/api/views/{CENSUS_ID}.json"

DIRECTORY_SAFE_FIELDS = [
    "region",
    "facility_number",
    "level_of_care",
    "level_of_care_code",
    "capacity",
    "fcilicensenumber",
    "fcilicenseeffdate",
    "license_expiration",
    "facility_name",
    "city",
    "county",
    "certification",
    "dmh_licensed",
    "alzheimer_s_scu",
    "scucapacity",
    "entity_name",
    "definition",
]

GENERIC_FACILITY_TOKENS = {
    "ASSISTED",
    "CARE",
    "CENTER",
    "CENTRE",
    "FACILITY",
    "HEALTH",
    "HOME",
    "HOMES",
    "INC",
    "LLC",
    "LONG",
    "LTC",
    "MISSOURI",
    "MO",
    "NURSING",
    "OF",
    "REHAB",
    "REHABILITATION",
    "RESIDENTIAL",
    "SKILLED",
    "THE",
    "TERM",
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


def normalize_text(value: Any) -> str:
    cleaned = re.sub(r"[^A-Z0-9&]+", " ", clean_text(value).upper())
    return re.sub(r"\s+", " ", cleaned).strip()


def parse_int(value: Any) -> int:
    cleaned = clean_text(value).replace(",", "")
    return int(cleaned) if re.fullmatch(r"-?\d+", cleaned) else 0


def parse_decimal(value: Any) -> Decimal:
    cleaned = clean_text(value).replace(",", "")
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return Decimal("0")


def decimal_json(value: Decimal, places: str = "0.0001") -> str:
    return str(value.quantize(Decimal(places), rounding=ROUND_HALF_UP))


def format_ratio(value: Any) -> str:
    ratio = parse_decimal(value)
    return f"{(ratio * Decimal('100')).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)}%"


def rows_updated_label(value: Any) -> str | None:
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).replace(microsecond=0).isoformat()


def date_label(value: Any) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    return text.split("T", 1)[0]


def facility_tokens(value: str) -> set[str]:
    return {token for token in normalize_text(value).split() if token not in GENERIC_FACILITY_TOKENS}


def level_from_question(question: str) -> str | None:
    lowered = question.lower()
    if re.search(r"\bsnf\b|skilled nursing", lowered):
        return "SNF"
    if re.search(r"\balf\b|assisted living", lowered):
        return "ALF"
    if re.search(r"\brcf\b|residential care", lowered):
        return "RCF"
    if re.search(r"\bicf\b|intermediate care", lowered):
        return "ICF"
    return None


def normalize_directory_row(row: dict[str, Any]) -> dict[str, Any]:
    facility_name = clean_text(row.get("facility_name")).upper()
    city = clean_text(row.get("city")).upper()
    county = clean_text(row.get("county")).upper()
    level = clean_text(row.get("level_of_care")).upper()
    entity = clean_text(row.get("entity_name")).upper()
    return {
        "facility_number": clean_text(row.get("facility_number")),
        "facility_name": facility_name,
        "facility_name_norm": normalize_text(facility_name),
        "region": parse_int(row.get("region")),
        "level_of_care": level,
        "level_of_care_code": clean_text(row.get("level_of_care_code")).upper(),
        "capacity": parse_int(row.get("capacity")),
        "license_number": clean_text(row.get("fcilicensenumber")),
        "license_effective_date": date_label(row.get("fcilicenseeffdate")),
        "license_expiration": date_label(row.get("license_expiration")),
        "city": city,
        "city_norm": normalize_text(city),
        "county": county,
        "county_norm": normalize_text(county),
        "certification": clean_text(row.get("certification")),
        "dmh_licensed": str(row.get("dmh_licensed")).lower() == "true",
        "alzheimers_scu": str(row.get("alzheimer_s_scu")).lower() == "true",
        "alzheimers_scu_capacity": parse_int(row.get("scucapacity")),
        "entity_name": entity,
        "definition": clean_text(row.get("definition")),
    }


def normalize_census_row(row: dict[str, Any]) -> dict[str, Any]:
    label = clean_text(row.get("licensure_level_state_region")).upper()
    beds = parse_int(row.get("licensed_beds"))
    census = parse_int(row.get("census"))
    homes = parse_int(row.get("licensed_homes"))
    match = re.search(r"^([A-Z]+)\s+REGION\s+(\d+)$", label)
    return {
        "licensure_level_state_region": label,
        "level_of_care": match.group(1) if match else "",
        "region": int(match.group(2)) if match else None,
        "licensed_homes": homes,
        "licensed_beds": beds,
        "census": census,
        "occupancy_ratio": decimal_json(Decimal(census) / Decimal(beds)) if beds else "0.0000",
    }


def build_data_mo_ltc_index(force: bool = False) -> dict[str, Any]:
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

    directory_meta_response = session.get(DIRECTORY_METADATA_URL, timeout=60)
    directory_meta_response.raise_for_status()
    directory_meta = directory_meta_response.json()
    census_meta_response = session.get(CENSUS_METADATA_URL, timeout=60)
    census_meta_response.raise_for_status()
    census_meta = census_meta_response.json()

    directory_response = session.get(
        DIRECTORY_URL,
        params={"$select": ",".join(DIRECTORY_SAFE_FIELDS), "$limit": 50000},
        timeout=120,
    )
    directory_response.raise_for_status()
    directory_rows_raw = directory_response.json()
    census_response = session.get(CENSUS_URL, params={"$limit": 1000}, timeout=60)
    census_response.raise_for_status()
    census_rows_raw = census_response.json()

    directory_records = sorted(
        [normalize_directory_row(row) for row in directory_rows_raw],
        key=lambda item: (item["county"], item["city"], item["facility_name"], item["level_of_care"]),
    )
    census_records = sorted(
        [normalize_census_row(row) for row in census_rows_raw],
        key=lambda item: (item["level_of_care"], item["region"] or 0),
    )

    county_groups: dict[str, dict[str, Any]] = {}
    grouped_by_county: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in directory_records:
        grouped_by_county[record["county"]].append(record)
    for county, rows in grouped_by_county.items():
        facilities = {row["facility_number"] for row in rows if row.get("facility_number")}
        level_counts = Counter(row["level_of_care"] for row in rows if row.get("level_of_care"))
        city_counts = Counter(row["city"] for row in rows if row.get("city"))
        county_groups[county] = {
            "county": county,
            "county_norm": normalize_text(county),
            "directory_rows": len(rows),
            "facility_count": len(facilities),
            "capacity": sum(row["capacity"] for row in rows),
            "top_level_counts": [{"level_of_care": level, "count": count} for level, count in level_counts.most_common(8)],
            "top_cities": [{"city": city, "count": count} for city, count in city_counts.most_common(8)],
        }

    by_level: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in directory_records:
        by_level[record["level_of_care"]].append(record)
    level_summaries = {
        level: {
            "level_of_care": level,
            "directory_rows": len(rows),
            "facility_count": len({row["facility_number"] for row in rows if row.get("facility_number")}),
            "capacity": sum(row["capacity"] for row in rows),
        }
        for level, rows in sorted(by_level.items())
    }

    total_census_beds = sum(row["licensed_beds"] for row in census_records)
    total_census = sum(row["census"] for row in census_records)
    total_homes = sum(row["licensed_homes"] for row in census_records)
    source_text = "\n".join([directory_response.text, census_response.text, directory_meta_response.text, census_meta_response.text])
    top_counties = sorted(county_groups.values(), key=lambda item: (-item["capacity"], item["county"]))[:12]
    top_facilities = sorted(directory_records, key=lambda item: (-item["capacity"], item["facility_name"]))[:12]

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    write_json(RAW_DIR / "ltc_directory_sanitized_rows.json", directory_records)
    write_json(RAW_DIR / "ltc_census_rows.json", census_records)

    payload = {
        "generated_at_utc": utc_now(),
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "source": "Selected data.mo.gov long-term-care datasets",
        "directory_source": DIRECTORY_NAME,
        "directory_source_url": DIRECTORY_URL,
        "directory_landing_page": DIRECTORY_LANDING_PAGE,
        "directory_dataset_id": DIRECTORY_ID,
        "directory_rows_updated_at_utc": rows_updated_label(directory_meta.get("rowsUpdatedAt")),
        "census_source": CENSUS_NAME,
        "census_source_url": CENSUS_URL,
        "census_landing_page": CENSUS_LANDING_PAGE,
        "census_dataset_id": CENSUS_ID,
        "census_rows_updated_at_utc": rows_updated_label(census_meta.get("rowsUpdatedAt")),
        "index_path": str(INDEX_PATH.relative_to(PROJECT_ROOT)),
        "bytes": len(source_text.encode("utf-8")),
        "sha256": sha256_text(source_text),
        "directory_record_count": len(directory_records),
        "facility_count": len({row["facility_number"] for row in directory_records if row.get("facility_number")}),
        "county_count": len(county_groups),
        "directory_capacity": sum(row["capacity"] for row in directory_records),
        "census_record_count": len(census_records),
        "census_licensed_homes": total_homes,
        "census_licensed_beds": total_census_beds,
        "census": total_census,
        "statewide_occupancy_ratio": decimal_json(Decimal(total_census) / Decimal(total_census_beds)) if total_census_beds else "0.0000",
        "sanitization_note": (
            "The directory query selects facility, capacity, county, city, license-date, certification, and level-of-care fields only. "
            "It does not store or return administrator names, phone numbers, mailing addresses, or street addresses."
        ),
        "top_counties_by_capacity": top_counties,
        "top_facilities_by_capacity": top_facilities,
        "level_summaries": level_summaries,
        "census_rows": census_records,
        "county_rows": sorted(county_groups.values(), key=lambda item: item["county"]),
        "directory_rows": directory_records,
    }
    write_json(INDEX_PATH, payload)
    write_json(
        REPORT_PATH,
        {
            "generated_at_utc": payload["generated_at_utc"],
            "elapsed_seconds": payload["elapsed_seconds"],
            "source": payload["source"],
            "index_path": payload["index_path"],
            "directory_source": payload["directory_source"],
            "directory_landing_page": payload["directory_landing_page"],
            "directory_dataset_id": payload["directory_dataset_id"],
            "directory_rows_updated_at_utc": payload["directory_rows_updated_at_utc"],
            "census_source": payload["census_source"],
            "census_landing_page": payload["census_landing_page"],
            "census_dataset_id": payload["census_dataset_id"],
            "census_rows_updated_at_utc": payload["census_rows_updated_at_utc"],
            "bytes": payload["bytes"],
            "sha256": payload["sha256"],
            "directory_record_count": payload["directory_record_count"],
            "facility_count": payload["facility_count"],
            "county_count": payload["county_count"],
            "directory_capacity": payload["directory_capacity"],
            "census_record_count": payload["census_record_count"],
            "census_licensed_homes": payload["census_licensed_homes"],
            "census_licensed_beds": payload["census_licensed_beds"],
            "census": payload["census"],
            "statewide_occupancy_ratio": payload["statewide_occupancy_ratio"],
            "sanitization_note": payload["sanitization_note"],
            "top_counties_by_capacity": payload["top_counties_by_capacity"][:10],
            "top_facilities_by_capacity": payload["top_facilities_by_capacity"][:10],
            "level_summaries": payload["level_summaries"],
            "census_rows": payload["census_rows"],
        },
    )
    return payload


def asks_for_top(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["top", "highest", "largest", "most"])


def asks_for_summary(question: str) -> bool:
    lowered = question.lower()
    return bool(
        re.search(r"\b(what|which|show|list)\b.*\b(ltc|long[-\s]+term care|nursing home)\b.*\b(indexed|lookup|data|source)\b", lowered)
        or re.search(r"\b(ltc|long[-\s]+term care|nursing home)\b.*\b(indexed|lookup|coverage)\b", lowered)
    )


class DataMoLtcIndex:
    def __init__(self, path: Path = INDEX_PATH) -> None:
        self.path = path
        self._payload: dict[str, Any] | None = None

    def available(self) -> bool:
        return self.path.exists() and self.path.stat().st_size > 0

    def payload(self) -> dict[str, Any]:
        if self._payload is None:
            self._payload = json.loads(self.path.read_text(encoding="utf-8")) if self.available() else {}
        return self._payload

    def directory_rows(self) -> list[dict[str, Any]]:
        return list(self.payload().get("directory_rows", []))

    def county_rows(self) -> list[dict[str, Any]]:
        return list(self.payload().get("county_rows", []))

    def census_rows(self) -> list[dict[str, Any]]:
        return list(self.payload().get("census_rows", []))

    def citation(self, matched_rows: int = 0, source: str = "combined") -> list[dict[str, Any]]:
        payload = self.payload()
        files = [
            {
                "category": "data_mo_ltc",
                "category_label": payload.get("directory_source", DIRECTORY_NAME),
                "file_name": payload.get("directory_landing_page", DIRECTORY_LANDING_PAGE),
                "row_count": payload.get("directory_record_count"),
                "bytes": payload.get("bytes"),
                "sha256": payload.get("sha256"),
            },
            {
                "category": "data_mo_ltc",
                "category_label": payload.get("census_source", CENSUS_NAME),
                "file_name": payload.get("census_landing_page", CENSUS_LANDING_PAGE),
                "row_count": payload.get("census_record_count"),
                "bytes": payload.get("bytes"),
                "sha256": payload.get("sha256"),
            },
        ]
        if source == "directory":
            files = files[:1]
            source_rows = payload.get("directory_record_count", 0)
        elif source == "census":
            files = files[1:]
            source_rows = payload.get("census_record_count", 0)
        else:
            source_rows = payload.get("directory_record_count", 0) + payload.get("census_record_count", 0)
        return [
            {
                "dataset": payload.get("source", "Selected data.mo.gov long-term-care datasets"),
                "category": "Long-term care",
                "kind": "sanitized facility directory and aggregate census rows",
                "lookup_table": "data_mo_ltc_index",
                "year": None,
                "year_range": None,
                "source_files": files,
                "source_file_count": len(files),
                "source_rows": source_rows,
                "matched_rows": matched_rows,
            }
        ]

    def unavailable_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "The selected data.mo.gov LTC index has not been built yet. Run "
                "`python scripts/build_data_mo_ltc_index.py --force` to build sanitized directory and census lookups."
            ),
            "retrieved_context_id": "data_mo_ltc_index:missing",
            "retrieved_source": "data_mo_ltc_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "The LTC route exists, but the local ignored index is missing.",
            "citations": [],
            "source_rows": [],
        }

    def summary_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        top_counties = "; ".join(
            f"{row['county']}: {row['capacity']:,} capacity"
            for row in payload.get("top_counties_by_capacity", [])[:5]
        )
        return {
            "question": question,
            "answer": (
                "The selected long-term-care exact lookup layer indexes sanitized fields from data.mo.gov "
                f"{DIRECTORY_NAME} and aggregate rows from {CENSUS_NAME}. It has "
                f"{payload.get('directory_record_count', 0):,} directory row(s), "
                f"{payload.get('facility_count', 0):,} unique facility number(s), "
                f"{payload.get('county_count', 0):,} counties, and {payload.get('directory_capacity', 0):,} listed capacity. "
                f"The census table totals {payload.get('census_licensed_homes', 0):,} licensed homes, "
                f"{payload.get('census_licensed_beds', 0):,} licensed beds, census {payload.get('census', 0):,}, "
                f"and statewide occupancy {format_ratio(payload.get('statewide_occupancy_ratio'))}. "
                f"Top counties by listed directory capacity: {top_counties}."
            ),
            "retrieved_context_id": "data_mo_ltc_index:summary",
            "retrieved_source": "data_mo_ltc_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": self.payload().get("sanitization_note"),
            "citations": self.citation(matched_rows=payload.get("directory_record_count", 0)),
            "source_rows": [],
        }

    def county_from_question(self, question: str) -> dict[str, Any] | None:
        question_norm = normalize_text(question)
        for row in sorted(self.county_rows(), key=lambda item: len(item.get("county_norm", "")), reverse=True):
            county_norm = row.get("county_norm", "")
            if county_norm and re.search(rf"\b{re.escape(county_norm)}\b(?:\s+COUNTY)?", question_norm):
                return row
        return None

    def city_from_question(self, question: str, county: str | None = None) -> str | None:
        question_norm = normalize_text(question)
        cities = sorted(
            {
                record["city"]
                for record in self.directory_rows()
                if record.get("city") and (county is None or record.get("county") == county)
            },
            key=len,
            reverse=True,
        )
        for city in cities:
            city_norm = normalize_text(city)
            if city_norm and re.search(rf"\b{re.escape(city_norm)}\b", question_norm):
                return city
        return None

    def facility_from_question(self, question: str) -> dict[str, Any] | None:
        question_norm = normalize_text(question)
        for record in sorted(self.directory_rows(), key=lambda item: len(item.get("facility_name_norm", "")), reverse=True):
            name_norm = record.get("facility_name_norm", "")
            if name_norm and re.search(rf"\b{re.escape(name_norm)}\b", question_norm):
                return record
        question_tokens = facility_tokens(question)
        candidates: list[tuple[int, int, dict[str, Any]]] = []
        for record in self.directory_rows():
            tokens = facility_tokens(record.get("facility_name", ""))
            score = len(tokens & question_tokens)
            if score >= 2:
                candidates.append((score, record.get("capacity", 0), record))
        if not candidates:
            return None
        return sorted(candidates, key=lambda item: (-item[0], -item[1], item[2].get("facility_name", "")))[0][2]

    def directory_records_for_location(self, county: str | None = None, city: str | None = None, level: str | None = None) -> list[dict[str, Any]]:
        records = self.directory_rows()
        if county:
            records = [record for record in records if record.get("county") == county]
        if city:
            records = [record for record in records if record.get("city") == city]
        if level:
            records = [record for record in records if str(record.get("level_of_care", "")).startswith(level)]
        return records

    def county_answer(self, question: str, county_row: dict[str, Any]) -> dict[str, Any]:
        level = level_from_question(question)
        records = self.directory_records_for_location(county=county_row["county"], level=level)
        capacity = sum(record["capacity"] for record in records)
        facility_count = len({record["facility_number"] for record in records if record.get("facility_number")})
        level_text = f" {level}" if level else ""
        city_examples = "; ".join(item["city"] for item in county_row.get("top_cities", [])[:5])
        return {
            "question": question,
            "answer": (
                f"The sanitized {DIRECTORY_NAME} index lists {len(records):,}{level_text} directory row(s) in "
                f"{county_row['county']} County, representing {facility_count:,} unique facility number(s) and "
                f"{capacity:,} listed capacity. Example listed cities: {city_examples}."
            ),
            "retrieved_context_id": f"data_mo_ltc_index:county:{county_row['county_norm']}:{level or 'all'}",
            "retrieved_source": "data_mo_ltc_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": self.payload().get("sanitization_note"),
            "citations": self.citation(matched_rows=len(records), source="directory"),
            "source_rows": [{"source_file": DIRECTORY_LANDING_PAGE, "values": record} for record in records[:5]],
        }

    def city_answer(self, question: str, county: str | None, city: str) -> dict[str, Any]:
        records = self.directory_records_for_location(county=county, city=city, level=level_from_question(question))
        capacity = sum(record["capacity"] for record in records)
        facility_count = len({record["facility_number"] for record in records if record.get("facility_number")})
        location = f"{city}, {county} County" if county else city
        examples = "; ".join(f"{row['facility_name']} ({row['level_of_care']}, {row['capacity']})" for row in records[:5])
        return {
            "question": question,
            "answer": (
                f"The sanitized {DIRECTORY_NAME} index lists {len(records):,} directory row(s) for {location}, "
                f"representing {facility_count:,} unique facility number(s) and {capacity:,} listed capacity. "
                f"Examples: {examples}."
            ),
            "retrieved_context_id": f"data_mo_ltc_index:city:{county or 'all'}:{city}",
            "retrieved_source": "data_mo_ltc_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": self.payload().get("sanitization_note"),
            "citations": self.citation(matched_rows=len(records), source="directory"),
            "source_rows": [{"source_file": DIRECTORY_LANDING_PAGE, "values": record} for record in records[:5]],
        }

    def facility_answer(self, question: str, record: dict[str, Any]) -> dict[str, Any]:
        alz = f"; Alzheimer's SCU capacity: {record['alzheimers_scu_capacity']:,}" if record.get("alzheimers_scu") else ""
        certification = f"; certification: {record['certification']}" if record.get("certification") else ""
        return {
            "question": question,
            "answer": (
                f"The sanitized {DIRECTORY_NAME} index lists {record['facility_name']} as {record['level_of_care']} "
                f"in {record['city']}, {record['county']} County, region {record['region']}, with listed capacity "
                f"{record['capacity']:,}. License effective date: {record.get('license_effective_date') or 'not listed'}; "
                f"license expiration: {record.get('license_expiration') or 'not listed'}{certification}{alz}."
            ),
            "retrieved_context_id": f"data_mo_ltc_index:facility:{record['facility_number']}:{record['level_of_care']}",
            "retrieved_source": "data_mo_ltc_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": self.payload().get("sanitization_note"),
            "citations": self.citation(matched_rows=1, source="directory"),
            "source_rows": [{"source_file": DIRECTORY_LANDING_PAGE, "values": record}],
        }

    def top_county_answer(self, question: str) -> dict[str, Any]:
        rows = self.payload().get("top_counties_by_capacity", [])[:5]
        winner = rows[0] if rows else {"county": "unknown", "capacity": 0}
        rendered = "; ".join(f"{row['county']}: {row['capacity']:,} capacity" for row in rows)
        return {
            "question": question,
            "answer": (
                f"In the sanitized {DIRECTORY_NAME} index, the county with the highest listed long-term-care capacity is "
                f"{winner['county']}: {winner['capacity']:,}. Top counties: {rendered}."
            ),
            "retrieved_context_id": "data_mo_ltc_index:rank:county_capacity",
            "retrieved_source": "data_mo_ltc_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed by ranking county capacity totals in the sanitized LTC Directory index.",
            "citations": self.citation(matched_rows=len(self.county_rows()), source="directory"),
            "source_rows": [{"source_file": DIRECTORY_LANDING_PAGE, "values": row} for row in rows],
        }

    def census_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        lowered = question.lower()
        matched = None
        for row in self.census_rows():
            label = row.get("licensure_level_state_region", "")
            if label and label.lower() in lowered:
                matched = row
                break
        if matched:
            answer = (
                f"The {CENSUS_NAME} aggregate lists {matched['licensure_level_state_region']} with "
                f"{matched['licensed_homes']:,} licensed home(s), {matched['licensed_beds']:,} licensed bed(s), "
                f"census {matched['census']:,}, and occupancy {format_ratio(matched['occupancy_ratio'])}."
            )
            context_id = f"data_mo_ltc_index:census:{matched['licensure_level_state_region']}"
            source_rows = [{"source_file": CENSUS_LANDING_PAGE, "values": matched}]
            matched_rows = 1
        else:
            answer = (
                f"The {CENSUS_NAME} aggregate totals {payload.get('census_licensed_homes', 0):,} licensed home(s), "
                f"{payload.get('census_licensed_beds', 0):,} licensed bed(s), census {payload.get('census', 0):,}, "
                f"and statewide occupancy {format_ratio(payload.get('statewide_occupancy_ratio'))}."
            )
            context_id = "data_mo_ltc_index:census:statewide"
            source_rows = []
            matched_rows = payload.get("census_record_count", 0)
        return {
            "question": question,
            "answer": answer,
            "retrieved_context_id": context_id,
            "retrieved_source": "data_mo_ltc_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from aggregate LTC Census Report rows.",
            "citations": self.citation(matched_rows=matched_rows, source="census"),
            "source_rows": source_rows,
        }

    def missing_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "I have indexed selected long-term-care directory and census data, but this question did not match a supported "
                "facility, city, county, top-capacity ranking, or census aggregate. Try `What LTC data is indexed?`, "
                "`How many LTC directory rows are listed for Boone County?`, or "
                "`What does the LTC directory list for Baptist Homes of Adrian?`."
            ),
            "retrieved_context_id": "data_mo_ltc_index:no_match",
            "retrieved_source": "data_mo_ltc_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Answered from LTC coverage metadata because no exact row matched.",
            "citations": self.citation(),
            "source_rows": [],
        }

    def answer(self, question: str) -> dict[str, Any] | None:
        if not self.available():
            return self.unavailable_answer(question)
        lowered = question.lower()
        if asks_for_summary(question):
            return self.summary_answer(question)
        if "census" in lowered or "occupancy" in lowered or "licensed beds" in lowered:
            if "hospital" not in lowered:
                return self.census_answer(question)
        if asks_for_top(question) and any(term in lowered for term in ["county", "capacity", "ltc", "long-term", "nursing"]):
            return self.top_county_answer(question)
        if not re.search(r"\b(how many|count|number of|total|rows?)\b", lowered):
            facility = self.facility_from_question(question)
            if facility is not None:
                return self.facility_answer(question, facility)
        county = self.county_from_question(question)
        city = self.city_from_question(question, county["county"] if county else None)
        if city:
            return self.city_answer(question, county["county"] if county else None, city)
        if county:
            return self.county_answer(question, county)
        return self.missing_answer(question)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    payload = build_data_mo_ltc_index(force=args.force)
    print(
        json.dumps(
            {
                key: value
                for key, value in payload.items()
                if key not in {"directory_rows", "county_rows", "census_rows"}
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
