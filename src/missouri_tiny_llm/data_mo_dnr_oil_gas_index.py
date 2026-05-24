"""Build and query selected Missouri DNR oil and gas permit data from data.mo.gov."""

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
RAW_DIR = PROJECT_ROOT / "data" / "raw_public" / "data_mo_dnr_oil_gas"
INDEX_PATH = RAW_DIR / "data_mo_dnr_oil_gas_index.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "data_mo_dnr_oil_gas_index_report.json"
DATASET_ID = "y64b-aec2"
DATASET_NAME = "Oil and Gas Permits"
DATA_URL = f"https://data.mo.gov/resource/{DATASET_ID}.json"
LANDING_PAGE = f"https://data.mo.gov/d/{DATASET_ID}"
METADATA_URL = f"https://data.mo.gov/api/views/{DATASET_ID}.json"

GENERIC_PERMIT_TOKENS = {
    "AND",
    "DATA",
    "DNR",
    "GAS",
    "INDEX",
    "INDEXED",
    "MISSOURI",
    "MO",
    "OIL",
    "PERMIT",
    "PERMITS",
    "THE",
    "WELL",
    "WELLS",
}

STATUS_GROUPS = {
    "active": {"ACTIVE", "ACTIVE WELL", "ACITVE WELL"},
    "abandoned": {
        "ABANDONED",
        "ABANDONED, KNOWN LOCATION AND VERIFIED",
        "ABANDONED, UNKNOWN LOCATION",
        "ABANDONED, NO EVIDENCE OF EXISTENCE/ UNABLE TO FIND",
        "TEMPORARILY ABANDONED(IDLE)",
    },
    "plugged": {"PLUGGED - APPROVED"},
    "shut in": {"SHUT IN", "SHUT-IN"},
    "under construction": {"UNDER CONSTRUCTION"},
    "incomplete": {"INCOMPLETE"},
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


def permit_tokens(value: str) -> set[str]:
    return {token for token in normalize_text(value).split() if token not in GENERIC_PERMIT_TOKENS}


def rows_updated_label(value: Any) -> str | None:
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).replace(microsecond=0).isoformat()


def permit_pdf_url(row: dict[str, Any]) -> str:
    apiwebaddress = row.get("apiwebaddress")
    if isinstance(apiwebaddress, dict):
        return clean_text(apiwebaddress.get("url"))
    return clean_text(apiwebaddress)


def location_value(row: dict[str, Any], key: str) -> str:
    location = row.get("location_1")
    if isinstance(location, dict):
        return clean_text(location.get(key))
    return ""


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    permit_id = clean_text(row.get("id")).upper()
    company = clean_text(row.get("coname")).upper()
    lease_name = clean_text(row.get("leasename")).upper()
    county = clean_text(row.get("county"))
    status = clean_text(row.get("status"))
    return {
        "permit_id": permit_id,
        "county": county,
        "county_norm": normalize_text(county),
        "ogc_number": clean_text(row.get("ogcnumber")),
        "company_name": company,
        "company_norm": normalize_text(company),
        "lease_name": lease_name,
        "lease_norm": normalize_text(lease_name),
        "well_no": clean_text(row.get("wellno")),
        "status": status,
        "status_norm": normalize_text(status),
        "township": clean_text(row.get("township")),
        "range": clean_text(row.get("range")),
        "range_dir": clean_text(row.get("rangedir")),
        "section": clean_text(row.get("section")),
        "latitude": location_value(row, "latitude"),
        "longitude": location_value(row, "longitude"),
        "permit_pdf_url": permit_pdf_url(row),
        "source_url": DATA_URL,
        "landing_page": LANDING_PAGE,
    }


def top_counts(counter: Counter[str], limit: int = 12) -> list[dict[str, Any]]:
    return [
        {"label": label, "count": count}
        for label, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:limit]
        if label
    ]


def status_group(status: str) -> str:
    normalized = normalize_text(status)
    for label, statuses in STATUS_GROUPS.items():
        if normalized in {normalize_text(item) for item in statuses}:
            return label
    return status.lower() or "unknown"


