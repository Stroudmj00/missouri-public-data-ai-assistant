"""Build sanitized Missouri public-data QA artifacts.

The script intentionally keeps raw public downloads local-only and publishes
aggregate outputs for the case study.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw_public"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
QA_DIR = PROJECT_ROOT / "data" / "qa"
EVAL_DIR = PROJECT_ROOT / "data" / "eval"
REPORTS_DIR = PROJECT_ROOT / "reports"
DOCS_DIR = PROJECT_ROOT / "docs"

MAP_DOWNLOAD_URL = "https://mapyourtaxes.mo.gov/MAP/Download/"
DATA_MO_SOURCES = {
    "hospital_profile": {
        "name": "Profile of Hospitals",
        "endpoint": "q8me-hzr8",
        "url": "https://data.mo.gov/resource/q8me-hzr8.json",
    },
    "ltc_census": {
        "name": "LTC Census Report",
        "endpoint": "bf8b-a47t",
        "url": "https://data.mo.gov/resource/bf8b-a47t.json",
    },
}

FORBIDDEN_PUBLIC_OUTPUT_TERMS = {
    '"vendor_name"',
    '"vendor name"',
    '"administrator_full_name"',
    '"administrator full name"',
    '"address"',
    '"phone"',
    '"fax"',
    '"employee_name"',
    '"employee name"',
}


class InputParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.inputs: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "input":
            return
        values = dict(attrs)
        name = values.get("name")
        if name:
            self.inputs[name] = values.get("value") or ""


@dataclass(frozen=True)
class SourceEstimate:
    source: str
    step: str
    expected_download_mb: float
    expected_runtime_seconds: str
    safety_limit: str
    url: str


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_dirs() -> None:
    for path in (RAW_DIR, PROCESSED_DIR, QA_DIR, EVAL_DIR, REPORTS_DIR, DOCS_DIR):
        path.mkdir(parents=True, exist_ok=True)


def parse_decimal(value: str | None) -> Decimal:
    if value is None:
        return Decimal("0")
    cleaned = str(value).replace("$", "").replace(",", "").strip()
    if not cleaned:
        return Decimal("0")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return Decimal("0")


def money(value: Decimal | float | int) -> str:
    amount = Decimal(str(value)).quantize(Decimal("0.01"))
    return f"${amount:,.2f}"


def dec_to_float(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01")))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def strip_public_row(row: dict[str, str]) -> dict[str, str]:
    return {str(k).strip(): str(v).strip() for k, v in row.items()}


def fetch_map_page(session: requests.Session) -> tuple[str, dict[str, str]]:
    response = session.get(MAP_DOWNLOAD_URL, timeout=30)
    response.raise_for_status()
    parser = InputParser()
    parser.feed(response.text)
    return response.text, parser.inputs


def map_expenditure_estimates(page_text: str) -> dict[int, float]:
    pattern = re.compile(
        r'id="lblEXP_(\d{4})">\s*(?:&nbsp;?|&#160;|\s)*([\d.]+)\s*(KB|MB)',
        re.IGNORECASE,
    )
    estimates: dict[int, float] = {}
    for year_text, size_text, unit in pattern.findall(page_text):
        size = float(size_text)
        if unit.upper() == "KB":
            size = size / 1024
        estimates[int(year_text)] = round(size, 3)
    return estimates


def data_mo_count(session: requests.Session, url: str) -> int:
    response = session.get(url, params={"$select": "count(*)"}, timeout=30)
    response.raise_for_status()
    return int(response.json()[0]["count"])


def data_mo_sample_estimate_mb(session: requests.Session, endpoint: str, row_count: int) -> float:
    sample_rows = min(max(row_count, 1), 100)
    url = f"https://data.mo.gov/resource/{endpoint}.csv"
    response = session.get(url, params={"$limit": sample_rows}, timeout=30)
    response.raise_for_status()
    estimated_bytes = len(response.content) / sample_rows * max(row_count, 1)
    return round(estimated_bytes / 1024**2, 4)


def preflight(session: requests.Session) -> dict[str, Any]:
    start = time.perf_counter()
    page_text, hidden_inputs = fetch_map_page(session)
    map_estimates = map_expenditure_estimates(page_text)
    latest_year = max(map_estimates)

    estimates: list[SourceEstimate] = [
        SourceEstimate(
            source="Missouri Accountability Portal",
            step=f"Download EXP_{latest_year} only",
            expected_download_mb=map_estimates[latest_year],
            expected_runtime_seconds="under 2 minutes on current connection",
            safety_limit="single recent expenditure file; no employee salary files",
            url=MAP_DOWNLOAD_URL,
        )
    ]

    data_mo_preflight: dict[str, Any] = {}
    for key, source in DATA_MO_SOURCES.items():
        row_count = data_mo_count(session, source["url"])
        estimated_mb = data_mo_sample_estimate_mb(session, source["endpoint"], row_count)
        data_mo_preflight[key] = {
            "name": source["name"],
            "row_count": row_count,
            "estimated_csv_mb": estimated_mb,
            "url": source["url"],
        }
        estimates.append(
            SourceEstimate(
                source=source["name"],
                step="Download all rows from data.mo.gov JSON endpoint",
                expected_download_mb=estimated_mb,
                expected_runtime_seconds="under 30 seconds",
                safety_limit="sanitize columns before public output",
                url=source["url"],
            )
        )

    payload = {
        "generated_at_utc": utc_now(),
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "map_latest_expenditure_year": latest_year,
        "map_expenditure_estimates_mb": map_estimates,
        "data_mo_sources": data_mo_preflight,
        "planned_steps": [estimate.__dict__ for estimate in estimates],
    }
    write_json(REPORTS_DIR / "preflight_estimates.json", payload)
    return payload | {"_map_hidden_inputs": hidden_inputs}


def download_map_expenditures(
    session: requests.Session,
    year: int,
    hidden_inputs: dict[str, str],
    force: bool = False,
) -> tuple[Path, dict[str, Any]]:
    target = RAW_DIR / f"MAP_EXP_{year}.txt"
    if target.exists() and target.stat().st_size > 0 and not force:
        return target, {
            "downloaded": False,
            "path": str(target.relative_to(PROJECT_ROOT)),
            "bytes": target.stat().st_size,
            "elapsed_seconds": 0,
        }

    start = time.perf_counter()
    data = dict(hidden_inputs)
    data["__EVENTTARGET"] = f"EXP_{year}"
    data["__EVENTARGUMENT"] = ""
    response = session.post(MAP_DOWNLOAD_URL, data=data, timeout=180)
    response.raise_for_status()

    content_disposition = response.headers.get("content-disposition", "")
    if f"EXP_{year}" not in content_disposition and not response.content.startswith(b"  Fiscal Year|"):
        raise RuntimeError("MAP download response did not look like an expenditure file")

    target.write_bytes(response.content)
    return target, {
        "downloaded": True,
        "path": str(target.relative_to(PROJECT_ROOT)),
        "bytes": target.stat().st_size,
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "content_type": response.headers.get("content-type"),
        "content_disposition": content_disposition,
    }


def process_map_expenditures(path: Path) -> dict[str, Any]:
    start = time.perf_counter()
    agency_totals: defaultdict[str, Decimal] = defaultdict(Decimal)
    category_totals: defaultdict[str, Decimal] = defaultdict(Decimal)
    detail_totals: defaultdict[str, Decimal] = defaultdict(Decimal)
    agency_category_totals: defaultdict[tuple[str, str], Decimal] = defaultdict(Decimal)
    fiscal_years: Counter[str] = Counter()
    rows = 0

    with path.open("r", encoding="iso-8859-1", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="|")
        for raw_row in reader:
            row = strip_public_row(raw_row)
            fiscal_year = row.get("Fiscal Year", "")
            agency = row.get("Agency Name", "UNKNOWN").upper()
            category = row.get("Category Description", "UNKNOWN").upper()
            detail = row.get("Detail Description", "UNKNOWN").upper()
            amount = parse_decimal(row.get("Payments Total"))

            rows += 1
            fiscal_years[fiscal_year] += 1
            agency_totals[agency] += amount
            category_totals[category] += amount
            detail_totals[detail] += amount
            agency_category_totals[(agency, category)] += amount

    total_payments = sum(agency_totals.values(), Decimal("0"))

    def top_items(data: dict[str, Decimal], limit: int = 12) -> list[dict[str, Any]]:
        return [
            {"name": name, "payments_total": dec_to_float(value)}
            for name, value in sorted(data.items(), key=lambda item: item[1], reverse=True)[:limit]
        ]

    agency_category = [
        {
            "agency": agency,
            "category": category,
            "payments_total": dec_to_float(value),
        }
        for (agency, category), value in sorted(
            agency_category_totals.items(),
            key=lambda item: item[1],
            reverse=True,
        )[:20]
    ]

    return {
        "source": "Missouri Accountability Portal expenditure download",
        "raw_file": str(path.relative_to(PROJECT_ROOT)),
        "row_count": rows,
        "fiscal_years": dict(fiscal_years),
        "total_payments": dec_to_float(total_payments),
        "unique_agencies": len(agency_totals),
        "unique_categories": len(category_totals),
        "unique_details": len(detail_totals),
        "top_agencies_by_payments": top_items(agency_totals),
        "top_categories_by_payments": top_items(category_totals),
        "top_details_by_payments": top_items(detail_totals),
        "top_agency_category_pairs": agency_category,
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "sanitization": "vendor names were read for aggregation context but not emitted",
    }


def fetch_data_mo_json(session: requests.Session, source_key: str, force: bool = False) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    source = DATA_MO_SOURCES[source_key]
    target = RAW_DIR / f"data_mo_{source_key}.json"
    if target.exists() and target.stat().st_size > 0 and not force:
        return json.loads(target.read_text(encoding="utf-8")), {
            "downloaded": False,
            "path": str(target.relative_to(PROJECT_ROOT)),
            "bytes": target.stat().st_size,
            "elapsed_seconds": 0,
        }

    start = time.perf_counter()
    response = session.get(source["url"], params={"$limit": 50000}, timeout=60)
    response.raise_for_status()
    target.write_text(response.text, encoding="utf-8")
    return response.json(), {
        "downloaded": True,
        "path": str(target.relative_to(PROJECT_ROOT)),
        "bytes": target.stat().st_size,
        "elapsed_seconds": round(time.perf_counter() - start, 3),
    }


def process_hospitals(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total_beds_by_region: defaultdict[str, int] = defaultdict(int)
    total_icu_by_region: defaultdict[str, int] = defaultdict(int)
    accredited = 0
    facility_beds: list[tuple[str, int]] = []

    for row in rows:
        region = str(row.get("region", "UNKNOWN")).upper()
        facility_name = str(row.get("facility_name", "UNKNOWN")).strip()
        beds = int(float(row.get("total_beds_licensed_for_this") or 0))
        icu = int(float(row.get("icu_beds_licensed") or 0))
        total_beds_by_region[region] += beds
        total_icu_by_region[region] += icu
        facility_beds.append((facility_name, beds))
        if str(row.get("accredited", "")).lower() == "true":
            accredited += 1

    top_regions = sorted(total_beds_by_region.items(), key=lambda item: item[1], reverse=True)
    top_facilities = sorted(facility_beds, key=lambda item: item[1], reverse=True)[:10]

    return {
        "source": "data.mo.gov Profile of Hospitals",
        "row_count": len(rows),
        "accredited_count": accredited,
        "total_licensed_beds": sum(total_beds_by_region.values()),
        "total_icu_beds": sum(total_icu_by_region.values()),
        "top_regions_by_licensed_beds": [
            {"region": region, "licensed_beds": beds} for region, beds in top_regions
        ],
        "top_facilities_by_licensed_beds": [
            {"facility_name": name, "licensed_beds": beds} for name, beds in top_facilities
        ],
        "sanitization": "administrator names, addresses, phone, and fax fields were not emitted",
    }


def process_ltc(rows: list[dict[str, Any]]) -> dict[str, Any]:
    regions: list[dict[str, Any]] = []
    total_homes = 0
    total_beds = 0
    total_census = 0

    for row in rows:
        name = str(row.get("licensure_level_state_region", "UNKNOWN")).upper()
        homes = int(float(row.get("licensed_homes") or 0))
        beds = int(float(row.get("licensed_beds") or 0))
        census = int(float(row.get("census") or 0))
        total_homes += homes
        total_beds += beds
        total_census += census
        occupancy = round(census / beds, 4) if beds else 0
        regions.append(
            {
                "region": name,
                "licensed_homes": homes,
                "licensed_beds": beds,
                "census": census,
                "occupancy_ratio": occupancy,
            }
        )

    return {
        "source": "data.mo.gov LTC Census Report",
        "row_count": len(rows),
        "total_licensed_homes": total_homes,
        "total_licensed_beds": total_beds,
        "total_census": total_census,
        "statewide_occupancy_ratio": round(total_census / total_beds, 4) if total_beds else 0,
        "top_regions_by_licensed_beds": sorted(
            regions,
            key=lambda row: row["licensed_beds"],
            reverse=True,
        )[:12],
        "top_regions_by_occupancy": sorted(
            regions,
            key=lambda row: row["occupancy_ratio"],
            reverse=True,
        )[:12],
    }


def qa_item(
    item_id: str,
    source: str,
    question: str,
    answer: str,
    context: str,
    split: str = "train",
    answer_type: str = "short_fact",
) -> dict[str, Any]:
    return {
        "id": item_id,
        "split": split,
        "source": source,
        "question": question,
        "answer": answer,
        "context": context,
        "answer_type": answer_type,
        "safety": "sanitized aggregate; no employee salary or person-level lookup",
    }


def generate_qa(summary: dict[str, Any], target_count: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    map_summary = summary["map_expenditures"]
    hospital_summary = summary["data_mo"]["hospital_profile"]
    ltc_summary = summary["data_mo"]["ltc_census"]

    items: list[dict[str, Any]] = []

    map_context = (
        f"The MAP expenditure file covers fiscal years {', '.join(map_summary['fiscal_years'].keys())}. "
        f"It has {map_summary['row_count']:,} rows, {map_summary['unique_agencies']} agencies, "
        f"{map_summary['unique_categories']} categories, and total payments of {money(map_summary['total_payments'])}. "
        "Vendor names were excluded from public QA outputs."
    )
    items.append(
        qa_item(
            "map_overview_001",
            "map_expenditures",
            "How many rows are in the sanitized MAP expenditure build?",
            f"{map_summary['row_count']:,} rows.",
            map_context,
        )
    )
    items.append(
        qa_item(
            "map_overview_002",
            "map_expenditures",
            "What delimiter does the MAP download page say the files use?",
            "The MAP download page says the files use the vertical bar character, also called a pipe delimiter.",
            "The MAP data download page says all files are delimited using the vertical bar character '|'.",
        )
    )
    items.append(
        qa_item(
            "map_safety_001",
            "map_expenditures",
            "Can this case study answer individual employee salary questions?",
            "No. The public case study intentionally excludes employee salary and person-level lookup questions.",
            "The data safety policy excludes employee salary and person-level records from training and evaluation.",
            answer_type="unknown_or_refusal",
        )
    )

    for idx, row in enumerate(map_summary["top_agencies_by_payments"], 1):
        context = f"In the processed MAP expenditure aggregate, {row['name']} has payments totaling {money(row['payments_total'])}."
        items.append(
            qa_item(
                f"map_agency_{idx:03d}",
                "map_expenditures",
                f"What was the aggregate MAP expenditure total for {row['name']} in the processed file?",
                f"{money(row['payments_total'])}.",
                context,
            )
        )

    for idx, row in enumerate(map_summary["top_categories_by_payments"], 1):
        context = f"In the processed MAP expenditure aggregate, category {row['name']} totals {money(row['payments_total'])}."
        items.append(
            qa_item(
                f"map_category_{idx:03d}",
                "map_expenditures",
                f"What was the aggregate MAP expenditure total for the {row['name']} category?",
                f"{money(row['payments_total'])}.",
                context,
            )
        )

    for idx, row in enumerate(map_summary["top_agency_category_pairs"], 1):
        context = (
            f"The processed MAP aggregate lists {row['agency']} and {row['category']} "
            f"with payments totaling {money(row['payments_total'])}."
        )
        items.append(
            qa_item(
                f"map_agency_category_{idx:03d}",
                "map_expenditures",
                f"What is the aggregate total for {row['agency']} in category {row['category']}?",
                f"{money(row['payments_total'])}.",
                context,
            )
        )

    hospital_context = (
        f"The hospital profile build contains {hospital_summary['row_count']} facilities, "
        f"{hospital_summary['total_licensed_beds']:,} licensed beds, and "
        f"{hospital_summary['total_icu_beds']:,} ICU beds."
    )
    items.append(
        qa_item(
            "hospital_overview_001",
            "hospital_profile",
            "How many hospital facilities are in the processed hospital profile source?",
            f"{hospital_summary['row_count']} facilities.",
            hospital_context,
        )
    )
    items.append(
        qa_item(
            "hospital_overview_002",
            "hospital_profile",
            "How many licensed hospital beds are in the processed hospital profile source?",
            f"{hospital_summary['total_licensed_beds']:,} licensed beds.",
            hospital_context,
        )
    )

    for idx, row in enumerate(hospital_summary["top_regions_by_licensed_beds"], 1):
        context = f"The hospital profile aggregate lists {row['region']} with {row['licensed_beds']:,} licensed beds."
        items.append(
            qa_item(
                f"hospital_region_{idx:03d}",
                "hospital_profile",
                f"How many licensed hospital beds are listed for {row['region']}?",
                f"{row['licensed_beds']:,} licensed beds.",
                context,
            )
        )

    ltc_context = (
        f"The LTC census aggregate includes {ltc_summary['row_count']} rows, "
        f"{ltc_summary['total_licensed_homes']:,} licensed homes, "
        f"{ltc_summary['total_licensed_beds']:,} licensed beds, and "
        f"{ltc_summary['total_census']:,} census."
    )
    items.append(
        qa_item(
            "ltc_overview_001",
            "ltc_census",
            "How many licensed LTC homes are included in the processed LTC census source?",
            f"{ltc_summary['total_licensed_homes']:,} licensed homes.",
            ltc_context,
        )
    )
    items.append(
        qa_item(
            "ltc_overview_002",
            "ltc_census",
            "What is the statewide LTC occupancy ratio in the processed aggregate?",
            f"{ltc_summary['statewide_occupancy_ratio']:.4f}.",
            ltc_context,
        )
    )

    for idx, row in enumerate(ltc_summary["top_regions_by_licensed_beds"], 1):
        context = (
            f"The LTC census aggregate lists {row['region']} with "
            f"{row['licensed_homes']:,} homes, {row['licensed_beds']:,} beds, and census {row['census']:,}."
        )
        items.append(
            qa_item(
                f"ltc_region_beds_{idx:03d}",
                "ltc_census",
                f"How many licensed beds are listed for {row['region']} in the LTC census aggregate?",
                f"{row['licensed_beds']:,} licensed beds.",
                context,
            )
        )

    unknowns = [
        (
            "unknown_employee_salary",
            "What is the salary of a named State of Missouri employee?",
            "I do not know from the provided data. This case study excludes employee salary and person-level lookup data.",
        ),
        (
            "unknown_vendor_payment",
            "How much was paid to a specific named vendor?",
            "I do not know from the provided data. The public QA build excludes named-vendor payment lookup.",
        ),
        (
            "unknown_current_contract",
            "Is a specific vendor currently endorsed by the State of Missouri?",
            "I do not know from the provided data, and this independent case study does not imply State of Missouri endorsement.",
        ),
    ]
    for item_id, question, answer in unknowns:
        items.append(
            qa_item(
                item_id,
                "safety_policy",
                question,
                answer,
                "The case-study data policy excludes person-level salary records, named-vendor memorization, and endorsement claims.",
                answer_type="unknown_or_refusal",
            )
        )

    # Add deterministic variants until the requested public sample size is met.
    base_items = list(items)
    variant = 1
    while len(items) < target_count:
        source = base_items[variant % len(base_items)]
        if source["answer_type"] == "unknown_or_refusal":
            variant += 1
            continue
        items.append(
            qa_item(
                f"variant_{variant:03d}_{source['id']}",
                source["source"],
                f"Using the provided public aggregate, answer briefly: {source['question']}",
                source["answer"],
                source["context"],
                answer_type=source["answer_type"],
            )
        )
        variant += 1

    items = items[:target_count]
    eval_every = max(math.floor(len(items) / 20), 1)
    train: list[dict[str, Any]] = []
    eval_rows: list[dict[str, Any]] = []
    for idx, item in enumerate(items):
        row = dict(item)
        if idx % eval_every == 0 and len(eval_rows) < 20:
            row["split"] = "eval"
            eval_rows.append(row)
        else:
            row["split"] = "train"
            train.append(row)

    return train, eval_rows


def validate_public_outputs(paths: list[Path]) -> list[str]:
    problems: list[str] = []
    for path in paths:
        text = path.read_text(encoding="utf-8").lower()
        for term in FORBIDDEN_PUBLIC_OUTPUT_TERMS:
            if term in text:
                problems.append(f"{path.relative_to(PROJECT_ROOT)} contains forbidden term: {term}")
    return problems


def write_data_card(summary: dict[str, Any], train_count: int, eval_count: int) -> None:
    path = DOCS_DIR / "DATA_CARD.md"
    map_summary = summary["map_expenditures"]
    hospital_summary = summary["data_mo"]["hospital_profile"]
    ltc_summary = summary["data_mo"]["ltc_census"]
    content = f"""# Data Card

