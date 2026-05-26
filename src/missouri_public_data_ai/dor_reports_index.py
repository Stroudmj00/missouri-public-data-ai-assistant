"""Build and query aggregate Missouri Department of Revenue public reports."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import requests
from pypdf import PdfReader


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw_public" / "dor_reports"
INDEX_PATH = RAW_DIR / "dor_reports_index.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "dor_reports_index_report.json"
DOR_PUBLIC_REPORTS_URL = "https://dor.mo.gov/public-reports/"


@dataclass(frozen=True)
class DorTextReportSpec:
    key: str
    label: str
    url: str
    estimated_kb: int

    @property
    def file_name(self) -> str:
        return self.url.rsplit("/", 1)[-1]


TEXT_REPORTS: tuple[DorTextReportSpec, ...] = (
    DorTextReportSpec(
        "business_locations",
        "Total business and locations open during 2016 by city and county",
        "https://dor.mo.gov/public-reports/bus_location_tots_report.txt",
        216,
    ),
    DorTextReportSpec(
        "vehicles_by_county",
        "Vehicles per county by kind of vehicle",
        "https://dor.mo.gov/public-reports/kov_cnty_file.txt",
        95,
    ),
    DorTextReportSpec(
        "drivers_by_age_county",
        "Total drivers by age per county",
        "https://dor.mo.gov/public-reports/drivers_age_cnty_report.txt",
        195,
    ),
    DorTextReportSpec(
        "dealers_by_county",
        "Dealer license records aggregated by county and dealer type",
        "https://dor.mo.gov/public-reports/DI52L06_dealers_file_cnty.txt",
        930,
    ),
    DorTextReportSpec(
        "sic_state",
        "Total business locations statewide by 4-digit SIC",
        "https://dor.mo.gov/public-reports/DT60871_SIC_statetots.txt",
        65,
    ),
    DorTextReportSpec(
        "sic_county",
        "Total business locations by 4-digit SIC by county",
        "https://dor.mo.gov/public-reports/DT60871_SIC_cntytots.txt",
        4140,
    ),
)

TAXABLE_SALES_COUNTY_ZIP_TEMPLATE = "https://dor.mo.gov/public-reports/zips/DI60IL02_TXB_CNTY_F_{year}.zip"
TAXABLE_SALES_YEARS = tuple(range(2016, 2026))

FOOD_TAX_REPORTS: tuple[DorTextReportSpec, ...] = (
    DorTextReportSpec(
        "food_tax_fy25",
        "FY25 Food Tax by Political Subdivision",
        "https://dor.mo.gov/public-reports/FY25-Combined-totals.pdf",
        135,
    ),
    DorTextReportSpec(
        "food_tax_fy24",
        "FY24 Food Tax by Political Subdivision",
        "https://dor.mo.gov/public-reports/FY24-Combined-totals.pdf",
        135,
    ),
    DorTextReportSpec(
        "food_tax_fy23",
        "FY23 Food Tax by Political Subdivision",
        "https://dor.mo.gov/public-reports/FY23-Combined-totals.pdf",
        135,
    ),
    DorTextReportSpec(
        "food_tax_fy22",
        "FY22 Food Tax by Political Subdivision",
        "https://dor.mo.gov/public-reports/FY22-Combined-totals.pdf",
        135,
    ),
)

WORKING_FAMILY_TAX_CREDIT_REPORTS: tuple[DorTextReportSpec, ...] = (
    DorTextReportSpec(
        "wftc_2025",
        "2025 Missouri Working Family Tax Credit Report",
        "https://dor.mo.gov/public-reports/documents/2025-MO-WFTC-Report.pdf",
        100,
    ),
    DorTextReportSpec(
        "wftc_2024",
        "2024 Missouri Working Family Tax Credit Report",
        "https://dor.mo.gov/public-reports/documents/2024-MO-WFTC-Report.pdf",
        100,
    ),
)

QUARTERLY_TAX_CREDIT_REPORTS: tuple[DorTextReportSpec, ...] = (
    DorTextReportSpec(
        "tax_credit_fy26_q3",
        "Third Quarter FY26 Tax Credit Report",
        "https://dor.mo.gov/public-reports/documents/FY26-thirdquarter-tax-credit-report.pdf",
        150,
    ),
    DorTextReportSpec(
        "tax_credit_fy26_q2",
        "Second Quarter FY26 Tax Credit Report",
        "https://dor.mo.gov/public-reports/documents/Second-Quarter-FY26-Tax-Credit-Report.pdf",
        168,
    ),
    DorTextReportSpec(
        "tax_credit_fy26_q1",
        "First Quarter FY26 Tax Credit Report",
        "https://dor.mo.gov/public-reports/documents/First-Quarter-FY26-Tax-Credit-Report.pdf",
        131,
    ),
    DorTextReportSpec(
        "tax_credit_fy25_q4",
        "Fourth Quarter FY25 Tax Credit Report",
        "https://dor.mo.gov/public-reports/documents/Fourth-Quarter-FY25-Tax-Credit-Report.pdf",
        155,
    ),
    DorTextReportSpec(
        "tax_credit_fy25_q3",
        "Third Quarter FY25 Tax Credit Report",
        "https://dor.mo.gov/public-reports/documents/Third-Quarter-FY25-Tax-Credit-Report.pdf",
        155,
    ),
    DorTextReportSpec(
        "tax_credit_fy25_q2",
        "Second Quarter FY25 Tax Credit Report",
        "https://dor.mo.gov/public-reports/documents/Second-Quarter-FY25-Tax-Credit-Report.pdf",
        156,
    ),
    DorTextReportSpec(
        "tax_credit_fy25_q1",
        "First Quarter FY25 Tax Credit Report",
        "https://dor.mo.gov/public-reports/documents/First-Quarter-FY25-Tax-Credit-Report.pdf",
        145,
    ),
)

VEHICLE_KIND_ALIASES = {
    "passenger": "PASSENGER",
    "car": "PASSENGER",
    "cars": "PASSENGER",
    "truck": "TRUCKS",
    "trucks": "TRUCKS",
    "trailer": "TRAILERS",
    "trailers": "TRAILERS",
    "bus": "BUSSES",
    "busses": "BUSSES",
    "boat": "MOTOR BOATS",
    "boats": "MOTOR BOATS",
    "motor boat": "MOTOR BOATS",
    "motor boats": "MOTOR BOATS",
    "motorcycle": "MOTORCYCLES",
    "motorcycles": "MOTORCYCLES",
    "rv": "RV 'S",
    "rvs": "RV 'S",
    "atv": "ATV",
    "all": "COUNTY TOTALS",
    "total": "COUNTY TOTALS",
    "totals": "COUNTY TOTALS",
    "vehicle": "COUNTY TOTALS",
    "vehicles": "COUNTY TOTALS",
}

REPORTING_AGENCY_CODES = {"DED", "DESE", "DNR", "DOH", "DOR", "DPS", "DSS", "MDA", "MDI", "STO"}
QUARTER_WORDS = {"first": 1, "second": 2, "third": 3, "fourth": 4}

DEALER_TYPE_ALIASES = {
    "auction": "AUCTION",
    "marine": "MARINE",
    "boat": "MARINE",
    "motor vehicle": "MOTOR V",
    "vehicle": "MOTOR V",
    "car": "MOTOR V",
    "auto": "MOTOR V",
    "dealer": "ALL",
    "dealers": "ALL",
    "salvage": "SALVAGE",
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


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def clean_int(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).replace(",", "").replace("$", "").replace("*", "").strip()
    if not text:
        return None
    try:
        return int(Decimal(text))
    except (InvalidOperation, ValueError):
        return None


def clean_decimal(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).replace(",", "").replace("$", "").strip()
    if not text:
        return None
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1].strip()
    try:
        amount = Decimal(text)
        return float(-amount if negative else amount)
    except (InvalidOperation, ValueError):
        return None


def normalize_key(value: str) -> str:
    normalized = value.lower().replace("&", " and ")
    normalized = normalized.replace("saint ", "st ")
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
    return re.sub(r"_+", "_", normalized)


def normalize_county(value: str) -> str:
    normalized = clean_text(value).upper().replace(".", "")
    normalized = re.sub(r"\s+COUNTY\b", "", normalized)
    normalized = normalized.replace("SAINT ", "ST ")
    return normalized.strip()


def display_county(value: str) -> str:
    label = clean_text(value).title()
    label = label.replace("Mcdonald", "McDonald").replace("Dekalb", "DeKalb")
    if label.startswith("St "):
        label = label.replace("St ", "St. ", 1)
    if not label:
        return "selected county"
    if "county" in label.lower() or "city" in label.lower():
        return label
    return f"{label} County"


def value_label(value: int | float) -> str:
    if isinstance(value, int):
        return f"{value:,}"
    return f"${value:,.2f}"


def plain_number_label(value: int | float) -> str:
    if isinstance(value, int):
        return f"{value:,}"
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def years_in_text(question: str) -> list[int]:
    return [int(match) for match in re.findall(r"\b((?:19|20)\d{2})\b", question)]


def question_tokens(question: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", question.lower()) if len(token) > 1}


def download_text_report(session: requests.Session, spec: DorTextReportSpec, force: bool = False) -> Path:
    path = RAW_DIR / spec.file_name
    if path.exists() and not force:
        return path
    response = session.get(spec.url, timeout=90)
    response.raise_for_status()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(response.content)
    return path


def taxable_sales_zip_url(year: int) -> str:
    return TAXABLE_SALES_COUNTY_ZIP_TEMPLATE.format(year=year)


def download_taxable_sales_zip(session: requests.Session, year: int, force: bool = False) -> Path:
    source_url = taxable_sales_zip_url(year)
    file_name = source_url.rsplit("/", 1)[-1]
    path = RAW_DIR / file_name
    if path.exists() and not force:
        return path
    response = session.get(source_url, timeout=90)
    response.raise_for_status()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(response.content)
    return path


def download_pdf_report(session: requests.Session, spec: DorTextReportSpec, force: bool = False) -> Path:
    path = RAW_DIR / spec.file_name
    if path.exists() and not force:
        return path
    response = session.get(spec.url, timeout=90)
    response.raise_for_status()
    if "pdf" not in response.headers.get("content-type", "").lower() and not response.content.startswith(b"%PDF"):
        raise ValueError(f"Expected PDF response for {spec.url}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(response.content)
    return path


def parse_business_locations(path: Path, spec: DorTextReportSpec) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    year_match = re.search(r"OPEN DURING:\s+(\d{4})", text)
    year = int(year_match.group(1)) if year_match else None
    records: list[dict[str, Any]] = []
    current_county: str | None = None
    for row_number, line in enumerate(text.splitlines(), start=1):
        county_match = re.match(r"\s*([A-Z][A-Z .'\-]+ COUNTY)\s+-{5,}\s*$", line)
        if county_match:
            current_county = normalize_county(county_match.group(1))
            continue
        if current_county is None:
            continue
        total_match = re.search(r"COUNTY TOTALS:\s+([\d,]+)\*?\s+([\d,]+)", line)
        if total_match:
            records.append(
                {
                    "report_key": spec.key,
                    "record_type": "business_locations_county",
                    "source_label": spec.label,
                    "source_url": spec.url,
                    "source_file": spec.file_name,
                    "source_row_number": row_number,
                    "year": year,
                    "county": current_county,
                    "business_count": clean_int(total_match.group(1)),
                    "location_count": clean_int(total_match.group(2)),
                }
            )
            continue
        city_match = re.match(r"\s{35,}([A-Z0-9 .'/&()\-]+?)\s{2,}([\d,]+)\s+([\d,]+)\s*$", line)
        if city_match:
            city = clean_text(city_match.group(1)).upper()
            records.append(
                {
                    "report_key": spec.key,
                    "record_type": "business_locations_city",
                    "source_label": spec.label,
                    "source_url": spec.url,
                    "source_file": spec.file_name,
                    "source_row_number": row_number,
                    "year": year,
                    "county": current_county,
                    "city": city,
                    "business_count": clean_int(city_match.group(2)),
                    "location_count": clean_int(city_match.group(3)),
                }
            )
    return records


def parse_vehicle_counts(path: Path, spec: DorTextReportSpec) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    date_match = re.search(r"AS OF\s+(\d{2})/(\d{2})/(\d{2})", text)
    as_of_date = None
    if date_match:
        month, day, year_suffix = date_match.groups()
        as_of_date = f"20{year_suffix}-{int(month):02d}-{int(day):02d}"
    records: list[dict[str, Any]] = []
    for row_number, line in enumerate(text.splitlines(), start=1):
        if "," not in line:
            continue
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 4 or not parts[0] or parts[0].upper() == "COUNTY":
            continue
        titled = clean_int(parts[2])
        registered = clean_int(parts[3])
        if titled is None or registered is None:
            continue
        records.append(
            {
                "report_key": spec.key,
                "record_type": "vehicle_county_kind",
                "source_label": spec.label,
                "source_url": spec.url,
                "source_file": spec.file_name,
                "source_row_number": row_number,
                "as_of_date": as_of_date,
                "county": normalize_county(parts[0]),
                "vehicle_kind": clean_text(parts[1]).upper(),
                "titled_count": titled,
                "registered_count": registered,
            }
        )
    return records


def parse_driver_counts(path: Path, spec: DorTextReportSpec) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    run_match = re.search(r"\b(\d{2}/\d{2}/\d{2})\b", text)
    run_date = None
    if run_match:
        month, day, year_suffix = run_match.group(1).split("/")
        run_date = f"20{year_suffix}-{int(month):02d}-{int(day):02d}"
    records: list[dict[str, Any]] = []
    current_county: str | None = None
    for row_number, line in enumerate(text.splitlines(), start=1):
        county_match = re.match(r"\s*-\d{3}\s+([A-Z][A-Z .'\-]+)\s*$", line)
        if county_match:
            current_county = normalize_county(county_match.group(1))
            continue
        if current_county is None:
            continue
        age_match = re.match(r"\s*(-?\d+\s*-\s*\d+)\s+(.+?)\s*$", line)
        if age_match:
            numbers = [clean_int(item) for item in re.findall(r"\b\d[\d,]*\b", age_match.group(2))]
            numbers = [number for number in numbers if number is not None]
            if numbers:
                age_band = re.sub(r"\s+", " ", age_match.group(1).replace("-0", "- 0")).strip()
                records.append(
                    {
                        "report_key": spec.key,
                        "record_type": "driver_county_age_band",
                        "source_label": spec.label,
                        "source_url": spec.url,
                        "source_file": spec.file_name,
                        "source_row_number": row_number,
                        "as_of_date": run_date,
                        "county": current_county,
                        "age_band": age_band,
                        "driver_count": sum(numbers),
                    }
                )
            continue
        total_match = re.match(r"\s+([\d,]+)\s*$", line)
        if total_match:
            total = clean_int(total_match.group(1))
            if total is not None:
                records.append(
                    {
                        "report_key": spec.key,
                        "record_type": "driver_county_total",
                        "source_label": spec.label,
                        "source_url": spec.url,
                        "source_file": spec.file_name,
                        "source_row_number": row_number,
                        "as_of_date": run_date,
                        "county": current_county,
                        "driver_count": total,
                    }
                )
    return records


def parse_dealer_counts(path: Path, spec: DorTextReportSpec) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    counts: dict[tuple[str, str], int] = {}
    for line in text.splitlines():
        if ";" not in line or line.startswith("DLR_TYP"):
            continue
        parts = [part.strip() for part in line.split(";")]
        if len(parts) < 10:
            continue
        dealer_type = clean_text(parts[0]).upper()
        county = normalize_county(parts[8])
        if not dealer_type or not county:
            continue
        counts[(county, dealer_type)] = counts.get((county, dealer_type), 0) + 1
    records: list[dict[str, Any]] = []
    for index, ((county, dealer_type), dealer_count) in enumerate(sorted(counts.items()), start=1):
        records.append(
            {
                "report_key": spec.key,
                "record_type": "dealer_county_type",
                "source_label": spec.label,
                "source_url": spec.url,
                "source_file": spec.file_name,
                "source_row_number": None,
                "county": county,
                "dealer_type": dealer_type,
                "dealer_count": dealer_count,
                "aggregate_record_number": index,
            }
        )
    totals: dict[str, int] = {}
    for (county, _dealer_type), dealer_count in counts.items():
        totals[county] = totals.get(county, 0) + dealer_count
    for index, (county, dealer_count) in enumerate(sorted(totals.items()), start=1):
        records.append(
            {
                "report_key": spec.key,
                "record_type": "dealer_county_total",
                "source_label": spec.label,
                "source_url": spec.url,
                "source_file": spec.file_name,
                "source_row_number": None,
                "county": county,
                "dealer_type": "ALL",
                "dealer_count": dealer_count,
                "aggregate_record_number": index,
            }
        )
    return records


def parse_sic_state(path: Path, spec: DorTextReportSpec) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    records: list[dict[str, Any]] = []
    for row_number, line in enumerate(text.splitlines(), start=1):
        match = re.match(r"\s*(\d{4})\s+(.+?)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s*$", line)
        if not match:
            continue
        records.append(
            {
                "report_key": spec.key,
                "record_type": "sic_state_total",
                "source_label": spec.label,
                "source_url": spec.url,
                "source_file": spec.file_name,
                "source_row_number": row_number,
                "sic4": match.group(1),
                "sic_description": clean_text(match.group(2)).upper(),
                "sales_tax_locations": clean_int(match.group(3)),
                "use_tax_locations": clean_int(match.group(4)),
                "total_locations": clean_int(match.group(5)),
            }
        )
    return records


def parse_sic_county(path: Path, spec: DorTextReportSpec) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    records: list[dict[str, Any]] = []
    current_county: str | None = None
    pattern = re.compile(
        r"\s*(?:(?P<county>[A-Z][A-Z .'\-]+ COUNTY)\s+)?"
        r"(?P<sic4>\d{4})\s+(?P<description>.+?)\s+"
        r"(?P<sales>[\d,]+)\s+(?P<use>[\d,]+)\s+(?P<total>[\d,]+)\s*$"
    )
    for row_number, line in enumerate(text.splitlines(), start=1):
        match = pattern.match(line)
        if not match:
            continue
        if match.group("county"):
            current_county = normalize_county(match.group("county"))
        if current_county is None:
            continue
        records.append(
            {
                "report_key": spec.key,
                "record_type": "sic_county_total",
                "source_label": spec.label,
                "source_url": spec.url,
                "source_file": spec.file_name,
                "source_row_number": row_number,
                "county": current_county,
                "sic4": match.group("sic4"),
                "sic_description": clean_text(match.group("description")).upper(),
                "sales_tax_locations": clean_int(match.group("sales")),
                "use_tax_locations": clean_int(match.group("use")),
                "total_locations": clean_int(match.group("total")),
            }
        )
    return records


def decode_zip_text(data: bytes) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")) or b"\x00" in data[:80]:
        return data.decode("utf-16", errors="replace")
    return data.decode("utf-8-sig", errors="replace")


def parse_taxable_sales_county(path: Path, year: int, source_url: str) -> list[dict[str, Any]]:
    with zipfile.ZipFile(path) as archive:
        csv_name = archive.namelist()[0]
        text = decode_zip_text(archive.read(csv_name))
    records: list[dict[str, Any]] = []

    def add_record(
        row_number: int,
        county_raw: Any,
        county_code_raw: Any,
        quarter_1_raw: Any,
        quarter_2_raw: Any,
        quarter_3_raw: Any,
        quarter_4_raw: Any,
        total_raw: Any,
        statewide_total_raw: Any = None,
    ) -> None:
        county_text = re.sub(r"\bCNTY\b", "COUNTY", clean_text(county_raw), flags=re.IGNORECASE)
        county_label = county_text.upper().replace(".", "")
        if not (county_label.endswith(" COUNTY") or county_label == "ST LOUIS CITY"):
            return
        county = normalize_county(county_text)
        total = clean_decimal(total_raw)
        if not county or total is None:
            return
        records.append(
            {
                "report_key": "taxable_sales_county",
                "record_type": "taxable_sales_county",
                "source_label": "Public taxable sales reports by county, Sales/Use tax, file format",
                "source_url": source_url,
                "source_file": path.name,
                "source_row_number": row_number,
                "year": year,
                "county": county,
                "county_code": clean_text(county_code_raw),
                "tax_type": "Sales/Use",
                "quarter_1": clean_decimal(quarter_1_raw),
                "quarter_2": clean_decimal(quarter_2_raw),
                "quarter_3": clean_decimal(quarter_3_raw),
                "quarter_4": clean_decimal(quarter_4_raw),
                "taxable_sales_total": total,
                "statewide_total": clean_decimal(statewide_total_raw),
            }
        )

    first_line = next((line for line in text.splitlines() if line.strip()), "")
    if ";" in first_line and "," not in first_line and "\t" not in first_line:
        for row_number, line in enumerate(text.splitlines(), start=1):
            parts = [part.strip() for part in line.split(";")]
            if len(parts) < 8 or not re.fullmatch(r"\d{4}", parts[0]):
                continue
            add_record(row_number, parts[2], parts[1], parts[3], parts[4], parts[5], parts[6], parts[7])
        return records

    delimiter = "\t" if "\t" in first_line else ","
    dict_reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=delimiter)
    if dict_reader.fieldnames and "P_Business_name" in dict_reader.fieldnames:
        for row_number, row in enumerate(dict_reader, start=2):
            add_record(
                row_number,
                row.get("P_Business_name"),
                row.get("MOID"),
                row.get("Textbox13"),
                row.get("Textbox14"),
                row.get("Textbox15"),
                row.get("Textbox16"),
                row.get("Total"),
                row.get("Total1"),
            )
        return records

    for row_number, row in enumerate(csv.reader(io.StringIO(text, newline="")), start=1):
        if len(row) < 13 or not re.fullmatch(r"\d{3}", clean_text(row[0])):
            continue
        add_record(row_number, row[2], row[0], row[3], row[6], row[8], row[10], row[12])
    return records


def fiscal_year_from_food_tax_spec(spec: DorTextReportSpec) -> int:
    match = re.search(r"FY(\d{2})", spec.key.upper() + " " + spec.label.upper())
    if not match:
        raise ValueError(f"Could not infer fiscal year from {spec.key}")
    return 2000 + int(match.group(1))


def extract_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def parse_food_tax_pdf(path: Path, spec: DorTextReportSpec) -> list[dict[str, Any]]:
    fiscal_year = fiscal_year_from_food_tax_spec(spec)
    text = extract_pdf_text(path)
    text = text.replace("COUNT\nY", "COUNTY").replace("T **", "T * *")
    text = re.sub(r"\s+", " ", text)
    type_pattern = r"CITY-TIF|COUNTY-TIF|TRANS-DEV|District|County|City|State"
    row_text = re.sub(
        rf"(?=(?:{type_pattern})\s+(?:[A-Z]{{2,}}\d{{3,}}|\d{{2,5}})\s+)",
        "\n",
        text,
        flags=re.IGNORECASE,
    )
    row_pattern = re.compile(
        rf"^(?P<type>{type_pattern})\s+"
        r"(?P<code>[A-Z0-9-]+)\s+"
        r"(?P<name>.+?)\s+"
        r"(?P<amount>-?\$[\d,]+\.\d{2}|\*)\s+"
        r"(?P<accounts>[\d,]+|\*)",
        re.IGNORECASE,
    )
    records: list[dict[str, Any]] = []
    for row_number, line in enumerate(row_text.splitlines(), start=1):
        line = clean_text(line)
        if not line:
            continue
        match = row_pattern.match(line)
        if not match:
            continue
        subdivision_type = clean_text(match.group("type")).upper()
        name = clean_text(match.group("name")).upper()
        if not name or name.startswith("POLITICAL SUBDIVISION"):
            continue
        amount = clean_decimal(match.group("amount"))
        account_count = clean_int(match.group("accounts"))
        records.append(
            {
                "report_key": "food_tax_subdivision",
                "record_type": "food_tax_subdivision",
                "source_label": "Food Tax by Political Subdivision",
                "source_url": spec.url,
                "source_file": path.name,
                "source_row_number": row_number,
                "fiscal_year": fiscal_year,
                "fiscal_year_label": f"FY{str(fiscal_year)[-2:]}",
                "political_subdivision_type": subdivision_type,
                "political_subdivision_code": clean_text(match.group("code")),
                "political_subdivision_name": name,
                "food_tax_reported": amount,
                "account_count": account_count,
                "suppressed": amount is None or account_count is None,
            }
        )
    return records


def calendar_year_from_spec(spec: DorTextReportSpec) -> int:
    match = re.search(r"\b(20\d{2})\b", f"{spec.key} {spec.label} {spec.file_name}")
    if not match:
        raise ValueError(f"Could not infer calendar year from {spec.key}")
    return int(match.group(1))


def fiscal_year_quarter_from_spec(spec: DorTextReportSpec) -> tuple[int, int]:
    text = f"{spec.key} {spec.label} {spec.file_name}".lower()
    year_match = re.search(r"\bfy\s*'?(\d{2,4})\b", text)
    if not year_match:
        year_match = re.search(r"\bfiscal year\s+(20\d{2})\b", text)
    if not year_match:
        raise ValueError(f"Could not infer fiscal year from {spec.key}")
    year = int(year_match.group(1))
    fiscal_year = 2000 + year if year < 100 else year
    quarter_match = re.search(r"\bq([1-4])\b", text)
    if quarter_match:
        return fiscal_year, int(quarter_match.group(1))
    for word, quarter in QUARTER_WORDS.items():
        if re.search(rf"\b{word}[-\s]*quarter\b", text):
            return fiscal_year, quarter
    raise ValueError(f"Could not infer quarter from {spec.key}")


def parse_working_family_tax_credit_pdf(path: Path, spec: DorTextReportSpec) -> list[dict[str, Any]]:
    year = calendar_year_from_spec(spec)
    text = extract_pdf_text(path)
    records: list[dict[str, Any]] = []
    row_pattern = re.compile(
        r"(?P<income>\$[\d,]+\s*-\s*\$[\d,]+|\$[\d,]+\+|Total)\s+"
        r"(?P<claimed>[\d,]+)\s+\$(?P<amount>[\d,]+\.\d{2})\s+\$(?P<average>[\d,]+\.\d{2})",
        re.IGNORECASE,
    )
    for row_number, match in enumerate(row_pattern.finditer(text), start=1):
        income_range = clean_text(match.group("income").replace(" - ", "-"))
        records.append(
            {
                "report_key": "working_family_tax_credit",
                "record_type": "working_family_tax_credit_income_range",
                "source_label": "Missouri Working Family Tax Credit Report",
                "source_url": spec.url,
                "source_file": path.name,
                "source_row_number": row_number,
                "year": year,
                "income_range": income_range,
                "credits_claimed": clean_int(match.group("claimed")),
                "credits_amount": clean_decimal(match.group("amount")),
                "average_credit_amount": clean_decimal(match.group("average")),
                "total_row": income_range.lower() == "total",
            }
        )
    if not records:
        raise ValueError(f"No Working Family Tax Credit rows parsed from {path}")
    return records


def parse_quarterly_tax_credit_pdf(path: Path, spec: DorTextReportSpec) -> list[dict[str, Any]]:
    fiscal_year, quarter = fiscal_year_quarter_from_spec(spec)
    text = extract_pdf_text(path)
    amount_pattern = re.compile(r"\(?\$?-?[\d,]+\.\d{2}\)?")
    records: list[dict[str, Any]] = []
    for row_number, line in enumerate(text.splitlines(), start=1):
        line = clean_text(line)
        amount_match = amount_pattern.search(line)
        if not amount_match:
            continue
        prefix = line[: amount_match.start()].strip()
        amounts = [clean_decimal(item) for item in amount_pattern.findall(line[amount_match.start() :])]
        amounts = [amount for amount in amounts if amount is not None]
        if len(amounts) < 2:
            continue
        credit_type: str | None = None
        credit_code: str | None = None
        reporting_agency: str | None = None
        is_total = prefix.lower() == "total"
        if is_total:
            credit_type = "Total"
            credit_code = "TOTAL"
            reporting_agency = "TOTAL"
        else:
            tokens = prefix.split()
            if not tokens or tokens[-1] not in REPORTING_AGENCY_CODES:
                continue
            reporting_agency = tokens[-1]
            if len(tokens) >= 2 and re.fullmatch(r"[A-Z0-9]{2,4}", tokens[-2]) and tokens[-2] not in REPORTING_AGENCY_CODES:
                credit_code = tokens[-2]
                credit_type = " ".join(tokens[:-2])
            else:
                credit_type = " ".join(tokens[:-1])
        credit_type = clean_text(credit_type)
        if not credit_type:
            continue
        records.append(
            {
                "report_key": "quarterly_tax_credit_report",
                "record_type": "quarterly_tax_credit_report",
                "source_label": "Quarterly Tax Credit Report",
                "source_url": spec.url,
                "source_file": path.name,
                "source_row_number": row_number,
                "fiscal_year": fiscal_year,
                "fiscal_year_label": format_fiscal_year(fiscal_year),
                "quarter": quarter,
                "quarter_label": f"Q{quarter}",
                "credit_type": credit_type,
                "credit_code": credit_code,
                "reporting_agency": reporting_agency,
                "authorized_quarter": amounts[0] if len(amounts) >= 6 else None,
                "authorized_fytd": amounts[1] if len(amounts) >= 6 else None,
                "issued_quarter": amounts[2] if len(amounts) >= 6 else None,
                "issued_fytd": amounts[3] if len(amounts) >= 6 else None,
                "redemptions_quarter": amounts[-2],
                "redemptions_fytd": amounts[-1],
                "numeric_value_count": len(amounts),
                "is_total": is_total,
            }
        )
    if not records:
        raise ValueError(f"No quarterly tax-credit rows parsed from {path}")
    return records


def parse_report(path: Path, spec: DorTextReportSpec) -> list[dict[str, Any]]:
    parsers = {
        "business_locations": parse_business_locations,
        "vehicles_by_county": parse_vehicle_counts,
        "drivers_by_age_county": parse_driver_counts,
        "dealers_by_county": parse_dealer_counts,
        "sic_state": parse_sic_state,
        "sic_county": parse_sic_county,
    }
    return parsers[spec.key](path, spec)


def build_dor_reports_index(force: bool = False, delay_seconds: float = 0.05) -> dict[str, Any]:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (compatible; MissouriPublicDataAssistant/1.0)",
            "Accept": "text/plain,text/csv,application/zip,application/pdf,text/html;q=0.8,*/*;q=0.7",
        }
    )
    start = time.perf_counter()
    all_records: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []
    for spec in TEXT_REPORTS:
        path = download_text_report(session, spec, force=force)
        records = parse_report(path, spec)
        all_records.extend(records)
        files.append(
            {
                "key": spec.key,
                "label": spec.label,
                "file_name": spec.file_name,
                "url": spec.url,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "record_count": len(records),
                "record_types": sorted({record["record_type"] for record in records}),
            }
        )
        if delay_seconds > 0:
            time.sleep(delay_seconds)
    for year in TAXABLE_SALES_YEARS:
        source_url = taxable_sales_zip_url(year)
        taxable_path = download_taxable_sales_zip(session, year, force=force)
        taxable_records = parse_taxable_sales_county(taxable_path, year, source_url)
        all_records.extend(taxable_records)
        files.append(
            {
                "key": "taxable_sales_county",
                "label": "Public taxable sales reports by county, Sales/Use tax, file format",
                "file_name": taxable_path.name,
                "url": source_url,
                "bytes": taxable_path.stat().st_size,
                "sha256": sha256_file(taxable_path),
                "record_count": len(taxable_records),
                "record_types": ["taxable_sales_county"],
                "year": year,
            }
        )
        if delay_seconds > 0:
            time.sleep(delay_seconds)
    for spec in FOOD_TAX_REPORTS:
        food_tax_path = download_pdf_report(session, spec, force=force)
        food_tax_records = parse_food_tax_pdf(food_tax_path, spec)
        all_records.extend(food_tax_records)
        files.append(
            {
                "key": "food_tax_subdivision",
                "label": spec.label,
                "file_name": food_tax_path.name,
                "url": spec.url,
                "bytes": food_tax_path.stat().st_size,
                "sha256": sha256_file(food_tax_path),
                "record_count": len(food_tax_records),
                "record_types": ["food_tax_subdivision"],
                "fiscal_year": fiscal_year_from_food_tax_spec(spec),
            }
        )
        if delay_seconds > 0:
            time.sleep(delay_seconds)
    for spec in WORKING_FAMILY_TAX_CREDIT_REPORTS:
        wftc_path = download_pdf_report(session, spec, force=force)
        wftc_records = parse_working_family_tax_credit_pdf(wftc_path, spec)
        all_records.extend(wftc_records)
        files.append(
            {
                "key": "working_family_tax_credit",
                "label": spec.label,
                "file_name": wftc_path.name,
                "url": spec.url,
                "bytes": wftc_path.stat().st_size,
                "sha256": sha256_file(wftc_path),
                "record_count": len(wftc_records),
                "record_types": ["working_family_tax_credit_income_range"],
                "year": calendar_year_from_spec(spec),
            }
        )
        if delay_seconds > 0:
            time.sleep(delay_seconds)
    for spec in QUARTERLY_TAX_CREDIT_REPORTS:
        tax_credit_path = download_pdf_report(session, spec, force=force)
        tax_credit_records = parse_quarterly_tax_credit_pdf(tax_credit_path, spec)
        fiscal_year, quarter = fiscal_year_quarter_from_spec(spec)
        all_records.extend(tax_credit_records)
        files.append(
            {
                "key": "quarterly_tax_credit_report",
                "label": spec.label,
                "file_name": tax_credit_path.name,
                "url": spec.url,
                "bytes": tax_credit_path.stat().st_size,
                "sha256": sha256_file(tax_credit_path),
                "record_count": len(tax_credit_records),
                "record_types": ["quarterly_tax_credit_report"],
                "fiscal_year": fiscal_year,
                "quarter": quarter,
            }
        )
        if delay_seconds > 0:
            time.sleep(delay_seconds)
    payload = {
        "generated_at_utc": utc_now(),
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "source": "Missouri Department of Revenue public reports",
        "source_url": DOR_PUBLIC_REPORTS_URL,
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
            "record_types": sorted({record["record_type"] for record in all_records}),
        },
    )
    return payload


def is_summary_question(question: str) -> bool:
    lowered = question.lower()
    if asks_for_quarterly_tax_credit_report(question) and (
        tax_credit_periods_in_text(question)
        or re.search(r"\bfy\s*'?\d{2,4}\b", lowered)
        or re.search(r"\bq[1-4]\b", lowered)
        or re.search(r"\b(issued|authorized|redemptions?|redeemed|fy\s*to\s*date|fytd|year\s*to\s*date|ytd)\b", lowered)
    ):
        return False
    return bool(
        re.search(r"\b(what|which|show|list)\b.*\b(dor|department of revenue|revenue)\b.*\b(reports?|data|indexed|connected|sources?)\b", lowered)
        or re.search(r"\b(dor|department of revenue|revenue)\b.*\b(reports?|data)\b.*\b(indexed|connected|available)\b", lowered)
    )


def county_matches(records: list[dict[str, Any]], question: str) -> list[str]:
    lowered = normalize_key(question)
    counties = sorted({record["county"] for record in records if record.get("county")}, key=len, reverse=True)
    matches = []
    for county in counties:
        county_key = normalize_key(county)
        if county_key in lowered or f"{county_key}_county" in lowered:
            matches.append(county)
    return matches


def fiscal_years_in_text(question: str) -> list[int]:
    years: list[int] = []
    for match in re.findall(r"\bfy\s*'?(\d{2,4})\b", question, flags=re.IGNORECASE):
        year = int(match)
        years.append(2000 + year if year < 100 else year)
    for year in years_in_text(question):
        if year not in years:
            years.append(year)
    return years


def food_tax_type_filter(question: str) -> str | None:
    lowered = question.lower()
    if re.search(r"\b(county|counties)\b", lowered):
        return "COUNTY"
    if re.search(r"\b(cities|city)\b", lowered):
        return "CITY"
    if re.search(r"\b(district|districts|cid|tdd|tif)\b", lowered):
        return "DISTRICT"
    if re.search(r"\b(state|statewide|missouri)\b", lowered):
        return "STATE"
    return None


def food_tax_matches(records: list[dict[str, Any]], question: str, type_filter: str | None = None) -> list[dict[str, Any]]:
    question_key = normalize_key(question)
    candidates = [
        record
        for record in records
        if type_filter is None
        or str(record.get("political_subdivision_type", "")).upper() == type_filter
        or (type_filter == "DISTRICT" and "DISTRICT" in str(record.get("political_subdivision_type", "")).upper())
    ]
    matches: list[dict[str, Any]] = []
    for record in sorted(candidates, key=lambda row: len(str(row.get("political_subdivision_name", ""))), reverse=True):
        name = str(record.get("political_subdivision_name") or "")
        name_key = normalize_key(name)
        if not name_key:
            continue
        bare_county_key = normalize_key(re.sub(r"\s+COUNTY$", "", name, flags=re.IGNORECASE))
        is_county_row = str(record.get("political_subdivision_type", "")).upper() == "COUNTY"
        if (
            name_key in question_key
            or (bare_county_key and f"{bare_county_key}_county" in question_key)
            or (is_county_row and bare_county_key and bare_county_key in question_key)
        ):
            matches.append(record)
    return matches


def wftc_income_matches(records: list[dict[str, Any]], question: str) -> list[dict[str, Any]]:
    question_key = normalize_key(question)
    if re.search(r"\b(total|overall|all\s+income|all\s+ranges?)\b", question, flags=re.IGNORECASE):
        total = [row for row in records if row.get("total_row")]
        if total:
            return total
    matches: list[dict[str, Any]] = []
    for record in sorted(records, key=lambda row: len(str(row.get("income_range", ""))), reverse=True):
        income_range = str(record.get("income_range") or "")
        range_key = normalize_key(income_range)
        if range_key and range_key in question_key:
            matches.append(record)
            continue
        bounds = re.findall(r"\d[\d,]*", income_range)
        if len(bounds) >= 2 and all(normalize_key(bound) in question_key for bound in bounds[:2]):
            matches.append(record)
        elif len(bounds) == 1 and "+" in income_range and normalize_key(bounds[0]) in question_key:
            matches.append(record)
    return matches


def format_fiscal_year(year: int) -> str:
    return f"FY{str(year)[-2:]}"


def find_vehicle_kind(question: str) -> str:
    lowered = question.lower()
    for alias, kind in sorted(VEHICLE_KIND_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if re.search(rf"\b{re.escape(alias)}\b", lowered):
            return kind
    return "COUNTY TOTALS"


def find_dealer_type(question: str) -> str:
    lowered = question.lower()
    for alias, dealer_type in sorted(DEALER_TYPE_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if re.search(rf"\b{re.escape(alias)}\b", lowered):
            return dealer_type
    return "ALL"


def asks_for_top(question: str) -> bool:
    lowered = question.lower()
    return any(word in lowered for word in ["top", "highest", "largest", "most", "biggest"])


def asks_for_titled(question: str) -> bool:
    return "titled" in question.lower()


def asks_for_business_locations(question: str) -> bool:
    lowered = question.lower()
    return "business location" in lowered or "business locations" in lowered or "location counts" in lowered


def asks_for_taxable_sales(question: str) -> bool:
    lowered = question.lower()
    return "taxable sales" in lowered or ("sales/use" in lowered and "county" in lowered)


def asks_for_food_tax(question: str) -> bool:
    lowered = question.lower()
    return "food tax" in lowered or "food-tax" in lowered or "grocery tax" in lowered


def asks_for_working_family_tax_credit(question: str) -> bool:
    lowered = question.lower()
    return (
        "working family tax credit" in lowered
        or "working family tax credits" in lowered
        or "wftc" in lowered
    )


def asks_for_quarterly_tax_credit_report(question: str) -> bool:
    lowered = question.lower()
    has_tax_credit_term = "tax credit" in lowered or "tax credits" in lowered
    has_period = bool(
        tax_credit_periods_in_text(question)
        or re.search(r"\bfy\s*'?\d{2,4}\b", lowered)
        or re.search(r"\bq[1-4]\b", lowered)
        or re.search(r"\b(first|second|third|fourth)\s+quarter\b", lowered)
    )
    has_metric = bool(re.search(r"\b(issued|authorized|redemptions?|redeemed|fy\s*to\s*date|fytd|year\s*to\s*date|ytd)\b", lowered))
    if not has_tax_credit_term and not (has_period and has_metric):
        return False
    return bool(
        "tax credit report" in lowered
        or "quarterly tax credit" in lowered
        or "quarterly credit" in lowered
        or has_period
    )


def asks_for_vehicles(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["vehicle", "vehicles", "registered", "titled", "passenger", "truck", "motorcycle", "trailer"])


def asks_for_drivers(question: str) -> bool:
    lowered = question.lower()
    return "driver" in lowered or "drivers" in lowered or "licensed drivers" in lowered


def asks_for_dealers(question: str) -> bool:
    lowered = question.lower()
    return "dealer" in lowered or "dealers" in lowered or "dealership" in lowered


def asks_for_sic(question: str) -> bool:
    lowered = question.lower()
    return "sic" in lowered or "industry" in lowered or re.search(r"\b\d{4}\b", lowered) is not None


def tax_credit_periods_in_text(question: str) -> list[tuple[int, int]]:
    lowered = question.lower()
    periods: list[tuple[int, int]] = []

    def add_period(year_text: str, quarter_text: str) -> None:
        year = int(year_text)
        fiscal_year = 2000 + year if year < 100 else year
        quarter = int(quarter_text)
        period = (fiscal_year, quarter)
        if period not in periods:
            periods.append(period)

    for match in re.finditer(r"\bfy\s*'?(\d{2,4})\s*(?:q|quarter\s*)([1-4])\b", lowered):
        add_period(match.group(1), match.group(2))
    for match in re.finditer(r"\bq([1-4])\s*fy\s*'?(\d{2,4})\b", lowered):
        add_period(match.group(2), match.group(1))
    for word, quarter in QUARTER_WORDS.items():
        for match in re.finditer(rf"\b{word}\s+quarter\b.*?\bfy\s*'?(\d{{2,4}})\b", lowered):
            add_period(match.group(1), str(quarter))
        for match in re.finditer(rf"\bfy\s*'?(\d{{2,4}})\b.*?\b{word}\s+quarter\b", lowered):
            add_period(match.group(1), str(quarter))
    return periods


def requested_tax_credit_period(records: list[dict[str, Any]], question: str) -> tuple[int, int] | None:
    available = sorted({(int(row["fiscal_year"]), int(row["quarter"])) for row in records if row.get("fiscal_year") and row.get("quarter")})
    if not available:
        return None
    periods = tax_credit_periods_in_text(question)
    if periods:
        return periods[-1]
    fiscal_years = fiscal_years_in_text(question)
    quarter = None
    quarter_match = re.search(r"\bq([1-4])\b", question.lower())
    if quarter_match:
        quarter = int(quarter_match.group(1))
    else:
        for word, value in QUARTER_WORDS.items():
            if re.search(rf"\b{word}\s+quarter\b", question.lower()):
                quarter = value
                break
    if fiscal_years:
        year = fiscal_years[-1]
        year_quarters = [item[1] for item in available if item[0] == year]
        if not year_quarters:
            return (year, quarter or 0)
        return (year, quarter or max(year_quarters))
    return available[-1]


def tax_credit_metric(question: str) -> tuple[str, str]:
    lowered = question.lower()
    fytd = bool(re.search(r"\b(fy\s*to\s*date|fytd|year\s*to\s*date|ytd)\b", lowered))
    if "authorized" in lowered:
        return ("authorized_fytd" if fytd else "authorized_quarter", "authorized FY-to-date" if fytd else "authorized this quarter")
    if "redemption" in lowered or "redemptions" in lowered or "redeemed" in lowered:
        return ("redemptions_fytd" if fytd else "redemptions_quarter", "redemptions FY-to-date" if fytd else "redemptions this quarter")
    if "quarter" in lowered and not fytd and not re.search(r"\bfy\s*to\s*date|fytd|ytd\b", lowered):
        return ("issued_quarter", "issued this quarter")
    return ("issued_fytd", "issued FY-to-date")


def tax_credit_matches(records: list[dict[str, Any]], question: str) -> list[dict[str, Any]]:
    question_key = normalize_key(question)
    tokens = question_tokens(question)
    matches: list[dict[str, Any]] = []
    for record in sorted(records, key=lambda row: len(str(row.get("credit_type", ""))), reverse=True):
        if record.get("is_total"):
            continue
        name = str(record.get("credit_type") or "")
        code = str(record.get("credit_code") or "").lower()
        name_key = normalize_key(name)
        if name_key and name_key in question_key:
            matches.append(record)
            continue
        if code and code in tokens:
            matches.append(record)
            continue
        simplified_name = normalize_key(re.sub(r"\btax\s+credit\b|\bcredit\b", "", name, flags=re.IGNORECASE))
        if simplified_name and simplified_name in question_key:
            matches.append(record)
    return matches


class DorReportsIndex:
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

    def records_of_type(self, record_type: str) -> list[dict[str, Any]]:
        return [record for record in self.records() if record.get("record_type") == record_type]

    def file_info(self, source_file: str) -> dict[str, Any] | None:
        for item in self.payload().get("files", []):
            if item.get("file_name") == source_file:
                return item
        return None

    def coverage_citation(self, matched_rows: int = 0) -> list[dict[str, Any]]:
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
            for item in files[:6]
        ]
        return [
            {
                "dataset": "Missouri Department of Revenue public reports",
                "category": "Revenue public reports",
                "kind": "aggregate DOR report coverage",
                "lookup_table": "dor_reports_index",
                "year": None,
                "year_range": "2016-2025 taxable sales, FY22-FY25 food tax, 2024-2025 Working Family Tax Credit, FY25-FY26 quarterly tax-credit reports, 2016 business locations, 2017 vehicle counts, 2024 driver counts, plus SIC report snapshots",
                "source_files": source_files,
                "source_file_count": len(files),
                "source_rows": sum(item.get("record_count") or 0 for item in files),
                "matched_rows": matched_rows,
            }
        ]

    def citation(self, record: dict[str, Any], matched_rows: int = 1) -> list[dict[str, Any]]:
        file_info = self.file_info(record["source_file"]) or {}
        return [
            {
                "dataset": "Missouri Department of Revenue public reports",
                "category": "Revenue public reports",
                "kind": record.get("record_type", "aggregate DOR report"),
                "lookup_table": "dor_reports_index",
                "year": record.get("year") or record.get("fiscal_year"),
                "year_range": record.get("as_of_date") or file_info.get("year") or file_info.get("fiscal_year"),
                "source_files": [
                    {
                        "category": record.get("report_key"),
                        "category_label": record.get("source_label"),
                        "file_name": record.get("source_url"),
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

    def missing_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "I have exact DOR aggregate parsers for 2016-2025 county taxable sales, 2016 business locations, "
                "FY22-FY25 food tax by political subdivision, 2024-2025 Working Family Tax Credit income ranges, FY25-FY26 quarterly tax-credit reports, vehicle counts by county, licensed-driver county totals, dealer counts by county/type, and SIC location counts, "
                "but I could not identify the county, metric, or supported report needed for this question."
            ),
            "retrieved_context_id": "dor_reports_index:no_match",
            "retrieved_source": "dor_reports_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Answered from DOR coverage metadata because no exact aggregate row matched.",
            "citations": self.coverage_citation(),
            "source_rows": [],
        }

    def unavailable_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "The DOR aggregate report index has not been built yet. Run "
                "`python scripts/build_dor_reports_index.py --force` to download public DOR aggregate reports and build exact lookups."
            ),
            "retrieved_context_id": "dor_reports_index:missing",
            "retrieved_source": "dor_reports_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "The DOR source route exists, but the local ignored index is missing.",
            "citations": [],
            "source_rows": [],
        }

    def summary_answer(self, question: str) -> dict[str, Any]:
        files = self.payload().get("files", [])
        labels = [
            "2016-2025 county taxable sales",
            "FY22-FY25 food tax by political subdivision",
            "2024-2025 Working Family Tax Credit income ranges",
            "FY25-FY26 quarterly tax-credit authorized, issued, and redemption report rows",
            "2016 business locations by city/county",
            "vehicle counts by county/kind",
            "licensed-driver totals by county/age band",
            "dealer counts aggregated by county/type",
            "4-digit SIC location totals statewide and by county",
        ]
        return {
            "question": question,
            "answer": (
                f"The DOR exact lookup layer is built from {len(files)} official public report files and "
                f"{self.payload().get('record_count', 0):,} parsed aggregate records. Indexed DOR report families: "
                f"{'; '.join(labels)}. It returns aggregate counts and totals only; dealer source files are summarized "
                "by county/type rather than exposing individual addresses or phone numbers."
            ),
            "retrieved_context_id": "dor_reports_index:summary",
            "retrieved_source": "dor_reports_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local DOR aggregate report index.",
            "citations": self.coverage_citation(matched_rows=len(files)),
            "source_rows": [],
        }

    def taxable_sales_answer(self, question: str) -> dict[str, Any] | None:
        rows = self.records_of_type("taxable_sales_county")
        if not rows:
            return None
        available_years = sorted({int(row["year"]) for row in rows if row.get("year")})
        if not available_years:
            return None
        available_label = f"{available_years[0]}-{available_years[-1]}"
        years = years_in_text(question)
        requested_years: list[int] = []
        for year in years:
            if year not in requested_years:
                requested_years.append(year)
        missing_year = next((year for year in requested_years if year not in available_years), None)
        if missing_year is not None:
            return {
                "question": question,
                "answer": (
                    f"The DOR taxable-sales exact parser currently indexes county Sales/Use totals for {available_label}, "
                    f"not requested year {missing_year}."
                ),
                "retrieved_context_id": f"dor_reports_index:taxable_sales:missing_year:{missing_year}",
                "retrieved_source": "dor_reports_lookup_index",
                "retrieval_score": 1.0,
                "used_model": False,
                "model": "deterministic_public_lookup",
                "source_note": "Answered from DOR taxable-sales coverage metadata.",
                "citations": self.coverage_citation(),
                "source_rows": [],
            }
        requested_year = requested_years[0] if requested_years else available_years[-1]
        year_rows = [row for row in rows if int(row["year"]) == requested_year]
        counties = county_matches(rows, question)
        if len(requested_years) >= 2 and counties:
            county = counties[0]
            start_year, end_year = requested_years[0], requested_years[1]
            start_row = next((row for row in rows if row["county"] == county and int(row["year"]) == start_year), None)
            end_row = next((row for row in rows if row["county"] == county and int(row["year"]) == end_year), None)
            if start_row is not None and end_row is not None:
                start_total = float(start_row["taxable_sales_total"])
                end_total = float(end_row["taxable_sales_total"])
                difference = end_total - start_total
                if difference > 0:
                    change_label = "increased"
                    amount_label = f"an increase of {value_label(abs(difference))}"
                elif difference < 0:
                    change_label = "decreased"
                    amount_label = f"a decrease of {value_label(abs(difference))}"
                else:
                    change_label = "did not change"
                    amount_label = "no dollar change"
                percent_label = "" if start_total == 0 else f" ({abs(difference) / start_total * 100:.1f}%)"
                return {
                    "question": question,
                    "answer": (
                        f"{display_county(county)} DOR county Sales/Use taxable sales {change_label} from "
                        f"{value_label(start_total)} in {start_year} to {value_label(end_total)} in {end_year}, "
                        f"{amount_label}{percent_label}."
                    ),
                    "retrieved_context_id": (
                        f"dor_reports_index:taxable_sales:{normalize_key(county)}:{start_year}_to_{end_year}"
                    ),
                    "retrieved_source": "dor_reports_lookup_index",
                    "retrieval_score": 1.0,
                    "used_model": False,
                    "model": "deterministic_public_lookup",
                    "source_note": "Computed by comparing county totals in two DOR taxable-sales county files.",
                    "citations": self.citation(start_row) + self.citation(end_row),
                    "source_rows": [
                        {"source_file": start_row["source_file"], "values": start_row},
                        {"source_file": end_row["source_file"], "values": end_row},
                    ],
                }
        if asks_for_top(question):
            top = max(year_rows, key=lambda row: float(row["taxable_sales_total"]))
            return {
                "question": question,
                "answer": (
                    f"In the indexed {requested_year} DOR county Sales/Use taxable-sales file, "
                    f"{top['county']} has the highest taxable-sales total: {value_label(top['taxable_sales_total'])}."
                ),
                "retrieved_context_id": f"dor_reports_index:taxable_sales:{requested_year}:top_county",
                "retrieved_source": "dor_reports_lookup_index",
                "retrieval_score": 1.0,
                "used_model": False,
                "model": "deterministic_public_lookup",
                "source_note": "Computed by ranking county totals in the DOR taxable-sales county file.",
                "citations": self.citation(top, matched_rows=len(year_rows)),
                "source_rows": [{"source_file": top["source_file"], "values": top}],
            }
        if not counties:
            return None
        row = next((item for item in year_rows if item["county"] == counties[0]), None)
        if row is None:
            return None
        return {
            "question": question,
            "answer": (
                f"The indexed DOR county Sales/Use taxable sales total for {display_county(row['county'])} in {requested_year} is "
                f"{value_label(row['taxable_sales_total'])}. Quarter totals: Q1 {value_label(row['quarter_1'])}, "
                f"Q2 {value_label(row['quarter_2'])}, Q3 {value_label(row['quarter_3'])}, Q4 {value_label(row['quarter_4'])}."
            ),
            "retrieved_context_id": f"dor_reports_index:taxable_sales:{requested_year}:{normalize_key(row['county'])}",
            "retrieved_source": "dor_reports_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the DOR taxable-sales county file.",
            "citations": self.citation(row),
            "source_rows": [{"source_file": row["source_file"], "values": row}],
        }

    def food_tax_answer(self, question: str) -> dict[str, Any] | None:
        rows = self.records_of_type("food_tax_subdivision")
        if not rows:
            return None
        available_years = sorted({int(row["fiscal_year"]) for row in rows if row.get("fiscal_year")})
        if not available_years:
            return None
        available_label = f"{format_fiscal_year(available_years[0])}-{format_fiscal_year(available_years[-1])}"
        requested_years: list[int] = []
        for year in fiscal_years_in_text(question):
            if year not in requested_years:
                requested_years.append(year)
        missing_year = next((year for year in requested_years if year not in available_years), None)
        if missing_year is not None:
            return {
                "question": question,
                "answer": (
                    f"The DOR food-tax exact parser currently indexes Food Tax by Political Subdivision reports for "
                    f"{available_label}, not requested {format_fiscal_year(missing_year)}."
                ),
                "retrieved_context_id": f"dor_reports_index:food_tax:missing_year:{missing_year}",
                "retrieved_source": "dor_reports_lookup_index",
                "retrieval_score": 1.0,
                "used_model": False,
                "model": "deterministic_public_lookup",
                "source_note": "Answered from DOR food-tax coverage metadata.",
                "citations": self.coverage_citation(),
                "source_rows": [],
            }
        requested_year = requested_years[0] if requested_years else available_years[-1]
        year_rows = [row for row in rows if int(row["fiscal_year"]) == requested_year]
        type_filter = food_tax_type_filter(question)
        filtered_rows = [
            row
            for row in year_rows
            if type_filter is None
            or str(row.get("political_subdivision_type", "")).upper() == type_filter
            or (type_filter == "DISTRICT" and "DISTRICT" in str(row.get("political_subdivision_type", "")).upper())
        ]
        matches = food_tax_matches(year_rows, question, type_filter)
        if len(requested_years) >= 2 and matches:
            name = matches[0]["political_subdivision_name"]
            subdivision_type = matches[0]["political_subdivision_type"]
            start_year, end_year = requested_years[0], requested_years[1]
            start_row = next(
                (
                    row
                    for row in rows
                    if row["political_subdivision_name"] == name
                    and row["political_subdivision_type"] == subdivision_type
                    and int(row["fiscal_year"]) == start_year
                ),
                None,
            )
            end_row = next(
                (
                    row
                    for row in rows
                    if row["political_subdivision_name"] == name
                    and row["political_subdivision_type"] == subdivision_type
                    and int(row["fiscal_year"]) == end_year
                ),
                None,
            )
            if start_row and end_row and start_row.get("food_tax_reported") is not None and end_row.get("food_tax_reported") is not None:
                start_total = float(start_row["food_tax_reported"])
                end_total = float(end_row["food_tax_reported"])
                difference = end_total - start_total
                if difference > 0:
                    change_label = "increased"
                    amount_label = f"an increase of {value_label(abs(difference))}"
                elif difference < 0:
                    change_label = "decreased"
                    amount_label = f"a decrease of {value_label(abs(difference))}"
                else:
                    change_label = "did not change"
                    amount_label = "no dollar change"
                percent_label = "" if start_total == 0 else f" ({abs(difference) / abs(start_total) * 100:.1f}%)"
                return {
                    "question": question,
                    "answer": (
                        f"{name.title()} DOR food tax reported {change_label} from {value_label(start_total)} in "
                        f"{format_fiscal_year(start_year)} to {value_label(end_total)} in {format_fiscal_year(end_year)}, "
                        f"{amount_label}{percent_label}."
                    ),
                    "retrieved_context_id": f"dor_reports_index:food_tax:{normalize_key(name)}:{start_year}_to_{end_year}",
                    "retrieved_source": "dor_reports_lookup_index",
                    "retrieval_score": 1.0,
                    "used_model": False,
                    "model": "deterministic_public_lookup",
                    "source_note": "Computed by comparing two DOR Food Tax by Political Subdivision reports.",
                    "citations": self.citation(start_row) + self.citation(end_row),
                    "source_rows": [
                        {"source_file": start_row["source_file"], "values": start_row},
                        {"source_file": end_row["source_file"], "values": end_row},
                    ],
                }
        if asks_for_top(question):
            ranked_rows = [row for row in filtered_rows if row.get("food_tax_reported") is not None]
            if not ranked_rows:
                return None
            top = max(ranked_rows, key=lambda row: float(row["food_tax_reported"]))
            type_label = str(top["political_subdivision_type"]).lower()
            return {
                "question": question,
                "answer": (
                    f"In the DOR {format_fiscal_year(requested_year)} Food Tax by Political Subdivision report, "
                    f"{top['political_subdivision_name']} has the highest indexed {type_label} food tax reported: "
                    f"{value_label(top['food_tax_reported'])} across {top['account_count']:,} accounts."
                ),
                "retrieved_context_id": f"dor_reports_index:food_tax:{requested_year}:top_{normalize_key(type_label)}",
                "retrieved_source": "dor_reports_lookup_index",
                "retrieval_score": 1.0,
                "used_model": False,
                "model": "deterministic_public_lookup",
                "source_note": "Computed by ranking DOR food-tax political-subdivision rows.",
                "citations": self.citation(top, matched_rows=len(ranked_rows)),
                "source_rows": [{"source_file": top["source_file"], "values": top}],
            }
        if not matches:
            return None
        row = matches[0]
        fiscal_year_label = format_fiscal_year(int(row["fiscal_year"]))
        name_label = row["political_subdivision_name"].title()
        if row.get("suppressed") or row.get("food_tax_reported") is None or row.get("account_count") is None:
            return {
                "question": question,
                "answer": (
                    f"The DOR {fiscal_year_label} Food Tax by Political Subdivision report lists {name_label}, "
                    "but the amount and account count are suppressed in the source because the cell has six or fewer businesses."
                ),
                "retrieved_context_id": f"dor_reports_index:food_tax:{row['fiscal_year']}:{normalize_key(row['political_subdivision_name'])}:suppressed",
                "retrieved_source": "dor_reports_lookup_index",
                "retrieval_score": 1.0,
                "used_model": False,
                "model": "deterministic_public_lookup",
                "source_note": "The DOR report marks this public aggregate cell as suppressed.",
                "citations": self.citation(row),
                "source_rows": [{"source_file": row["source_file"], "values": row}],
            }
        return {
            "question": question,
            "answer": (
                f"The DOR {fiscal_year_label} Food Tax by Political Subdivision report lists {name_label} food tax "
                f"reported at {value_label(row['food_tax_reported'])} across {row['account_count']:,} accounts."
            ),
            "retrieved_context_id": f"dor_reports_index:food_tax:{row['fiscal_year']}:{normalize_key(row['political_subdivision_name'])}",
            "retrieved_source": "dor_reports_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the DOR Food Tax by Political Subdivision report.",
            "citations": self.citation(row),
            "source_rows": [{"source_file": row["source_file"], "values": row}],
        }

    def working_family_tax_credit_answer(self, question: str) -> dict[str, Any] | None:
        rows = self.records_of_type("working_family_tax_credit_income_range")
        if not rows:
            return None
        available_years = sorted({int(row["year"]) for row in rows if row.get("year")})
        if not available_years:
            return None
        years = []
        for year in years_in_text(question):
            if year not in years:
                years.append(year)
        missing_year = next((year for year in years if year not in available_years), None)
        available_label = f"{available_years[0]}-{available_years[-1]}"
        if missing_year is not None:
            return {
                "question": question,
                "answer": (
                    f"The DOR Working Family Tax Credit exact parser currently indexes calendar years "
                    f"{available_label}, not requested year {missing_year}."
                ),
                "retrieved_context_id": f"dor_reports_index:wftc:missing_year:{missing_year}",
                "retrieved_source": "dor_reports_lookup_index",
                "retrieval_score": 1.0,
                "used_model": False,
                "model": "deterministic_public_lookup",
                "source_note": "Answered from DOR Working Family Tax Credit coverage metadata.",
                "citations": self.coverage_citation(),
                "source_rows": [],
            }
        requested_year = years[0] if years else available_years[-1]
        year_rows = [row for row in rows if int(row["year"]) == requested_year]
        if len(years) >= 2:
            start_year, end_year = years[0], years[1]
            start_row = next((row for row in rows if int(row["year"]) == start_year and row.get("total_row")), None)
            end_row = next((row for row in rows if int(row["year"]) == end_year and row.get("total_row")), None)
            if start_row and end_row:
                start_amount = float(start_row["credits_amount"])
                end_amount = float(end_row["credits_amount"])
                difference = end_amount - start_amount
                if difference > 0:
                    change_label = "increased"
                    amount_label = f"an increase of {value_label(abs(difference))}"
                elif difference < 0:
                    change_label = "decreased"
                    amount_label = f"a decrease of {value_label(abs(difference))}"
                else:
                    change_label = "did not change"
                    amount_label = "no dollar change"
                percent_label = "" if start_amount == 0 else f" ({abs(difference) / abs(start_amount) * 100:.1f}%)"
                claimed_difference = int(end_row["credits_claimed"]) - int(start_row["credits_claimed"])
                claimed_label = "more" if claimed_difference >= 0 else "fewer"
                return {
                    "question": question,
                    "answer": (
                        f"DOR Working Family Tax Credit total amount {change_label} from {value_label(start_amount)} "
                        f"in {start_year} to {value_label(end_amount)} in {end_year}, {amount_label}{percent_label}. "
                        f"Credits claimed changed from {start_row['credits_claimed']:,} to {end_row['credits_claimed']:,} "
                        f"({abs(claimed_difference):,} {claimed_label})."
                    ),
                    "retrieved_context_id": f"dor_reports_index:wftc:{start_year}_to_{end_year}",
                    "retrieved_source": "dor_reports_lookup_index",
                    "retrieval_score": 1.0,
                    "used_model": False,
                    "model": "deterministic_public_lookup",
                    "source_note": "Computed by comparing DOR Working Family Tax Credit report totals.",
                    "citations": self.citation(start_row) + self.citation(end_row),
                    "source_rows": [
                        {"source_file": start_row["source_file"], "values": start_row},
                        {"source_file": end_row["source_file"], "values": end_row},
                    ],
                }
        if asks_for_top(question):
            metric = "credits_claimed" if re.search(r"\b(claimed|claims?|number|count)\b", question.lower()) else "credits_amount"
            candidates = [row for row in year_rows if not row.get("total_row") and row.get(metric) is not None]
            if not candidates:
                return None
            top = max(candidates, key=lambda row: float(row[metric]))
            metric_label = "credits claimed" if metric == "credits_claimed" else "credit amount"
            return {
                "question": question,
                "answer": (
                    f"In the {requested_year} DOR Working Family Tax Credit report, income range "
                    f"{top['income_range']} had the highest {metric_label}: {value_label(top[metric])}. "
                    f"That row lists {top['credits_claimed']:,} credits claimed, total amount "
                    f"{value_label(top['credits_amount'])}, and average credit {value_label(top['average_credit_amount'])}."
                ),
                "retrieved_context_id": f"dor_reports_index:wftc:{requested_year}:top_{metric}",
                "retrieved_source": "dor_reports_lookup_index",
                "retrieval_score": 1.0,
                "used_model": False,
                "model": "deterministic_public_lookup",
                "source_note": "Computed by ranking DOR Working Family Tax Credit income-range rows.",
                "citations": self.citation(top, matched_rows=len(candidates)),
                "source_rows": [{"source_file": top["source_file"], "values": top}],
            }
        matches = wftc_income_matches(year_rows, question)
        row = matches[0] if matches else next((item for item in year_rows if item.get("total_row")), None)
        if row is None:
            return None
        range_label = "all income ranges" if row.get("total_row") else f"income range {row['income_range']}"
        return {
            "question": question,
            "answer": (
                f"The {requested_year} DOR Working Family Tax Credit report lists {row['credits_claimed']:,} "
                f"credits claimed for {range_label}, total amount {value_label(row['credits_amount'])}, "
                f"and average credit {value_label(row['average_credit_amount'])}."
            ),
            "retrieved_context_id": f"dor_reports_index:wftc:{requested_year}:{normalize_key(str(row['income_range']))}",
            "retrieved_source": "dor_reports_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the DOR Working Family Tax Credit report.",
            "citations": self.citation(row),
            "source_rows": [{"source_file": row["source_file"], "values": row}],
        }

    def quarterly_tax_credit_answer(self, question: str) -> dict[str, Any] | None:
        rows = self.records_of_type("quarterly_tax_credit_report")
        if not rows:
            return None
        available_periods = sorted(
            {(int(row["fiscal_year"]), int(row["quarter"])) for row in rows if row.get("fiscal_year") and row.get("quarter")}
        )
        if not available_periods:
            return None
        requested_periods = tax_credit_periods_in_text(question)
        missing_period = next((period for period in requested_periods if period not in available_periods), None)
        if missing_period is not None:
            available_label = ", ".join(f"{format_fiscal_year(year)} Q{quarter}" for year, quarter in available_periods)
            return {
                "question": question,
                "answer": (
                    f"The DOR quarterly tax-credit parser currently indexes these report periods: {available_label}. "
                    f"It does not have {format_fiscal_year(missing_period[0])} Q{missing_period[1]}."
                ),
                "retrieved_context_id": f"dor_reports_index:quarterly_tax_credit:missing:{missing_period[0]}_q{missing_period[1]}",
                "retrieved_source": "dor_reports_lookup_index",
                "retrieval_score": 1.0,
                "used_model": False,
                "model": "deterministic_public_lookup",
                "source_note": "Answered from DOR quarterly tax-credit report coverage metadata.",
                "citations": self.coverage_citation(),
                "source_rows": [],
            }
        period = requested_tax_credit_period(rows, question)
        if period is None:
            return None
        fiscal_year, quarter = period
        period_rows = [
            row for row in rows if int(row.get("fiscal_year") or 0) == fiscal_year and int(row.get("quarter") or 0) == quarter
        ]
        if not period_rows:
            return None
        metric, metric_label = tax_credit_metric(question)
        matches = tax_credit_matches(period_rows, question)
        if len(requested_periods) >= 2 and matches:
            start_period, end_period = requested_periods[0], requested_periods[1]
            match = matches[0]
            credit_key = normalize_key(str(match.get("credit_type") or ""))
            start_row = next(
                (
                    row
                    for row in rows
                    if int(row.get("fiscal_year") or 0) == start_period[0]
                    and int(row.get("quarter") or 0) == start_period[1]
                    and normalize_key(str(row.get("credit_type") or "")) == credit_key
                ),
                None,
            )
            end_row = next(
                (
                    row
                    for row in rows
                    if int(row.get("fiscal_year") or 0) == end_period[0]
                    and int(row.get("quarter") or 0) == end_period[1]
                    and normalize_key(str(row.get("credit_type") or "")) == credit_key
                ),
                None,
            )
            if start_row and end_row and start_row.get(metric) is not None and end_row.get(metric) is not None:
                start_value = float(start_row[metric])
                end_value = float(end_row[metric])
                difference = end_value - start_value
                if difference > 0:
                    change_label = "increased"
                    amount_label = f"an increase of {value_label(abs(difference))}"
                elif difference < 0:
                    change_label = "decreased"
                    amount_label = f"a decrease of {value_label(abs(difference))}"
                else:
                    change_label = "did not change"
                    amount_label = "no dollar change"
                percent_label = "" if start_value == 0 else f" ({abs(difference) / abs(start_value) * 100:.1f}%)"
                return {
                    "question": question,
                    "answer": (
                        f"DOR quarterly tax-credit report {metric_label} for {match['credit_type']} {change_label} from "
                        f"{value_label(start_value)} in {format_fiscal_year(start_period[0])} Q{start_period[1]} to "
                        f"{value_label(end_value)} in {format_fiscal_year(end_period[0])} Q{end_period[1]}, "
                        f"{amount_label}{percent_label}."
                    ),
                    "retrieved_context_id": (
                        f"dor_reports_index:quarterly_tax_credit:{credit_key}:{start_period[0]}_q{start_period[1]}_to_{end_period[0]}_q{end_period[1]}"
                    ),
                    "retrieved_source": "dor_reports_lookup_index",
                    "retrieval_score": 1.0,
                    "used_model": False,
                    "model": "deterministic_public_lookup",
                    "source_note": "Computed by comparing two DOR quarterly tax-credit report rows.",
                    "citations": self.citation(start_row) + self.citation(end_row),
                    "source_rows": [
                        {"source_file": start_row["source_file"], "values": start_row},
                        {"source_file": end_row["source_file"], "values": end_row},
                    ],
                }
        if asks_for_top(question):
            candidates = [row for row in period_rows if not row.get("is_total") and row.get(metric) is not None]
            if not candidates:
                return None
            top = max(candidates, key=lambda row: float(row[metric]))
            code_text = f" ({top['credit_code']})" if top.get("credit_code") else ""
            return {
                "question": question,
                "answer": (
                    f"In the DOR {format_fiscal_year(fiscal_year)} Q{quarter} quarterly tax-credit report, "
                    f"{top['credit_type']}{code_text} had the highest {metric_label}: {value_label(top[metric])}. "
                    f"Reporting agency: {top.get('reporting_agency') or 'not listed'}."
                ),
                "retrieved_context_id": f"dor_reports_index:quarterly_tax_credit:{fiscal_year}_q{quarter}:top_{metric}",
                "retrieved_source": "dor_reports_lookup_index",
                "retrieval_score": 1.0,
                "used_model": False,
                "model": "deterministic_public_lookup",
                "source_note": "Computed by ranking rows in the DOR quarterly tax-credit report.",
                "citations": self.citation(top, matched_rows=len(candidates)),
                "source_rows": [{"source_file": top["source_file"], "values": top}],
            }
        total_requested = re.search(r"\b(total|overall|all\s+tax\s+credits?|statewide)\b", question.lower())
        row = None
        if total_requested:
            row = next((item for item in period_rows if item.get("is_total")), None)
        if row is None and matches:
            row = matches[0]
        if row is None:
            return None
        if row.get(metric) is None:
            return {
                "question": question,
                "answer": (
                    f"The DOR {format_fiscal_year(fiscal_year)} Q{quarter} quarterly tax-credit report includes "
                    f"{row['credit_type']}, but the extracted row does not expose a reliable {metric_label} value. "
                    "Try asking for redemptions, or ask about a tax-credit row with a full authorized/issued layout."
                ),
                "retrieved_context_id": f"dor_reports_index:quarterly_tax_credit:{fiscal_year}_q{quarter}:{normalize_key(str(row.get('credit_type')))}:metric_missing",
                "retrieved_source": "dor_reports_lookup_index",
                "retrieval_score": 1.0,
                "used_model": False,
                "model": "deterministic_public_lookup",
                "source_note": "The source row has a shorter table layout, so this metric is not asserted.",
                "citations": self.citation(row),
                "source_rows": [{"source_file": row["source_file"], "values": row}],
            }
        code_text = f" ({row['credit_code']})" if row.get("credit_code") and not row.get("is_total") else ""
        return {
            "question": question,
            "answer": (
                f"The DOR {format_fiscal_year(fiscal_year)} Q{quarter} quarterly tax-credit report lists "
                f"{row['credit_type']}{code_text} {metric_label} at {value_label(row[metric])}. "
                f"Reporting agency: {row.get('reporting_agency') or 'not listed'}."
            ),
            "retrieved_context_id": f"dor_reports_index:quarterly_tax_credit:{fiscal_year}_q{quarter}:{normalize_key(str(row.get('credit_type')))}:{metric}",
            "retrieved_source": "dor_reports_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the DOR quarterly tax-credit report.",
            "citations": self.citation(row),
            "source_rows": [{"source_file": row["source_file"], "values": row}],
        }

    def business_locations_answer(self, question: str) -> dict[str, Any] | None:
        county_rows = self.records_of_type("business_locations_county")
        city_rows = self.records_of_type("business_locations_city")
        if not county_rows:
            return None
        if asks_for_top(question):
            top = max(county_rows, key=lambda row: int(row["location_count"]))
            return {
                "question": question,
                "answer": (
                    f"In the indexed DOR 2016 business-location report, {top['county']} has the highest county location count: "
                    f"{top['location_count']:,} locations across {top['business_count']:,} businesses."
                ),
                "retrieved_context_id": "dor_reports_index:business_locations:top_county",
                "retrieved_source": "dor_reports_lookup_index",
                "retrieval_score": 1.0,
                "used_model": False,
                "model": "deterministic_public_lookup",
                "source_note": "Computed by ranking county totals in the DOR business-location report.",
                "citations": self.citation(top, matched_rows=len(county_rows)),
                "source_rows": [{"source_file": top["source_file"], "values": top}],
            }
        counties = county_matches(county_rows, question)
        if not counties:
            return None
        county = counties[0]
        question_key = normalize_key(question)
        city_match = next(
            (
                row
                for row in city_rows
                if row["county"] == county and normalize_key(row["city"]) in question_key
            ),
            None,
        )
        if city_match is not None:
            return {
                "question": question,
                "answer": (
                    f"In the indexed DOR 2016 business-location report, {city_match['city']} in {county} has "
                    f"{city_match['business_count']:,} business count and {city_match['location_count']:,} location count."
                ),
                "retrieved_context_id": f"dor_reports_index:business_locations:{normalize_key(county)}:{normalize_key(city_match['city'])}",
                "retrieved_source": "dor_reports_lookup_index",
                "retrieval_score": 1.0,
                "used_model": False,
                "model": "deterministic_public_lookup",
                "source_note": "Computed from the DOR business-location city/county report.",
                "citations": self.citation(city_match),
                "source_rows": [{"source_file": city_match["source_file"], "values": city_match}],
            }
        row = next((item for item in county_rows if item["county"] == county), None)
        if row is None:
            return None
        return {
            "question": question,
            "answer": (
                f"In the indexed DOR 2016 business-location report, {county} totals "
                f"{row['business_count']:,} businesses and {row['location_count']:,} locations."
            ),
            "retrieved_context_id": f"dor_reports_index:business_locations:{normalize_key(county)}",
            "retrieved_source": "dor_reports_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the DOR business-location county report.",
            "citations": self.citation(row),
            "source_rows": [{"source_file": row["source_file"], "values": row}],
        }

    def vehicle_answer(self, question: str) -> dict[str, Any] | None:
        rows = self.records_of_type("vehicle_county_kind")
        if not rows:
            return None
        kind = find_vehicle_kind(question)
        metric = "titled_count" if asks_for_titled(question) else "registered_count"
        candidates = [row for row in rows if row.get("vehicle_kind") == kind]
        if not candidates and kind != "COUNTY TOTALS":
            return None
        if asks_for_top(question):
            pool = candidates or [row for row in rows if row.get("vehicle_kind") == "COUNTY TOTALS"]
            top = max(pool, key=lambda row: int(row[metric]))
            label = "titled" if metric == "titled_count" else "registered"
            return {
                "question": question,
                "answer": (
                    f"In the indexed DOR vehicle-count file as of {top.get('as_of_date')}, {top['county']} has the highest "
                    f"{label} {top['vehicle_kind'].lower()} count: {top[metric]:,}."
                ),
                "retrieved_context_id": f"dor_reports_index:vehicles:{normalize_key(kind)}:top_{metric}",
                "retrieved_source": "dor_reports_lookup_index",
                "retrieval_score": 1.0,
                "used_model": False,
                "model": "deterministic_public_lookup",
                "source_note": "Computed by ranking county rows in the DOR vehicle-count file.",
                "citations": self.citation(top, matched_rows=len(pool)),
                "source_rows": [{"source_file": top["source_file"], "values": top}],
            }
        counties = county_matches(rows, question)
        if not counties:
            return None
        row = next((item for item in rows if item["county"] == counties[0] and item["vehicle_kind"] == kind), None)
        if row is None:
            return None
        label = "titled" if metric == "titled_count" else "registered"
        return {
            "question": question,
            "answer": (
                f"The indexed DOR vehicle-count file lists {row[metric]:,} {label} {row['vehicle_kind'].lower()} "
                f"for {row['county']} as of {row.get('as_of_date')}."
            ),
            "retrieved_context_id": f"dor_reports_index:vehicles:{normalize_key(row['county'])}:{normalize_key(row['vehicle_kind'])}:{metric}",
            "retrieved_source": "dor_reports_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the DOR vehicle-count county file.",
            "citations": self.citation(row),
            "source_rows": [{"source_file": row["source_file"], "values": row}],
        }

    def driver_answer(self, question: str) -> dict[str, Any] | None:
        total_rows = self.records_of_type("driver_county_total")
        age_rows = self.records_of_type("driver_county_age_band")
        if not total_rows:
            return None
        counties = county_matches(total_rows, question)
        if asks_for_top(question):
            top = max(total_rows, key=lambda row: int(row["driver_count"]))
            return {
                "question": question,
                "answer": (
                    f"In the indexed DOR licensed-driver file as of {top.get('as_of_date')}, {top['county']} has the highest "
                    f"county driver total: {top['driver_count']:,}."
                ),
                "retrieved_context_id": "dor_reports_index:drivers:top_county",
                "retrieved_source": "dor_reports_lookup_index",
                "retrieval_score": 1.0,
                "used_model": False,
                "model": "deterministic_public_lookup",
                "source_note": "Computed by ranking county totals in the DOR driver-count file.",
                "citations": self.citation(top, matched_rows=len(total_rows)),
                "source_rows": [{"source_file": top["source_file"], "values": top}],
            }
        if not counties:
            return None
        age_match = re.search(r"\b(\d{1,3})\s*(?:-|to)\s*(\d{1,3})\b", question.lower())
        if age_match:
            age_band = f"{int(age_match.group(1))} - {int(age_match.group(2))}"
            row = next(
                (
                    item
                    for item in age_rows
                    if item["county"] == counties[0] and item["age_band"].replace("-15", "-15") == age_band
                ),
                None,
            )
            if row is not None:
                return {
                    "question": question,
                    "answer": (
                        f"The indexed DOR licensed-driver file lists {row['driver_count']:,} drivers in age band "
                        f"{row['age_band']} for {row['county']} as of {row.get('as_of_date')}."
                    ),
                    "retrieved_context_id": f"dor_reports_index:drivers:{normalize_key(row['county'])}:{normalize_key(row['age_band'])}",
                    "retrieved_source": "dor_reports_lookup_index",
                    "retrieval_score": 1.0,
                    "used_model": False,
                    "model": "deterministic_public_lookup",
                    "source_note": "Computed by summing age rows in the DOR driver-count county file.",
                    "citations": self.citation(row),
                    "source_rows": [{"source_file": row["source_file"], "values": row}],
                }
        row = next((item for item in total_rows if item["county"] == counties[0]), None)
        if row is None:
            return None
        return {
            "question": question,
            "answer": (
                f"The indexed DOR licensed-driver file lists {row['driver_count']:,} total drivers for {row['county']} "
                f"as of {row.get('as_of_date')}."
            ),
            "retrieved_context_id": f"dor_reports_index:drivers:{normalize_key(row['county'])}",
            "retrieved_source": "dor_reports_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the DOR driver-count county report.",
            "citations": self.citation(row),
            "source_rows": [{"source_file": row["source_file"], "values": row}],
        }

    def dealer_answer(self, question: str) -> dict[str, Any] | None:
        rows = self.records_of_type("dealer_county_type")
        total_rows = self.records_of_type("dealer_county_total")
        if not rows:
            return None
        dealer_type = find_dealer_type(question)
        candidates = total_rows if dealer_type == "ALL" else [row for row in rows if row["dealer_type"] == dealer_type]
        if not candidates:
            return None
        if asks_for_top(question):
            top = max(candidates, key=lambda row: int(row["dealer_count"]))
            label = "all dealer types" if dealer_type == "ALL" else top["dealer_type"]
            return {
                "question": question,
                "answer": (
                    f"In the indexed DOR dealer file, {top['county']} has the highest {label} count: "
                    f"{top['dealer_count']:,} dealers. The index stores aggregate counts only."
                ),
                "retrieved_context_id": f"dor_reports_index:dealers:{normalize_key(dealer_type)}:top_county",
                "retrieved_source": "dor_reports_lookup_index",
                "retrieval_score": 1.0,
                "used_model": False,
                "model": "deterministic_public_lookup",
                "source_note": "Computed by aggregating public DOR dealer rows by county and dealer type.",
                "citations": self.citation(top, matched_rows=len(candidates)),
                "source_rows": [{"source_file": top["source_file"], "values": top}],
            }
        counties = county_matches(candidates, question)
        if not counties:
            return None
        row = next((item for item in candidates if item["county"] == counties[0]), None)
        if row is None:
            return None
        label = "all dealer types" if dealer_type == "ALL" else row["dealer_type"]
        return {
            "question": question,
            "answer": (
                f"The indexed DOR dealer file has {row['dealer_count']:,} {label} dealer records for {row['county']}. "
                "This assistant returns aggregate dealer counts only, not addresses or phone numbers."
            ),
            "retrieved_context_id": f"dor_reports_index:dealers:{normalize_key(row['county'])}:{normalize_key(label)}",
            "retrieved_source": "dor_reports_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed by aggregating public DOR dealer rows by county and dealer type.",
            "citations": self.citation(row),
            "source_rows": [{"source_file": row["source_file"], "values": row}],
        }

    def sic_answer(self, question: str) -> dict[str, Any] | None:
        county_rows = self.records_of_type("sic_county_total")
        state_rows = self.records_of_type("sic_state_total")
        if not county_rows and not state_rows:
            return None
        code_match = re.search(r"\b(\d{4})\b", question)
        q_tokens = question_tokens(question)
        counties = county_matches(county_rows, question)
        pool = county_rows if counties else state_rows
        if counties:
            pool = [row for row in county_rows if row["county"] == counties[0]]
        if code_match:
            row = next((item for item in pool if item["sic4"] == code_match.group(1)), None)
        else:
            ranked = sorted(
                (
                    (len(q_tokens & question_tokens(f"{row['sic4']} {row['sic_description']}")), row)
                    for row in pool
                ),
                key=lambda item: item[0],
                reverse=True,
            )
            row = ranked[0][1] if ranked and ranked[0][0] >= 1 else None
        if row is None:
            return None
        scope = f"{row['county']} " if row.get("county") else "statewide "
        return {
            "question": question,
            "answer": (
                f"The indexed DOR SIC report lists {row['total_locations']:,} total {scope}locations for "
                f"SIC {row['sic4']} ({row['sic_description']}); sales-tax locations: {row['sales_tax_locations']:,}, "
                f"use-tax locations: {row['use_tax_locations']:,}."
            ),
            "retrieved_context_id": f"dor_reports_index:sic:{normalize_key(scope)}:{row['sic4']}",
            "retrieved_source": "dor_reports_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the DOR SIC location report.",
            "citations": self.citation(row),
            "source_rows": [{"source_file": row["source_file"], "values": row}],
        }

    def answer(self, question: str) -> dict[str, Any] | None:
        if not self.available():
            return self.unavailable_answer(question)
        if is_summary_question(question):
            return self.summary_answer(question)
        if asks_for_quarterly_tax_credit_report(question):
            result = self.quarterly_tax_credit_answer(question)
            if result is not None:
                return result
        if asks_for_working_family_tax_credit(question):
            result = self.working_family_tax_credit_answer(question)
            if result is not None:
                return result
        if asks_for_food_tax(question):
            result = self.food_tax_answer(question)
            if result is not None:
                return result
        if asks_for_taxable_sales(question):
            result = self.taxable_sales_answer(question)
            if result is not None:
                return result
        if asks_for_business_locations(question):
            result = self.business_locations_answer(question)
            if result is not None:
                return result
        if asks_for_dealers(question):
            result = self.dealer_answer(question)
            if result is not None:
                return result
        if asks_for_vehicles(question):
            result = self.vehicle_answer(question)
            if result is not None:
                return result
        if asks_for_drivers(question):
            result = self.driver_answer(question)
            if result is not None:
                return result
        if asks_for_sic(question):
            result = self.sic_answer(question)
            if result is not None:
                return result
        return self.missing_answer(question)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--delay-seconds", type=float, default=0.05)
    args = parser.parse_args()
    payload = build_dor_reports_index(force=args.force, delay_seconds=args.delay_seconds)
    print(json.dumps({key: value for key, value in payload.items() if key != "records"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
