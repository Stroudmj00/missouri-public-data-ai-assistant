"""Build and query selected aggregate DHSS WIC data."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw_public" / "data_mo_wic"
INDEX_PATH = RAW_DIR / "data_mo_wic_index.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "data_mo_wic_index_report.json"
DATASET_ID = "diyi-fr2a"
DATASET_NAME = "DHSS WIC Data"
DATA_URL = f"https://data.mo.gov/resource/{DATASET_ID}.json"
LANDING_PAGE = f"https://data.mo.gov/d/{DATASET_ID}"
METADATA_URL = f"https://data.mo.gov/api/views/{DATASET_ID}.json"
SFY_RE = re.compile(r"\bSFY\s*(\d{4})\b", flags=re.I)


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


def parse_int(value: Any) -> int:
    cleaned = clean_text(value).replace(",", "")
    return int(cleaned) if re.fullmatch(r"\d+", cleaned) else 0


def parse_decimal(value: Any) -> Decimal:
    cleaned = clean_text(value).replace(",", "")
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return Decimal("0")


def money_json(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def format_money(value: Any) -> str:
    amount = parse_decimal(value)
    return f"${amount:,.2f}"


def rows_updated_label(value: Any) -> str | None:
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).replace(microsecond=0).isoformat()


def socrata_get(session: requests.Session, params: dict[str, str | int]) -> tuple[list[dict[str, Any]], str]:
    response = session.get(DATA_URL, params=params, timeout=120)
    response.raise_for_status()
    return response.json(), response.text


def normalize_county_row(row: dict[str, Any]) -> dict[str, Any]:
    total = parse_decimal(row.get("net_benefit_total"))
    household_count = parse_int(row.get("household_count"))
    return {
        "county": clean_text(row.get("countyname")) or "Unlisted",
        "county_norm": normalize_text(row.get("countyname") or "Unlisted"),
        "household_count": household_count,
        "net_benefit_total": money_json(total),
        "average_net_benefit": money_json(total / household_count) if household_count else "0.00",
    }


def normalize_municipality_row(row: dict[str, Any]) -> dict[str, Any]:
    total = parse_decimal(row.get("net_benefit_total"))
    household_count = parse_int(row.get("household_count"))
    population = parse_int(row.get("population_2022"))
    return {
        "county": clean_text(row.get("countyname")) or "Unlisted",
        "county_norm": normalize_text(row.get("countyname") or "Unlisted"),
        "municipality": clean_text(row.get("municipality_name")) or "Unlisted",
        "municipality_norm": normalize_text(row.get("municipality_name") or "Unlisted"),
        "household_count": household_count,
        "net_benefit_total": money_json(total),
        "average_net_benefit": money_json(total / household_count) if household_count else "0.00",
        "population_2022": population if population else None,
    }


def build_data_mo_wic_index(force: bool = False) -> dict[str, Any]:
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
    description = clean_text(metadata.get("description"))
    sfy_match = SFY_RE.search(description)

    total_rows, total_text = socrata_get(
        session,
        {"$select": "count(*) as household_count,sum(net_benefit) as net_benefit_total"},
    )
    county_rows_raw, county_text = socrata_get(
        session,
        {
            "$select": "countyname,count(*) as household_count,sum(net_benefit) as net_benefit_total",
            "$group": "countyname",
            "$order": "net_benefit_total DESC",
            "$limit": 500,
        },
    )
    municipality_rows_raw, municipality_text = socrata_get(
        session,
        {
            "$select": "countyname,municipality_name,count(*) as household_count,sum(net_benefit) as net_benefit_total,max(population_2022) as population_2022",
            "$where": "municipality_name IS NOT NULL",
            "$group": "countyname,municipality_name",
            "$order": "net_benefit_total DESC",
            "$limit": 10000,
        },
    )

    total = total_rows[0] if total_rows else {}
    county_rows = [normalize_county_row(row) for row in county_rows_raw]
    municipality_rows = [normalize_municipality_row(row) for row in municipality_rows_raw]
    source_text = "\n".join([metadata_response.text, total_text, county_text, municipality_text])
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    write_json(RAW_DIR / "wic_county_aggregates.json", county_rows_raw)
    write_json(RAW_DIR / "wic_municipality_aggregates.json", municipality_rows_raw)

    payload = {
        "generated_at_utc": utc_now(),
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "source": DATASET_NAME,
        "source_url": DATA_URL,
        "landing_page": LANDING_PAGE,
        "metadata_url": METADATA_URL,
        "index_path": str(INDEX_PATH.relative_to(PROJECT_ROOT)),
        "dataset_id": DATASET_ID,
        "state_fiscal_year": int(sfy_match.group(1)) if sfy_match else None,
        "rows_updated_at_utc": rows_updated_label(metadata.get("rowsUpdatedAt")),
        "bytes": len(source_text.encode("utf-8")),
        "sha256": sha256_text(source_text),
        "source_household_rows": parse_int(total.get("household_count")),
        "net_benefit_total": money_json(parse_decimal(total.get("net_benefit_total"))),
        "county_count": len([row for row in county_rows if row["county"] != "Unlisted"]),
        "municipality_count": len([row for row in municipality_rows if row["municipality"] != "Unlisted"]),
        "description": description,
        "county_rows": county_rows,
        "municipality_rows": municipality_rows,
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
            "state_fiscal_year": payload["state_fiscal_year"],
            "rows_updated_at_utc": payload["rows_updated_at_utc"],
            "bytes": payload["bytes"],
            "sha256": payload["sha256"],
            "source_household_rows": payload["source_household_rows"],
            "net_benefit_total": payload["net_benefit_total"],
            "county_count": payload["county_count"],
            "municipality_count": payload["municipality_count"],
            "top_counties_by_net_benefit": county_rows[:10],
            "top_municipalities_by_net_benefit": municipality_rows[:10],
        },
    )
    return payload


def asks_for_top(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["top", "highest", "largest", "most"])


def asks_about_municipality(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["city", "municipality", "town", "columbia", "springfield", "kansas city", "st. louis"])


class DataMoWicIndex:
    def __init__(self, path: Path = INDEX_PATH) -> None:
        self.path = path
        self._payload: dict[str, Any] | None = None

    def available(self) -> bool:
        return self.path.exists() and self.path.stat().st_size > 0

    def payload(self) -> dict[str, Any]:
        if self._payload is None:
            self._payload = json.loads(self.path.read_text(encoding="utf-8")) if self.available() else {}
        return self._payload

    def county_rows(self) -> list[dict[str, Any]]:
        return list(self.payload().get("county_rows", []))

    def municipality_rows(self) -> list[dict[str, Any]]:
        return list(self.payload().get("municipality_rows", []))

    def citation(self, matched_rows: int = 0) -> list[dict[str, Any]]:
        payload = self.payload()
        return [
            {
                "dataset": payload.get("source", DATASET_NAME),
                "category": "Public health",
                "kind": "DHSS WIC aggregate rows",
                "lookup_table": "data_mo_wic_index",
                "year": payload.get("state_fiscal_year"),
                "year_range": None,
                "source_files": [
                    {
                        "category": "data_mo_wic",
                        "category_label": payload.get("source", DATASET_NAME),
                        "file_name": payload.get("landing_page", LANDING_PAGE),
                        "row_count": payload.get("source_household_rows"),
                        "bytes": payload.get("bytes"),
                        "sha256": payload.get("sha256"),
                    }
                ],
                "source_file_count": 1,
                "source_rows": payload.get("source_household_rows"),
                "matched_rows": matched_rows,
            }
        ]

    def unavailable_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "The selected DHSS WIC aggregate index has not been built yet. Run "
                "`python scripts/build_data_mo_wic_index.py --force` to build county and municipality aggregates."
            ),
            "retrieved_context_id": "data_mo_wic_index:missing",
            "retrieved_source": "data_mo_wic_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "The DHSS WIC route exists, but the local ignored index is missing.",
            "citations": [],
            "source_rows": [],
        }

    def summary_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        top_counties = "; ".join(
            f"{row['county']}: {format_money(row['net_benefit_total'])}"
            for row in self.county_rows()[:5]
        )
        return {
            "question": question,
            "answer": (
                f"The selected DHSS WIC exact aggregate layer indexes {payload.get('source_household_rows', 0):,} "
                f"public source household row(s) for SFY {payload.get('state_fiscal_year')}. It stores county and municipality aggregates only, "
                f"covering {payload.get('county_count', 0):,} counties and {payload.get('municipality_count', 0):,} municipalities. "
                f"Total redeemed net benefit: {format_money(payload.get('net_benefit_total'))}. "
                "It can answer county household counts, county benefit totals, top-county rankings, and municipality aggregates. "
                f"Top counties by redeemed benefit: {top_counties}."
            ),
            "retrieved_context_id": "data_mo_wic_index:summary",
            "retrieved_source": "data_mo_wic_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from aggregate Socrata queries over the DHSS WIC Data source; household identifiers are not stored or returned.",
            "citations": self.citation(matched_rows=payload.get("county_count", 0)),
            "source_rows": [],
        }

    def find_county(self, question: str) -> dict[str, Any] | None:
        question_norm = normalize_text(question)
        for row in sorted(self.county_rows(), key=lambda item: len(item.get("county_norm", "")), reverse=True):
            county_norm = row.get("county_norm", "")
            if county_norm and re.search(rf"\b{re.escape(county_norm)}\b", question_norm):
                return row
        return None

    def find_municipality(self, question: str) -> dict[str, Any] | None:
        question_norm = normalize_text(question)
        county = self.find_county(question)
        candidates = self.municipality_rows()
        if county is not None:
            candidates = [row for row in candidates if row.get("county_norm") == county.get("county_norm")]
        for row in sorted(candidates, key=lambda item: len(item.get("municipality_norm", "")), reverse=True):
            municipality_norm = row.get("municipality_norm", "")
            if municipality_norm and re.search(rf"\b{re.escape(municipality_norm)}\b", question_norm):
                return row
        return None

    def county_answer(self, question: str, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                f"The indexed DHSS WIC Data aggregate for SFY {self.payload().get('state_fiscal_year')} lists "
                f"{row['county']} County with {row['household_count']:,} household row(s), "
                f"{format_money(row['net_benefit_total'])} in redeemed net benefits, and an average net benefit of "
                f"{format_money(row['average_net_benefit'])}."
            ),
            "retrieved_context_id": f"data_mo_wic_index:county:{row['county_norm']}",
            "retrieved_source": "data_mo_wic_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from county-level aggregate Socrata query results; household identifiers are not stored or returned.",
            "citations": self.citation(matched_rows=1),
            "source_rows": [{"source_file": LANDING_PAGE, "values": row}],
        }

    def municipality_answer(self, question: str, row: dict[str, Any]) -> dict[str, Any]:
        population_text = f"; 2022 population: {row['population_2022']:,}" if row.get("population_2022") else ""
        return {
            "question": question,
            "answer": (
                f"The indexed DHSS WIC Data aggregate for SFY {self.payload().get('state_fiscal_year')} lists "
                f"{row['municipality']} in {row['county']} County with {row['household_count']:,} household row(s), "
                f"{format_money(row['net_benefit_total'])} in redeemed net benefits, and an average net benefit of "
                f"{format_money(row['average_net_benefit'])}{population_text}."
            ),
            "retrieved_context_id": f"data_mo_wic_index:municipality:{row['county_norm']}:{row['municipality_norm']}",
            "retrieved_source": "data_mo_wic_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from municipality-level aggregate Socrata query results; household identifiers are not stored or returned.",
            "citations": self.citation(matched_rows=1),
            "source_rows": [{"source_file": LANDING_PAGE, "values": row}],
        }

    def top_county_answer(self, question: str) -> dict[str, Any]:
        rows = self.county_rows()[:5]
        top = rows[0] if rows else {"county": "unknown", "net_benefit_total": "0", "household_count": 0}
        rendered = "; ".join(
            f"{row['county']}: {format_money(row['net_benefit_total'])} ({row['household_count']:,} household row(s))"
            for row in rows
        )
        return {
            "question": question,
            "answer": (
                f"In the indexed DHSS WIC Data aggregate for SFY {self.payload().get('state_fiscal_year')}, "
                f"the county with the highest redeemed net benefit total is {top['county']}: "
                f"{format_money(top['net_benefit_total'])}. Top counties: {rendered}."
            ),
            "retrieved_context_id": "data_mo_wic_index:rank:county_net_benefit",
            "retrieved_source": "data_mo_wic_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed by ranking county aggregate Socrata query results.",
            "citations": self.citation(matched_rows=len(self.county_rows())),
            "source_rows": [{"source_file": LANDING_PAGE, "values": row} for row in rows],
        }

    def missing_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "I have indexed selected DHSS WIC county and municipality aggregates, but this question did not match a supported county, "
                "municipality, or top-county ranking. Try `What DHSS WIC data is indexed?`, "
                "`How many WIC household rows are listed for Boone County?`, or "
                "`How many WIC household rows are listed for Columbia in Boone County?`."
            ),
            "retrieved_context_id": "data_mo_wic_index:no_match",
            "retrieved_source": "data_mo_wic_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Answered from DHSS WIC aggregate coverage metadata because no exact aggregate row matched.",
            "citations": self.citation(),
            "source_rows": [],
        }

    def answer(self, question: str) -> dict[str, Any] | None:
        if not self.available():
            return self.unavailable_answer(question)
        lowered = question.lower()
        if (
            re.search(r"\b(what|which|show|list)\b.*\b(wic|women infants children|dhss wic)\b.*\b(indexed|lookup|data|source)\b", lowered)
            or re.search(r"\b(wic|women infants children|dhss wic)\b.*\b(indexed|lookup|coverage)\b", lowered)
        ):
            return self.summary_answer(question)
        if asks_for_top(question) and any(term in lowered for term in ["county", "benefit", "wic"]):
            return self.top_county_answer(question)
        if asks_about_municipality(question):
            municipality = self.find_municipality(question)
            if municipality is not None:
                return self.municipality_answer(question, municipality)
        county = self.find_county(question)
        if county is not None:
            return self.county_answer(question, county)
        return self.missing_answer(question)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    payload = build_data_mo_wic_index(force=args.force)
    print(json.dumps({key: value for key, value in payload.items() if key not in {"county_rows", "municipality_rows"}}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