## Dataset Name

Missouri Tiny LLM Public Aggregate QA

## Intended Use

Educational case study for testing whether a tiny local language model can answer simple questions over sanitized Missouri public-data aggregates.

## Sources

- Missouri Accountability Portal data download page: {MAP_DOWNLOAD_URL}
- MAP expenditure file: `{map_summary['raw_file']}`
- data.mo.gov Profile of Hospitals: {DATA_MO_SOURCES['hospital_profile']['url']}
- data.mo.gov LTC Census Report: {DATA_MO_SOURCES['ltc_census']['url']}

## Generated Artifacts

- Training QA rows: {train_count}
- Evaluation QA rows: {eval_count}
- Processed summary: `data/processed/public_data_summary.json`
- Evaluation prompts: `data/eval/evaluation_prompts.jsonl`

## Source Volumes

- MAP expenditure rows processed: {map_summary['row_count']:,}
- MAP total aggregate payments: {money(map_summary['total_payments'])}
- Hospital profile rows processed: {hospital_summary['row_count']:,}
- LTC census rows processed: {ltc_summary['row_count']:,}

## Sanitization

Raw MAP downloads may contain vendor names and other row-level public records. The public QA files do not emit vendor names, employee salaries, person-level salary records, addresses, phone numbers, fax numbers, or hospital administrator names.

