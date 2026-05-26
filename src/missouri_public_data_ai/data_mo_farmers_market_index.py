"""Build and query selected Missouri Farmers' Markets data from data.mo.gov."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw_public" / "data_mo_farmers_markets"
INDEX_PATH = RAW_DIR / "data_mo_farmers_market_index.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "data_mo_farmers_market_index_report.json"
DATASET_ID = "2zg8-cta8"
DATASET_NAME = "Missouri Farmers' Markets"
DATA_URL = f"https://data.mo.gov/resource/{DATASET_ID}.json"
LANDING_PAGE = f"https://data.mo.gov/d/{DATASET_ID}"
METADATA_URL = f"https://data.mo.gov/api/views/{DATASET_ID}.json"

GENERIC_BUSINESS_TOKENS = {
    "AND",
    "BUSINESS",
    "COMPANY",
    "CO",
    "COUNTY",
    "DATA",
    "FARM",
    "FARMERS",
    "FARMER",
    "FARMS",
    "INDEX",
    "INDEXED",
    "LLC",
    "MARKET",
    "MARKETS",
    "MISSOURI",
    "MO",
    "OF",
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
    return re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()


def normalize_text(value: str) -> str:
    cleaned = re.sub(r"[^A-Z0-9&./'-]+", " ", clean_text(value).upper())
    return re.sub(r"\s+", " ", cleaned).strip()


def business_tokens(value: str) -> set[str]:
    return {token for token in normalize_text(value).split() if token not in GENERIC_BUSINESS_TOKENS}


def rows_updated_label(value: Any) -> str | None:
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).replace(microsecond=0).isoformat()


def url_value(value: Any) -> str:
    if isinstance(value, dict):
        return clean_text(value.get("url"))
    return clean_text(value)


def latlong_value(value: Any, key: str) -> str:
    if not isinstance(value, dict):
        return ""
    return clean_text(value.get(key))


def short_excerpt(value: str, limit: int = 220) -> str:
    cleaned = clean_text(value)
    if len(cleaned) <= limit:
        return cleaned
    clipped = cleaned[:limit].rsplit(" ", 1)[0].rstrip(" ,;:")
    return f"{clipped}."


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    business_name = clean_text(row.get("business_name"))
    county = clean_text(row.get("county"))
    city = clean_text(row.get("city"))
    state = clean_text(row.get("state")).upper()
    latlong = row.get("latlong")
    return {
        "business_name": business_name,
        "business_norm": normalize_text(business_name),
        "address1": clean_text(row.get("address1")),
        "address2": clean_text(row.get("address2")),
        "city": city,
        "city_norm": normalize_text(city),
        "state": state,
        "zip_code": clean_text(row.get("zipcode")),
        "county": county,
        "county_norm": normalize_text(county),
        "website_url": url_value(row.get("website")),
        "company_profile": clean_text(row.get("company_profile")),
        "company_description": clean_text(row.get("company_description")),
        "location_description": clean_text(row.get("location_description")),
        "latitude": latlong_value(latlong, "latitude"),
        "longitude": latlong_value(latlong, "longitude"),
        "source_url": DATA_URL,
        "landing_page": LANDING_PAGE,
    }


def sanitized_source_rows(raw_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [normalize_row(row) for row in raw_rows]


def top_counts(counter: Counter[str], limit: int = 12) -> list[dict[str, Any]]:
    return [
        {"label": label, "count": count}
        for label, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:limit]
        if label
    ]


def build_data_mo_farmers_market_index(force: bool = False) -> dict[str, Any]:
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
    metadata_response = session.get(METADATA_URL, timeout=60)
    metadata_response.raise_for_status()
    metadata = metadata_response.json()
    response = session.get(DATA_URL, params={"$limit": 50000}, timeout=60)
    response.raise_for_status()
    raw_text = response.text
    raw_rows = response.json()
    records = sorted(
        sanitized_source_rows(raw_rows),
        key=lambda item: (item["county_norm"], item["city_norm"], item["business_norm"]),
    )

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    write_json(RAW_DIR / "farmers_market_rows_sanitized.json", records)

    county_counts = Counter(record["county"] for record in records if record["county"])
    city_counts = Counter(record["city"] for record in records if record["city"])
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
        "city_count": len(city_counts),
        "business_count": len({record["business_norm"] for record in records if record["business_norm"]}),
        "columns": [column.get("name") for column in metadata.get("columns", []) if column.get("name")],
        "suppressed_fields": ["contact name", "email"],
        "sanitization_note": "The source table includes public contact_name and email fields; assistant answers, row previews, and the local index suppress them.",
        "top_counties": top_counts(county_counts),
        "top_cities": top_counts(city_counts),
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
            "business_count": payload["business_count"],
            "columns": payload["columns"],
            "suppressed_fields": payload["suppressed_fields"],
            "sanitization_note": payload["sanitization_note"],
            "top_counties": payload["top_counties"],
            "top_cities": payload["top_cities"],
        },
    )
    return payload


def asks_for_count(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["how many", "count", "number of", "total"])


def asks_for_top(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["top", "highest", "largest", "most"])


def asks_for_location_or_detail(question: str) -> bool:
    lowered = question.lower()
    return any(
        term in lowered
        for term in [
            "address",
            "description",
            "details",
            "located",
            "location",
            "open",
            "profile",
            "website",
            "where is",
        ]
    )


class DataMoFarmersMarketIndex:
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
                "category": "data_mo_farmers_market",
                "category_label": payload.get("source", DATASET_NAME),
                "file_name": payload.get("landing_page", LANDING_PAGE),
                "source_url": payload.get("landing_page", LANDING_PAGE),
                "row_count": payload.get("record_count"),
                "bytes": payload.get("bytes"),
                "sha256": payload.get("sha256"),
            },
            {
                "category": "data_mo_farmers_market",
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
                "category": "Agriculture",
                "kind": "farmers-market public directory rows",
                "lookup_table": "data_mo_farmers_market_index",
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
                "The selected data.mo.gov Missouri Farmers' Markets index has not been built yet. Run "
                "`python scripts/build_data_mo_farmers_market_index.py --force` to download the public directory table and build exact lookups."
            ),
            "retrieved_context_id": "data_mo_farmers_market_index:missing",
            "retrieved_source": "data_mo_farmers_market_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "The farmers-market route exists, but the local ignored index is missing.",
            "citations": [],
            "source_rows": [],
        }

    def render_address(self, record: dict[str, Any]) -> str:
        street = " ".join(clean_text(part) for part in [record.get("address1"), record.get("address2")] if clean_text(part))
        parts = [street, record.get("city"), record.get("state"), record.get("zip_code")]
        return ", ".join(clean_text(part) for part in parts if clean_text(part))

    def source_rows(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows = []
        for record in records[:5]:
            rows.append(
                {
                    "source_file": LANDING_PAGE,
                    "source_row_number": record.get("business_name"),
                    "values": {
                        "Business": record.get("business_name"),
                        "County": record.get("county"),
                        "City": record.get("city"),
                        "Public address": self.render_address(record),
                        "Website": record.get("website_url"),
                        "Listing excerpt": short_excerpt(record.get("company_profile") or record.get("company_description") or record.get("location_description") or ""),
                    },
                }
            )
        return rows

    def summary_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        top_counties = "; ".join(f"{item['label']}: {item['count']}" for item in payload.get("top_counties", [])[:5])
        top_cities = "; ".join(f"{item['label']}: {item['count']}" for item in payload.get("top_cities", [])[:5])
        return {
            "question": question,
            "answer": (
                f"The selected data.mo.gov Missouri Farmers' Markets exact lookup layer indexes {payload.get('record_count', 0):,} "
                f"public directory listing row(s) across {payload.get('county_count', 0):,} counties and "
                f"{payload.get('city_count', 0):,} cities. It can answer county counts, city lookups, business/listing lookups, "
                f"top-county rankings, public websites, public addresses, and short listing descriptions. Top counties: {top_counties}. "
                f"Top cities: {top_cities}. Listings can change; check the official source or business website before relying on hours or availability."
            ),
            "retrieved_context_id": "data_mo_farmers_market_index:summary",
            "retrieved_source": "data_mo_farmers_market_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local data.mo.gov Missouri Farmers' Markets index; this is public directory information, not an endorsement or availability guarantee.",
            "citations": self.citation(),
            "source_rows": [],
        }

    def county_from_question(self, question: str) -> str | None:
        normalized_question = normalize_text(question)
        for county in sorted({record["county"] for record in self.records() if record.get("county")}, key=len, reverse=True):
            if re.search(rf"\b{re.escape(normalize_text(county))}\b", normalized_question):
                return county
        return None

    def city_from_question(self, question: str, county: str | None = None) -> str | None:
        normalized_question = normalize_text(question)
        records = self.records()
        if county:
            county_norm = normalize_text(county)
            records = [record for record in records if record.get("county_norm") == county_norm]
        for city in sorted({record["city"] for record in records if record.get("city")}, key=len, reverse=True):
            if re.search(rf"\b{re.escape(normalize_text(city))}\b", normalized_question):
                return city
        return None

    def matching_business_records(self, question: str) -> list[dict[str, Any]]:
        question_tokens = business_tokens(question)
        if not question_tokens:
            return []
        scored: list[tuple[float, str, dict[str, Any]]] = []
        for record in self.records():
            tokens = business_tokens(record.get("business_name", ""))
            if not tokens:
                continue
            overlap = len(question_tokens & tokens)
            if overlap >= min(2, len(tokens)):
                scored.append((overlap / len(tokens), record.get("business_name", ""), record))
        if not scored:
            return []
        scored.sort(key=lambda item: (-item[0], item[1], item[2].get("county", "")))
        best_business = scored[0][1]
        return [record for _, business, record in scored if business == best_business]

    def business_answer(self, question: str, records: list[dict[str, Any]]) -> dict[str, Any]:
        record = records[0]
        excerpt = short_excerpt(record.get("company_profile") or record.get("company_description") or record.get("location_description") or "")
        detail = (
            f"{record['business_name']} is listed in the data.mo.gov Missouri Farmers' Markets dataset for {record['city']}, "
            f"{record['county']} County. Public address: {self.render_address(record) or 'not listed'}. "
            f"Website: {record.get('website_url') or 'not listed'}."
        )
        if excerpt:
            detail += f" Listing excerpt: {excerpt}"
        if len(records) > 1:
            detail += f" The index has {len(records)} row(s) with that listing name; source row previews are capped."
        detail += " Listings can change; check the official source or business website before relying on hours or availability."
        return {
            "question": question,
            "answer": detail,
            "retrieved_context_id": f"data_mo_farmers_market_index:business:{record['business_norm']}",
            "retrieved_source": "data_mo_farmers_market_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local data.mo.gov Missouri Farmers' Markets index; contact name and email fields are suppressed.",
            "citations": self.citation(matched_rows=len(records)),
            "source_rows": self.source_rows(records),
        }

    def county_answer(self, question: str, county: str) -> dict[str, Any]:
        matches = [record for record in self.records() if record.get("county") == county]
        examples = "; ".join(
            f"{record['business_name']} ({record['city']})" for record in sorted(matches, key=lambda item: (item["city_norm"], item["business_norm"]))[:5]
        )
        return {
            "question": question,
            "answer": (
                f"The indexed data.mo.gov Missouri Farmers' Markets dataset has {len(matches):,} listing row(s) in {county} County. "
                f"Example listings: {examples}. Listings can change; check the official source or business website before relying on hours or availability."
            ),
            "retrieved_context_id": f"data_mo_farmers_market_index:county:{normalize_text(county)}",
            "retrieved_source": "data_mo_farmers_market_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local data.mo.gov Missouri Farmers' Markets index; contact name and email fields are suppressed.",
            "citations": self.citation(matched_rows=len(matches)),
            "source_rows": self.source_rows(matches),
        }

    def city_answer(self, question: str, city: str, county: str | None = None) -> dict[str, Any]:
        matches = [record for record in self.records() if record.get("city") == city]
        if county:
            matches = [record for record in matches if record.get("county") == county]
        place = f"{city}, {county} County" if county else city
        examples = "; ".join(
            f"{record['business_name']} ({self.render_address(record) or 'address not listed'})"
            for record in sorted(matches, key=lambda item: (item["county_norm"], item["business_norm"]))[:5]
        )
        return {
            "question": question,
            "answer": (
                f"The indexed data.mo.gov Missouri Farmers' Markets dataset has {len(matches):,} listing row(s) for {place}. "
                f"Listings: {examples}. Listings can change; check the official source or business website before relying on hours or availability."
            ),
            "retrieved_context_id": f"data_mo_farmers_market_index:city:{normalize_text(place)}",
            "retrieved_source": "data_mo_farmers_market_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local data.mo.gov Missouri Farmers' Markets index; contact name and email fields are suppressed.",
            "citations": self.citation(matched_rows=len(matches)),
            "source_rows": self.source_rows(matches),
        }

    def top_county_answer(self, question: str) -> dict[str, Any]:
        top = self.payload().get("top_counties", [])[:8]
        rendered = "; ".join(f"{item['label']}: {item['count']}" for item in top)
        return {
            "question": question,
            "answer": f"Top indexed counties by data.mo.gov Missouri Farmers' Markets listing rows: {rendered}.",
            "retrieved_context_id": "data_mo_farmers_market_index:top_counties",
            "retrieved_source": "data_mo_farmers_market_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed by ranking county counts in the local data.mo.gov Missouri Farmers' Markets index.",
            "citations": self.citation(),
            "source_rows": [],
        }

    def missing_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "I have indexed the public data.mo.gov Missouri Farmers' Markets dataset, but this question did not match a supported county, city, "
                "listing, or top-county ranking. Try `What farmers market data is indexed?`, "
                "`How many farmers markets are listed in Adair County?`, or `Where is Kiwanis Club of Kirksville Farmers' Market listed?`."
            ),
            "retrieved_context_id": "data_mo_farmers_market_index:no_match",
            "retrieved_source": "data_mo_farmers_market_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Answered from farmers-market coverage metadata because no exact row matched.",
            "citations": self.citation(),
            "source_rows": [],
        }

    def answer(self, question: str) -> dict[str, Any] | None:
        if not self.available():
            return self.unavailable_answer(question)

        lowered = question.lower()
        if (
            re.search(r"\b(what|which|show|list)\b.*\bfarmers?'?\s+market(?:s)?\b.*\b(indexed|lookup|data|source|sources|coverage)\b", lowered)
            or re.search(r"\bfarmers?'?\s+market(?:s)?\b.*\b(indexed|lookup|coverage|source|sources|data)\b", lowered)
        ):
            return self.summary_answer(question)

        business_matches = self.matching_business_records(question)
        if business_matches and asks_for_location_or_detail(question):
            return self.business_answer(question, business_matches)

        county = self.county_from_question(question)
        city = self.city_from_question(question, county=county)
        if city:
            return self.city_answer(question, city, county=county)

        if county:
            return self.county_answer(question, county)

        if asks_for_top(question):
            return self.top_county_answer(question)

        if asks_for_count(question):
            return self.summary_answer(question)

        if business_matches:
            return self.business_answer(question, business_matches)

        return self.missing_answer(question)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build selected data.mo.gov Missouri Farmers' Markets lookup index.")
    parser.add_argument("--force", action="store_true", help="Rebuild even when the local index already exists.")
    args = parser.parse_args()
    payload = build_data_mo_farmers_market_index(force=args.force)
    print(
        json.dumps(
            {
                "index_path": payload["index_path"],
                "records": payload["record_count"],
                "counties": payload["county_count"],
                "cities": payload["city_count"],
                "businesses": payload["business_count"],
                "rows_updated_at_utc": payload["rows_updated_at_utc"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