def build_data_mo_dnr_oil_gas_index(force: bool = False) -> dict[str, Any]:
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
        key=lambda item: (item["county_norm"], item["company_norm"], item["permit_id"]),
    )
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    write_json(RAW_DIR / "oil_and_gas_permits.json", raw_rows)
    county_counts = Counter(record["county"] for record in records if record["county"])
    company_counts = Counter(record["company_name"] for record in records if record["company_name"])
    status_counts = Counter(record["status"] for record in records if record["status"])
    status_group_counts = Counter(status_group(record["status"]) for record in records if record["status"])
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
        "company_count": len(company_counts),
        "status_counts": dict(sorted(status_counts.items())),
        "status_group_counts": dict(sorted(status_group_counts.items())),
        "columns": [column.get("name") for column in metadata.get("columns", []) if column.get("name")],
        "top_counties": top_counts(county_counts),
        "top_companies": top_counts(company_counts),
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
            "company_count": payload["company_count"],
            "status_group_counts": payload["status_group_counts"],
            "top_counties": payload["top_counties"],
            "top_companies": payload["top_companies"],
        },
    )
    return payload


def asks_for_count(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["how many", "count", "number of", "total"])


def asks_for_top(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["top", "highest", "largest", "most"])


def permit_id_in_question(question: str) -> str | None:
    match = re.search(r"\b\d{3}-\d{5}\b", question.upper())
    return match.group(0) if match else None


def status_group_in_question(question: str) -> str | None:
    lowered = question.lower()
    if "active" in lowered:
        return "active"
    if "abandoned" in lowered:
        return "abandoned"
    if "plugged" in lowered:
        return "plugged"
    if "shut in" in lowered or "shut-in" in lowered:
        return "shut in"
    if "under construction" in lowered:
        return "under construction"
    if "incomplete" in lowered:
        return "incomplete"
    return None