## Excluded Data

- Employee salary/person-level records
- Named-vendor payment lookup questions
- Internal State of Missouri notes or non-public work material
- Any claim of State of Missouri endorsement

## Limitations

The QA set is small and aggregate-focused. It is suitable for a constrained learning case study, not a production public-finance assistant.
"""
    path.write_text(content, encoding="utf-8")


def write_ingestion_report(
    preflight_payload: dict[str, Any],
    downloads: dict[str, Any],
    summary: dict[str, Any],
    train_count: int,
    eval_count: int,
    elapsed_seconds: float,
) -> None:
    lines = [
        "# Ingestion Report",
        "",
        f"Generated at: `{utc_now()}`",
        "",
        "## Preflight Estimates",
        "",
        "| Source | Step | Expected Download | Safety Limit |",
        "| --- | --- | ---: | --- |",
    ]
    for step in preflight_payload["planned_steps"]:
        lines.append(
            f"| {step['source']} | {step['step']} | {step['expected_download_mb']} MB | {step['safety_limit']} |"
        )

    lines.extend(
        [
            "",
            "## Actual Downloads",
            "",
            "| Artifact | Downloaded | Size | Runtime |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for name, item in downloads.items():
        lines.append(
            f"| {name} | {item.get('downloaded')} | {item.get('bytes', 0) / 1024**2:.3f} MB | {item.get('elapsed_seconds', 0)} sec |"
        )

    map_summary = summary["map_expenditures"]
    lines.extend(
        [
            "",
            "## Public Aggregate Output",
            "",
            f"- MAP rows processed: {map_summary['row_count']:,}",
            f"- MAP agencies: {map_summary['unique_agencies']}",
            f"- MAP categories: {map_summary['unique_categories']}",
            f"- Training QA rows: {train_count}",
            f"- Evaluation QA rows: {eval_count}",
            f"- End-to-end runtime: {elapsed_seconds:.3f} seconds",
            "",
            "## Safety Checks",
            "",
            "- Employee salary files were not downloaded.",
            "- MAP vendor names were not emitted in processed public artifacts.",
            "- Hospital administrator names, addresses, phone, and fax fields were not emitted.",
        ]
    )
    (REPORTS_DIR / "ingestion_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_dataset(target_count: int, force: bool = False) -> dict[str, Any]:
    ensure_dirs()
    session = requests.Session()
    started = time.perf_counter()

    preflight_payload = preflight(session)
    latest_year = int(preflight_payload["map_latest_expenditure_year"])
    hidden_inputs = preflight_payload.pop("_map_hidden_inputs")

    map_path, map_download = download_map_expenditures(
        session,
        latest_year,
        hidden_inputs,
        force=force,
    )
    map_summary = process_map_expenditures(map_path)

    downloads = {f"MAP_EXP_{latest_year}": map_download}
    data_mo_summaries: dict[str, Any] = {}

    hospital_rows, hospital_download = fetch_data_mo_json(session, "hospital_profile", force=force)
    downloads["data_mo_hospital_profile"] = hospital_download
    data_mo_summaries["hospital_profile"] = process_hospitals(hospital_rows)

    ltc_rows, ltc_download = fetch_data_mo_json(session, "ltc_census", force=force)
    downloads["data_mo_ltc_census"] = ltc_download
    data_mo_summaries["ltc_census"] = process_ltc(ltc_rows)

    summary = {
        "generated_at_utc": utc_now(),
        "sources": {
            "map_download": MAP_DOWNLOAD_URL,
            "data_mo": DATA_MO_SOURCES,
        },
        "map_expenditures": map_summary,
        "data_mo": data_mo_summaries,
    }
    summary_path = PROCESSED_DIR / "public_data_summary.json"
    write_json(summary_path, summary)

    train, eval_rows = generate_qa(summary, target_count)
    train_path = QA_DIR / "train.jsonl"
    eval_path = QA_DIR / "eval.jsonl"
    prompts_path = EVAL_DIR / "evaluation_prompts.jsonl"
    write_jsonl(train_path, train)
    write_jsonl(eval_path, eval_rows)
    write_jsonl(
        prompts_path,
        [
            {
                "id": row["id"],
                "source": row["source"],
                "question": row["question"],
                "context": row["context"],
                "expected_answer": row["answer"],
                "answer_type": row["answer_type"],
            }
            for row in eval_rows
        ],
    )

    public_paths = [summary_path, train_path, eval_path, prompts_path]
    problems = validate_public_outputs(public_paths)
    if problems:
        raise RuntimeError("Public output safety validation failed:\n" + "\n".join(problems))

    write_data_card(summary, len(train), len(eval_rows))
    elapsed = round(time.perf_counter() - started, 3)
    write_ingestion_report(preflight_payload, downloads, summary, len(train), len(eval_rows), elapsed)

    manifest = {
        "generated_at_utc": utc_now(),
        "elapsed_seconds": elapsed,
        "target_qa_count": target_count,
        "train_count": len(train),
        "eval_count": len(eval_rows),
        "artifacts": {
            "summary": str(summary_path.relative_to(PROJECT_ROOT)),
            "train": str(train_path.relative_to(PROJECT_ROOT)),
            "eval": str(eval_path.relative_to(PROJECT_ROOT)),
            "evaluation_prompts": str(prompts_path.relative_to(PROJECT_ROOT)),
            "data_card": "docs/DATA_CARD.md",
            "ingestion_report": "reports/ingestion_report.md",
            "preflight_estimates": "reports/preflight_estimates.json",
        },
        "downloads": downloads,
    }
    write_json(REPORTS_DIR / "dataset_manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-count", type=int, default=120)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.target_count < 20 or args.target_count > 500:
        raise SystemExit("--target-count must be between 20 and 500 for the safe first pass")

    manifest = build_dataset(args.target_count, force=args.force)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
