"""Build and query selected Missouri hospital profile data from data.mo.gov."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw_public" / "data_mo_hospital_profile"
INDEX_PATH = RAW_DIR / "data_mo_hospital_index.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "data_mo_hospital_index_report.json"
LEGACY_RAW_PATH = PROJECT_ROOT / "data" / "raw_public" / "data_mo_hospital_profile.json"

DATASET_ID = "q8me-hzr8"
DATASET_NAME = "data.mo.gov Profile of Hospitals"
DATA_URL = f"https://data.mo.gov/resource/{DATASET_ID}.json"
LANDING_PAGE = f"https://data.mo.gov/d/{DATASET_ID}"
METADATA_URL = f"https://data.mo.gov/api/views/{DATASET_ID}.json"

BED_FIELDS = {
    "ltcbeds": "LTC beds",
    "med_surg_beds_licensed": "medical/surgical licensed beds",
    "pediatric_beds_licensed": "pediatric licensed beds",
    "icu_beds_licensed": "ICU licensed beds",
    "alcohol_drug_treatment_beds": "alcohol/drug treatment beds",
    "ob_beds_licensed": "OB licensed beds",
    "rehab_beds_licensed": "rehab licensed beds",
    "psych_beds_licensed": "psych licensed beds",
    "neo_natal_icu_beds_licensed": "neonatal ICU licensed beds",
    "total_beds_licensed_for_this": "total licensed beds",
}

GENERIC_HOSPITAL_TOKENS = {
    "AND",
    "AT",
    "CARE",
    "CENTER",
    "CENTERS",
    "CENTRE",
    "CITY",
    "COUNTY",
    "DATA",
    "HEALTH",
    "HEALTHCARE",
    "HOSP",
    "HOSPITAL",
    "HOSPITALS",
    "INDEX",
    "INDEXED",
    "LICENSED",
    "MEDICAL",
    "MEMORIAL",
    "MISSOURI",
    "MO",
    "OF",
    "PROFILE",
    "REGIONAL",
    "SAINT",
    "ST",
    "THE",
    "UNIVERSITY",
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


def date_label(value: Any) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    return text.split("T", 1)[0]


def rows_updated_label(value: Any) -> str | None:
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).replace(microsecond=0).isoformat()


def hospital_tokens(value: Any) -> set[str]:
    return {token for token in normalize_text(value).split() if token not in GENERIC_HOSPITAL_TOKENS and len(token) > 1}


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    facility_name = clean_text(row.get("facility_name"))
    city = clean_text(row.get("city"))
    county = clean_text(row.get("county"))
    region = clean_text(row.get("region"))
    record = {
        "facility_id": clean_text(row.get("facility_id")),
        "facility_name": facility_name,
        "facility_name_norm": normalize_text(facility_name),
        "city": city,
        "city_norm": normalize_text(city),
        "county": county,
        "county_norm": normalize_text(county),
        "region": region,
        "region_norm": normalize_text(region),
        "facility_type": clean_text(row.get("facility_type")),
        "hospital_license_type": clean_text(row.get("hospital_license_type")),
        "accredited": bool(row.get("accredited")),
        "accrediting_body": clean_text(row.get("accredbody")),
        "cms_provider_number": clean_text(row.get("cms_provider_number")),
        "current_license_expiration": date_label(row.get("current_license_expiration")),
        "source_url": DATA_URL,
        "landing_page": LANDING_PAGE,
    }
    for field in BED_FIELDS:
        record[field] = parse_int(row.get(field))
    return record


def fetch_hospital_rows(force: bool) -> tuple[list[dict[str, Any]], str, dict[str, Any], str]:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (compatible; MissouriPublicDataChat/1.0; +https://github.com/Stroudmj00/missouri-tiny-llm-case-study)",
            "Accept": "application/json,*/*;q=0.8",
        }
    )
    metadata: dict[str, Any] = {}
    fetch_note = "downloaded from Socrata API"
    try:
        metadata_response = session.get(METADATA_URL, timeout=60)
        metadata_response.raise_for_status()
        metadata = metadata_response.json()
    except requests.RequestException:
        metadata = {}

    if force or not LEGACY_RAW_PATH.exists():
        try:
            response = session.get(DATA_URL, params={"$limit": 5000}, timeout=90)
            response.raise_for_status()
            return response.json(), response.text, metadata, fetch_note
        except requests.RequestException:
            if not LEGACY_RAW_PATH.exists():
                raise
            fetch_note = "used existing local raw file because Socrata download failed"

    raw_text = LEGACY_RAW_PATH.read_text(encoding="utf-8")
    return json.loads(raw_text), raw_text, metadata, fetch_note if force else "used existing local raw file"


def top_items(counter: Counter[str], limit: int = 12) -> list[dict[str, Any]]:
    return [{"label": label, "count": count} for label, count in counter.most_common(limit) if label]


def build_data_mo_hospital_index(force: bool = False) -> dict[str, Any]:
    if INDEX_PATH.exists() and not force:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))

    start = time.perf_counter()
    raw_rows, raw_text, metadata, fetch_note = fetch_hospital_rows(force=force)
    records = sorted(
        [normalize_row(row) for row in raw_rows],
        key=lambda item: (item["region_norm"], item["county_norm"], item["city_norm"], item["facility_name_norm"]),
    )
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    write_json(RAW_DIR / "hospital_profile_rows.json", raw_rows)

    region_groups: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    county_groups: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    license_counts: Counter[str] = Counter()
    region_counts: Counter[str] = Counter()
    county_counts: Counter[str] = Counter()
    for record in records:
        region_groups[record["region"]].append(record)
        county_groups[record["county"]].append(record)
        license_counts[record["hospital_license_type"]] += 1
        region_counts[record["region"]] += 1
        county_counts[record["county"]] += 1

    region_summaries = []
    for region, rows in region_groups.items():
        region_summaries.append(
            {
                "region": region,
                "facility_count": len(rows),
                "total_licensed_beds": sum(row["total_beds_licensed_for_this"] for row in rows),
                "total_icu_beds": sum(row["icu_beds_licensed"] for row in rows),
            }
        )
    region_summaries.sort(key=lambda item: (-item["total_licensed_beds"], item["region"]))

    county_summaries = []
    for county, rows in county_groups.items():
        county_summaries.append(
            {
                "county": county,
                "facility_count": len(rows),
                "total_licensed_beds": sum(row["total_beds_licensed_for_this"] for row in rows),
                "total_icu_beds": sum(row["icu_beds_licensed"] for row in rows),
            }
        )
    county_summaries.sort(key=lambda item: (-item["total_licensed_beds"], item["county"]))

    top_facilities = sorted(records, key=lambda item: (-item["total_beds_licensed_for_this"], item["facility_name_norm"]))[:12]
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
        "fetch_note": fetch_note,
        "record_count": len(records),
        "columns": [column.get("name") for column in metadata.get("columns", []) if column.get("name")],
        "total_licensed_beds": sum(record["total_beds_licensed_for_this"] for record in records),
        "total_icu_beds": sum(record["icu_beds_licensed"] for record in records),
        "accredited_count": sum(1 for record in records if record.get("accredited")),
        "region_count": len(region_groups),
        "county_count": len(county_groups),
        "top_regions_by_licensed_beds": region_summaries[:12],
        "top_counties_by_licensed_beds": county_summaries[:12],
        "top_facilities_by_licensed_beds": [
            {
                "facility_id": record["facility_id"],
                "facility_name": record["facility_name"],
                "city": record["city"],
                "county": record["county"],
                "region": record["region"],
                "hospital_license_type": record["hospital_license_type"],
                "total_licensed_beds": record["total_beds_licensed_for_this"],
                "icu_beds_licensed": record["icu_beds_licensed"],
            }
            for record in top_facilities
        ],
        "license_type_counts": top_items(license_counts),
        "region_record_counts": top_items(region_counts),
        "county_record_counts": top_items(county_counts),
        "sanitization_note": (
            "The local hospital lookup keeps public facility names, city/county/region, license type, bed-count fields, "
            "accreditation flags, CMS provider number, and license-expiration date. It does not return address, phone, fax, "
            "or administrator-name fields in chatbot answers or source-row previews."
        ),
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
            "metadata_url": payload["metadata_url"],
            "index_path": payload["index_path"],
            "dataset_id": payload["dataset_id"],
            "rows_updated_at_utc": payload["rows_updated_at_utc"],
            "bytes": payload["bytes"],
            "sha256": payload["sha256"],
            "fetch_note": payload["fetch_note"],
            "record_count": payload["record_count"],
            "total_licensed_beds": payload["total_licensed_beds"],
            "total_icu_beds": payload["total_icu_beds"],
            "accredited_count": payload["accredited_count"],
            "region_count": payload["region_count"],
            "county_count": payload["county_count"],
            "top_regions_by_licensed_beds": payload["top_regions_by_licensed_beds"],
            "top_counties_by_licensed_beds": payload["top_counties_by_licensed_beds"],
            "top_facilities_by_licensed_beds": payload["top_facilities_by_licensed_beds"],
            "license_type_counts": payload["license_type_counts"],
            "sanitization_note": payload["sanitization_note"],
        },
    )
    return payload


def asks_for_coverage(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["what data", "indexed", "coverage", "summary", "source", "profile data"])


def asks_for_top(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["top", "highest", "largest", "most"])


def asks_for_contact_field(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["address", "phone", "fax", "administrator", "president", "ceo", "contact"])


def metric_for_question(question: str) -> tuple[str, str]:
    lowered = question.lower()
    if "icu" in lowered:
        return "icu_beds_licensed", "ICU licensed beds"
    if "med" in lowered or "surg" in lowered:
        return "med_surg_beds_licensed", "medical/surgical licensed beds"
    if "pediatric" in lowered:
        return "pediatric_beds_licensed", "pediatric licensed beds"
    if "psych" in lowered or "psychiatric" in lowered:
        return "psych_beds_licensed", "psych licensed beds"
    if "rehab" in lowered:
        return "rehab_beds_licensed", "rehab licensed beds"
    if re.search(r"\bob\b|\bobstetric", lowered):
        return "ob_beds_licensed", "OB licensed beds"
    if "neonatal" in lowered or "neo natal" in lowered or "nicu" in lowered:
        return "neo_natal_icu_beds_licensed", "neonatal ICU licensed beds"
    if "alcohol" in lowered or "drug" in lowered:
        return "alcohol_drug_treatment_beds", "alcohol/drug treatment beds"
    if "ltc" in lowered or "long-term" in lowered or "long term" in lowered:
        return "ltcbeds", "LTC beds"
    return "total_beds_licensed_for_this", "licensed beds"


class DataMoHospitalIndex:
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
        source_files = [
            {
                "category": "data_mo_hospital_profile",
                "category_label": payload.get("source", DATASET_NAME),
                "file_name": payload.get("landing_page", LANDING_PAGE),
                "source_url": payload.get("landing_page", LANDING_PAGE),
                "row_count": payload.get("record_count"),
                "bytes": payload.get("bytes"),
                "sha256": payload.get("sha256"),
            },
            {
                "category": "data_mo_hospital_profile",
                "category_label": "Socrata JSON resource",
                "file_name": payload.get("source_url", DATA_URL),
                "source_url": payload.get("source_url", DATA_URL),
                "row_count": payload.get("record_count"),
                "bytes": payload.get("bytes"),
                "sha256": payload.get("sha256"),
            },
        ]
        return [
            {
                "dataset": payload.get("source", DATASET_NAME),
                "category": "data.mo.gov Profile of Hospitals",
                "kind": "hospital profile lookup",
                "lookup_table": "data_mo_hospital_lookup",
                "year": None,
                "year_range": None,
                "source_files": source_files,
                "source_file_count": len(source_files),
                "source_rows": payload.get("record_count"),
                "matched_rows": matched_rows,
            }
        ]

    def source_row(self, record: dict[str, Any]) -> dict[str, Any]:
        values = {
            "facility_id": record.get("facility_id"),
            "facility_name": record.get("facility_name"),
            "city": record.get("city"),
            "county": record.get("county"),
            "region": record.get("region"),
            "hospital_license_type": record.get("hospital_license_type"),
            "total_licensed_beds": record.get("total_beds_licensed_for_this"),
            "icu_beds_licensed": record.get("icu_beds_licensed"),
            "med_surg_beds_licensed": record.get("med_surg_beds_licensed"),
            "pediatric_beds_licensed": record.get("pediatric_beds_licensed"),
            "psych_beds_licensed": record.get("psych_beds_licensed"),
            "accredited": record.get("accredited"),
            "license_expiration": record.get("current_license_expiration"),
        }
        return {"source_file": LANDING_PAGE, "source_row_number": record.get("facility_id") or "-", "values": values}

    def unavailable_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "The data.mo.gov hospital profile route exists, but the local ignored hospital index is missing. "
                "Run `python scripts/build_data_mo_hospital_index.py --force` to build it."
            ),
            "retrieved_context_id": "data_mo_hospital:index_missing",
            "retrieved_source": "data_mo_hospital_lookup_index",
            "retrieval_score": 0.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Hospital source registry is available, but the local ignored index is missing.",
            "citations": [],
            "source_rows": [],
        }

    def coverage_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        license_types = "; ".join(f"{item['label']}: {item['count']}" for item in payload.get("license_type_counts", [])[:4])
        top_region = (payload.get("top_regions_by_licensed_beds") or [{}])[0]
        answer = (
            f"The hospital profile index covers {payload.get('record_count', 0):,} public facility row(s), "
            f"{payload.get('total_licensed_beds', 0):,} licensed beds, and "
            f"{payload.get('total_icu_beds', 0):,} ICU licensed beds. "
            f"The largest indexed region by licensed beds is {top_region.get('region', 'not listed')} "
            f"with {top_region.get('total_licensed_beds', 0):,}. "
            f"License-type counts include {license_types}. "
            "The chatbot does not display hospital address, phone, fax, or administrator-name fields."
        )
        return {
            "question": question,
            "answer": answer,
            "retrieved_context_id": "data_mo_hospital:coverage",
            "retrieved_source": "data_mo_hospital_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": self.payload().get("sanitization_note"),
            "citations": self.citation(matched_rows=payload.get("record_count", 0)),
            "source_rows": [],
        }

    def total_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        metric, label = metric_for_question(question)
        total_key = "total_icu_beds" if metric == "icu_beds_licensed" else "total_licensed_beds"
        if metric not in {"icu_beds_licensed", "total_beds_licensed_for_this"}:
            value = sum(record.get(metric, 0) for record in self.records())
        else:
            value = payload.get(total_key, 0)
        answer = (
            f"The indexed data.mo.gov hospital profile lists {value:,} {label} "
            f"across {payload.get('record_count', 0):,} public hospital profile row(s). "
            "This is a public facility-profile aggregate, not medical advice or a quality ranking."
        )
        return {
            "question": question,
            "answer": answer,
            "retrieved_context_id": f"data_mo_hospital:total:{metric}",
            "retrieved_source": "data_mo_hospital_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": self.payload().get("sanitization_note"),
            "citations": self.citation(matched_rows=payload.get("record_count", 0)),
            "source_rows": [],
        }

    def find_facility(self, question: str) -> dict[str, Any] | None:
        q_norm = normalize_text(question)
        q_tokens = hospital_tokens(question)
        matches: list[tuple[int, int, dict[str, Any]]] = []
        for record in self.records():
            name_norm = record.get("facility_name_norm", "")
            name_tokens = hospital_tokens(record.get("facility_name", ""))
            if name_norm and name_norm in q_norm:
                matches.append((1000 + len(name_tokens), len(record.get("facility_name", "")), record))
                continue
            overlap = q_tokens & name_tokens
            if len(overlap) >= 2 and overlap == name_tokens:
                matches.append((100 + len(overlap), len(record.get("facility_name", "")), record))
            elif len(overlap) >= 2:
                matches.append((len(overlap), len(record.get("facility_name", "")), record))
        if not matches:
            return None
        matches.sort(key=lambda item: (-item[0], -item[1], item[2].get("facility_name_norm", "")))
        return matches[0][2]

    def facility_answer(self, question: str, record: dict[str, Any]) -> dict[str, Any]:
        if asks_for_contact_field(question):
            answer = (
                f"{record.get('facility_name')} is in {record.get('city')}, {record.get('county')} County/area. "
                "This prototype does not display hospital address, phone, fax, or administrator-name fields; use the linked official data page if you need the full public source record."
            )
        elif "license type" in question.lower() or "type" in question.lower():
            answer = (
                f"{record.get('facility_name')} is listed as {record.get('hospital_license_type') or 'not listed'} "
                f"in the hospital profile. City: {record.get('city')}; county/area: {record.get('county')}; "
                f"region: {record.get('region')}."
            )
        else:
            metric, label = metric_for_question(question)
            value = record.get(metric, 0)
            answer = (
                f"{record.get('facility_name')} is listed with {value:,} {label}. "
                f"Profile context: {record.get('city')}, {record.get('county')} County/area; "
                f"{record.get('region')} region; {record.get('hospital_license_type')}. "
                "This is a public facility-profile value, not medical advice or a quality ranking."
            )
        return {
            "question": question,
            "answer": answer,
            "retrieved_context_id": f"data_mo_hospital:facility:{record.get('facility_id')}",
            "retrieved_source": "data_mo_hospital_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": self.payload().get("sanitization_note"),
            "citations": self.citation(matched_rows=1),
            "source_rows": [self.source_row(record)],
        }

    def top_facility_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        rows = payload.get("top_facilities_by_licensed_beds", [])
        if not rows:
            return self.total_answer(question)
        limit = 5 if re.search(r"\btop\s+5\b", question.lower()) else 1
        selected = rows[:limit]
        if limit == 1:
            row = selected[0]
            answer = (
                f"The hospital with the most indexed licensed beds is {row['facility_name']} "
                f"with {row['total_licensed_beds']:,} licensed beds and {row['icu_beds_licensed']:,} ICU licensed beds. "
                f"Location context: {row['city']}, {row['county']} County/area; {row['region']} region."
            )
            source_rows = []
            record = self.find_facility(row["facility_name"])
            if record:
                source_rows = [self.source_row(record)]
        else:
            lines = [
                f"{index}. {row['facility_name']} - {row['total_licensed_beds']:,} licensed beds ({row['city']}, {row['county']})"
                for index, row in enumerate(selected, 1)
            ]
            answer = "Top indexed hospitals by licensed beds:\n" + "\n".join(lines)
            source_rows = []
        return {
            "question": question,
            "answer": answer,
            "retrieved_context_id": "data_mo_hospital:top_facilities",
            "retrieved_source": "data_mo_hospital_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": self.payload().get("sanitization_note"),
            "citations": self.citation(matched_rows=len(selected)),
            "source_rows": source_rows,
        }

    def region_answer(self, question: str) -> dict[str, Any] | None:
        q_norm = normalize_text(question)
        lowered = question.lower()
        payload = self.payload()
        regions = payload.get("top_regions_by_licensed_beds", [])
        top_region = regions[0] if regions else None
        if asks_for_top(question) and top_region and "region" in lowered:
            return {
                "question": question,
                "answer": (
                    f"The hospital-profile region with the most indexed licensed beds is {top_region['region']} "
                    f"with {top_region['total_licensed_beds']:,} licensed beds across "
                    f"{top_region['facility_count']:,} facility row(s)."
                ),
                "retrieved_context_id": "data_mo_hospital:top_region",
                "retrieved_source": "data_mo_hospital_lookup_index",
                "retrieval_score": 1.0,
                "used_model": False,
                "model": "deterministic_public_lookup",
                "source_note": self.payload().get("sanitization_note"),
                "citations": self.citation(matched_rows=top_region["facility_count"]),
                "source_rows": [],
            }
        for region in regions:
            region_norm = normalize_text(region.get("region", ""))
            if region_norm and region_norm in q_norm:
                return {
                    "question": question,
                    "answer": (
                        f"The {region['region']} hospital-profile region has {region['total_licensed_beds']:,} "
                        f"licensed beds and {region['total_icu_beds']:,} ICU licensed beds across "
                        f"{region['facility_count']:,} facility row(s)."
                    ),
                    "retrieved_context_id": f"data_mo_hospital:region:{region_norm}",
                    "retrieved_source": "data_mo_hospital_lookup_index",
                    "retrieval_score": 1.0,
                    "used_model": False,
                    "model": "deterministic_public_lookup",
                    "source_note": self.payload().get("sanitization_note"),
                    "citations": self.citation(matched_rows=region["facility_count"]),
                    "source_rows": [],
                }
        return None

    def answer(self, question: str) -> dict[str, Any] | None:
        if not self.available():
            return self.unavailable_answer(question)
        if asks_for_coverage(question):
            return self.coverage_answer(question)
        region_result = self.region_answer(question)
        if region_result is not None:
            return region_result
        facility = self.find_facility(question)
        if facility is not None:
            return self.facility_answer(question, facility)
        if asks_for_top(question):
            return self.top_facility_answer(question)
        if any(term in question.lower() for term in ["bed", "beds", "icu", "licensed", "facility", "facilities"]):
            return self.total_answer(question)
        return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Rebuild the ignored local hospital index")
    args = parser.parse_args()
    payload = build_data_mo_hospital_index(force=args.force)
    print(json.dumps({key: payload[key] for key in ["source", "record_count", "total_licensed_beds", "total_icu_beds"]}, indent=2))


if __name__ == "__main__":
    main()