class DataMoDnrOilGasIndex:
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
                "category": "oil_and_gas_permits",
                "category_label": payload.get("source", DATASET_NAME),
                "file_name": payload.get("source_url", DATA_URL),
                "source_url": payload.get("source_url", DATA_URL),
                "row_count": payload.get("record_count"),
                "bytes": payload.get("bytes"),
                "sha256": payload.get("sha256"),
            },
            {
                "category": "oil_and_gas_permits",
                "category_label": "data.mo.gov landing page",
                "file_name": payload.get("landing_page", LANDING_PAGE),
                "source_url": payload.get("landing_page", LANDING_PAGE),
                "row_count": None,
                "bytes": None,
                "sha256": None,
            },
        ]
        if record and record.get("permit_pdf_url"):
            source_files.insert(
                0,
                {
                    "category": "oil_and_gas_permit_pdf",
                    "category_label": "DNR permit PDF",
                    "file_name": record["permit_pdf_url"],
                    "source_url": record["permit_pdf_url"],
                    "row_count": 1,
                    "bytes": None,
                    "sha256": None,
                },
            )
        return [
            {
                "dataset": payload.get("source", DATASET_NAME),
                "category": "DNR oil and gas permits",
                "kind": "oil and gas permit row",
                "lookup_table": "data_mo_dnr_oil_gas_index",
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
                "The selected data.mo.gov DNR oil and gas permit index has not been built yet. Run "
                "`python scripts/build_data_mo_dnr_oil_gas_index.py --force` to download the public permit table and build exact lookups."
            ),
            "retrieved_context_id": "data_mo_dnr_oil_gas_index:missing",
            "retrieved_source": "data_mo_dnr_oil_gas_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "The DNR oil and gas permit route exists, but the local ignored index is missing.",
            "citations": [],
            "source_rows": [],
        }

    def source_rows(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows = []
        for record in records[:5]:
            rows.append(
                {
                    "source_file": DATA_URL,
                    "source_row_number": record.get("permit_id"),
                    "values": {
                        "Permit ID": record.get("permit_id"),
                        "County": record.get("county"),
                        "Company": record.get("company_name"),
                        "Lease": record.get("lease_name"),
                        "Well": record.get("well_no"),
                        "Status": record.get("status"),
                        "Township": record.get("township"),
                        "Range": " ".join(
                            part for part in [record.get("range"), record.get("range_dir")] if part
                        ),
                        "Section": record.get("section"),
                        "Permit PDF": record.get("permit_pdf_url"),
                    },
                }
            )
        return rows

    def summary_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        top_counties = "; ".join(f"{item['label']}: {item['count']}" for item in payload.get("top_counties", [])[:5])
        top_companies = "; ".join(f"{item['label']}: {item['count']}" for item in payload.get("top_companies", [])[:3])
        statuses = payload.get("status_group_counts", {})
        status_summary = "; ".join(f"{label}: {count}" for label, count in sorted(statuses.items(), key=lambda item: (-item[1], item[0]))[:6])
        return {
            "question": question,
            "answer": (
                f"The selected DNR oil-and-gas exact lookup layer indexes the data.mo.gov {payload.get('source', DATASET_NAME)} table. "
                f"It contains {payload.get('record_count', 0):,} public permit rows across {payload.get('county_count', 0):,} counties "
                f"and {payload.get('company_count', 0):,} company/operator names. Rows updated at: {payload.get('rows_updated_at_utc')}. "
                f"It can answer permit-ID lookups, county counts, status counts, county rankings, company/operator rankings, and permit-PDF links. "
                f"Top counties: {top_counties}. Top company/operators: {top_companies}. Status groups: {status_summary}."
            ),
            "retrieved_context_id": "data_mo_dnr_oil_gas_index:summary",
            "retrieved_source": "data_mo_dnr_oil_gas_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local data.mo.gov DNR oil and gas permit index.",
            "citations": self.citation(),
            "source_rows": [],
        }

    def county_from_question(self, question: str) -> str | None:
        normalized_question = normalize_text(question)
        for county in sorted({record["county"] for record in self.records() if record.get("county")}, key=len, reverse=True):
            if re.search(rf"\b{re.escape(normalize_text(county))}\b", normalized_question):
                return county
        return None

    def matching_company_records(self, question: str) -> list[dict[str, Any]]:
        question_tokens = permit_tokens(question)
        if not question_tokens:
            return []
        scored: list[tuple[float, str, dict[str, Any]]] = []
        for record in self.records():
            tokens = permit_tokens(record.get("company_name", ""))
            if not tokens:
                continue
            overlap = len(question_tokens & tokens)
            if overlap >= min(2, len(tokens)):
                scored.append((overlap / len(tokens), record.get("company_name", ""), record))
        if not scored:
            return []
        scored.sort(key=lambda item: (-item[0], item[1], item[2].get("permit_id", "")))
        best_company = scored[0][1]
        return [record for _, company, record in scored if company == best_company]

    def answer(self, question: str) -> dict[str, Any] | None:
        if not self.available():
            return self.unavailable_answer(question)

        payload = self.payload()
        records = self.records()
        permit_id = permit_id_in_question(question)
        if permit_id:
            matches = [record for record in records if record.get("permit_id") == permit_id]
            if not matches:
                return {
                    "question": question,
                    "answer": f"I could not find DNR oil and gas permit {permit_id} in the indexed data.mo.gov permit table.",
                    "retrieved_context_id": f"data_mo_dnr_oil_gas_index:permit:{permit_id}:missing",
                    "retrieved_source": "data_mo_dnr_oil_gas_lookup_index",
                    "retrieval_score": 1.0,
                    "used_model": False,
                    "model": "deterministic_public_lookup",
                    "source_note": "Computed from the local data.mo.gov DNR oil and gas permit index.",
                    "citations": self.citation(matched_rows=0),
                    "source_rows": [],
                }
            record = matches[0]
            range_label = " ".join(part for part in [record.get("range"), record.get("range_dir")] if part)
            location = ", ".join(part for part in [record.get("township"), range_label, record.get("section")] if part)
            return {
                "question": question,
                "answer": (
                    f"DNR oil and gas permit {record['permit_id']} is listed in {record['county']} County for "
                    f"{record['company_name']} on lease {record['lease_name']} well {record['well_no']}. "
                    f"Status: {record['status']}. Township/range/section: {location}. "
                    f"Permit PDF: {record.get('permit_pdf_url') or 'not listed'}."
                ),
                "retrieved_context_id": f"data_mo_dnr_oil_gas_index:permit:{permit_id}",
                "retrieved_source": "data_mo_dnr_oil_gas_lookup_index",
                "retrieval_score": 1.0,
                "used_model": False,
                "model": "deterministic_public_lookup",
                "source_note": "Computed from the local data.mo.gov DNR oil and gas permit index.",
                "citations": self.citation(matched_rows=1, record=record),
                "source_rows": self.source_rows([record]),
            }

        county = self.county_from_question(question)
        status = status_group_in_question(question)
        if asks_for_count(question) and (county or status):
            matches = records
            detail_parts = []
            if county:
                matches = [record for record in matches if record.get("county") == county]
                detail_parts.append(f"in {county} County")
            if status:
                matches = [record for record in matches if status_group(record.get("status", "")) == status]
                detail_parts.append(f"with {status} status")
            detail = " ".join(detail_parts) or "in the index"
            return {
                "question": question,
                "answer": (
                    f"The indexed data.mo.gov DNR oil and gas permit table lists {len(matches):,} permit row(s) {detail}."
                ),
                "retrieved_context_id": f"data_mo_dnr_oil_gas_index:count:{county or 'all'}:{status or 'all'}",
                "retrieved_source": "data_mo_dnr_oil_gas_lookup_index",
                "retrieval_score": 1.0,
                "used_model": False,
                "model": "deterministic_public_lookup",
                "source_note": "Computed from the local data.mo.gov DNR oil and gas permit index.",
                "citations": self.citation(matched_rows=len(matches)),
                "source_rows": self.source_rows(matches),
            }

        lowered = question.lower()
        if asks_for_top(question):
            if "company" in lowered or "operator" in lowered or "permittee" in lowered:
                top = payload.get("top_companies", [])[:5]
                rendered = "; ".join(f"{item['label']}: {item['count']}" for item in top)
                return {
                    "question": question,
                    "answer": f"Top indexed DNR oil and gas company/operator names by permit rows: {rendered}.",
                    "retrieved_context_id": "data_mo_dnr_oil_gas_index:top_companies",
                    "retrieved_source": "data_mo_dnr_oil_gas_lookup_index",
                    "retrieval_score": 1.0,
                    "used_model": False,
                    "model": "deterministic_public_lookup",
                    "source_note": "Computed from the local data.mo.gov DNR oil and gas permit index.",
                    "citations": self.citation(),
                    "source_rows": [],
                }
            top = payload.get("top_counties", [])[:8]
            rendered = "; ".join(f"{item['label']}: {item['count']}" for item in top)
            return {
                "question": question,
                "answer": f"Top indexed counties by DNR oil and gas permit rows: {rendered}.",
                "retrieved_context_id": "data_mo_dnr_oil_gas_index:top_counties",
                "retrieved_source": "data_mo_dnr_oil_gas_lookup_index",
                "retrieval_score": 1.0,
                "used_model": False,
                "model": "deterministic_public_lookup",
                "source_note": "Computed from the local data.mo.gov DNR oil and gas permit index.",
                "citations": self.citation(),
                "source_rows": [],
            }

        company_records = self.matching_company_records(question)
        if company_records and ("company" in lowered or "operator" in lowered or "permit" in lowered):
            company = company_records[0]["company_name"]
            county_counts = Counter(record["county"] for record in company_records if record.get("county"))
            top_counties = "; ".join(f"{label}: {count}" for label, count in county_counts.most_common(5))
            return {
                "question": question,
                "answer": (
                    f"The indexed DNR oil and gas permit table lists {len(company_records):,} permit row(s) for "
                    f"{company}. Top counties for this company/operator: {top_counties}."
                ),
                "retrieved_context_id": f"data_mo_dnr_oil_gas_index:company:{normalize_text(company)}",
                "retrieved_source": "data_mo_dnr_oil_gas_lookup_index",
                "retrieval_score": 1.0,
                "used_model": False,
                "model": "deterministic_public_lookup",
                "source_note": "Computed from the local data.mo.gov DNR oil and gas permit index.",
                "citations": self.citation(matched_rows=len(company_records)),
                "source_rows": self.source_rows(company_records),
            }

        return self.summary_answer(question)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build selected data.mo.gov DNR oil and gas permit lookup index.")
    parser.add_argument("--force", action="store_true", help="Rebuild even when the local index already exists.")
    args = parser.parse_args()
    payload = build_data_mo_dnr_oil_gas_index(force=args.force)
    print(
        json.dumps(
            {
                "index_path": payload["index_path"],
                "records": payload["record_count"],
                "counties": payload["county_count"],
                "companies": payload["company_count"],
                "rows_updated_at_utc": payload["rows_updated_at_utc"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
