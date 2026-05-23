"""Build and query a local public MAP lookup index."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sqlite3
import time
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MAP_ALL_DIR = PROJECT_ROOT / "data" / "raw_public" / "map_all"
INDEX_PATH = PROJECT_ROOT / "data" / "raw_public" / "map_public_lookup.sqlite"
REPORT_PATH = PROJECT_ROOT / "reports" / "map_public_index_report.json"

CATEGORY_LABELS = {
    "bonds": "Bonds",
    "budget_restrictions": "Budget restrictions",
    "check_cancellations": "Check cancellations",
    "employees": "Employee pay",
    "expenditures": "Expenditures",
    "federal_grants": "Federal grants",
    "stimulus": "Stimulus",
    "tax_credits": "Tax credits",
}

KIND_LABELS = {
    "bond_subdivision_face": "bond face amount",
    "bond_subdivision_outstanding": "bond outstanding balance",
    "budget_released_agency": "budget released amount",
    "budget_restricted_agency": "budget restricted amount",
    "expenditure_agency": "expenditure agency total",
    "expenditure_category": "expenditure category total",
    "expenditure_vendor": "expenditure vendor total",
    "federal_grant_agency": "federal grant agency total",
    "federal_grant_federal_agency": "federal grant source-agency total",
    "stimulus_agency": "stimulus agency total",
    "stimulus_vendor": "stimulus vendor total",
    "tax_credit_category": "tax credit category total",
    "tax_credit_customer": "tax credit customer total",
    "tax_credit_program": "tax credit program total",
}

KIND_CATEGORIES = {
    "bond_subdivision_face": "bonds",
    "bond_subdivision_outstanding": "bonds",
    "budget_released_agency": "budget_restrictions",
    "budget_restricted_agency": "budget_restrictions",
    "expenditure_agency": "expenditures",
    "expenditure_category": "expenditures",
    "expenditure_vendor": "expenditures",
    "federal_grant_agency": "federal_grants",
    "federal_grant_federal_agency": "federal_grants",
    "stimulus_agency": "stimulus",
    "stimulus_vendor": "stimulus",
    "tax_credit_category": "tax_credits",
    "tax_credit_customer": "tax_credits",
    "tax_credit_program": "tax_credits",
}


def normalize_public_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Z0-9& ]+", " ", value.upper())
    return re.sub(r"\s+", " ", cleaned).strip()


ENTITY_STOPWORDS = {
    "AMOUNT",
    "AGENCY",
    "AGENCIES",
    "ANSWER",
    "CALENDAR",
    "CO",
    "COMPANY",
    "CORP",
    "CORPORATION",
    "CREDIT",
    "DATA",
    "DID",
    "EXPENDITURE",
    "EXPENDITURES",
    "FEDERAL",
    "FILE",
    "FOR",
    "FROM",
    "GRANT",
    "GROSS",
    "HOW",
    "INDEXED",
    "ISSUED",
    "LIST",
    "LLC",
    "LTD",
    "MAP",
    "MONEY",
    "MUCH",
    "PAID",
    "PAY",
    "PAYMENT",
    "PAYMENTS",
    "RECEIVE",
    "RECEIVED",
    "SALARY",
    "TAX",
    "THE",
    "TOTAL",
    "TOP",
    "VENDOR",
    "VENDORS",
    "WHAT",
    "WAS",
    "WERE",
    "YEAR",
    "YTD",
}

PLACEHOLDER_NAMES = {
    "",
    "N A",
    "NA",
    "N/A",
    "NOT APPLICABLE",
    "NOT AVAILABLE",
    "NOT PROVIDED",
    "NULL",
    "UNKNOWN",
}


def name_tokens(value: str) -> set[str]:
    return {
        token
        for token in normalize_public_name(value).split()
        if len(token) >= 3 and token not in ENTITY_STOPWORDS and not re.fullmatch(r"20\d{2}", token)
    }


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


def format_money(value: Decimal | float | int) -> str:
    amount = Decimal(str(value)).quantize(Decimal("0.01"))
    return f"${amount:,.2f}"


def rows_from_pipe_file(path: Path) -> Iterable[dict[str, str]]:
    with path.open("r", encoding="iso-8859-1", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="|")
        for row in reader:
            if not row:
                continue
            yield {str(key).strip(): str(value).strip() for key, value in row.items() if key is not None}


def year_from_path(path: Path) -> int | None:
    match = re.search(r"_(\d{4})(?:\.|$)", path.name)
    if match:
        return int(match.group(1))
    return None


def parse_year(value: str | None, fallback: int | None = None) -> int | None:
    if value:
        match = re.search(r"\b(20\d{2})\b", str(value))
        if match:
            return int(match.group(1))
    return fallback


def years_in_question(question: str) -> list[int]:
    years = [int(match) for match in re.findall(r"\b((?:19|20)\d{2})\b", question)]
    lowered = question.lower().replace("-", " ")
    word_years = {
        "twenty twenty one": 2021,
        "twenty twenty two": 2022,
        "twenty twenty three": 2023,
        "twenty twenty four": 2024,
        "twenty twenty five": 2025,
        "twenty twenty six": 2026,
        "twenty twenty": 2020,
    }
    for text, year in word_years.items():
        if text in lowered and year not in years:
            years.append(year)
    return years


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        drop table if exists file_summary;
        drop table if exists public_amount_lookup;
        drop table if exists employee_lookup;
        drop table if exists expenditure_agency_vendor;

        create table file_summary (
            category text not null,
            file_name text not null,
            row_count integer not null,
            columns_json text not null,
            bytes integer not null,
            primary key (category, file_name)
        );

        create table public_amount_lookup (
            kind text not null,
            year integer,
            name_norm text not null,
            display_name text not null,
            amount real not null,
            row_count integer not null,
            source_category text not null,
            primary key (kind, year, name_norm)
        );

        create table employee_lookup (
            calendar_year integer not null,
            employee_norm text not null,
            employee_name text not null,
            agency_name text not null,
            position_title text not null,
            ytd_gross_pay real not null,
            row_count integer not null,
            primary key (calendar_year, employee_norm)
        );

        create table expenditure_agency_vendor (
            year integer not null,
            agency_norm text not null,
            agency_name text not null,
            vendor_norm text not null,
            vendor_name text not null,
            amount real not null,
            row_count integer not null,
            primary key (year, agency_norm, vendor_norm)
        );

        create index idx_amount_kind_year on public_amount_lookup(kind, year);
        create index idx_amount_name on public_amount_lookup(kind, name_norm);
        create index idx_employee_year on employee_lookup(calendar_year);
        create index idx_employee_name on employee_lookup(employee_norm);
        create index idx_exp_agency_vendor_year_agency on expenditure_agency_vendor(year, agency_norm);
        create index idx_exp_agency_vendor_vendor on expenditure_agency_vendor(vendor_norm);
        """
    )


@dataclass
class AmountAggregate:
    display_name: str
    amount: Decimal = Decimal("0")
    row_count: int = 0


@dataclass
class EmployeeAggregate:
    employee_name: str
    agency_name: str
    position_title: str
    ytd_gross_pay: Decimal = Decimal("0")
    row_count: int = 0


@dataclass
class AgencyVendorAggregate:
    agency_name: str
    vendor_name: str
    amount: Decimal = Decimal("0")
    row_count: int = 0


def add_amount(
    data: dict[tuple[str, int | None, str], AmountAggregate],
    kind: str,
    year: int | None,
    display_name: str,
    amount: Decimal,
) -> None:
    normalized = normalize_public_name(display_name)
    if not normalized or normalized in PLACEHOLDER_NAMES:
        return
    key = (kind, year, normalized)
    aggregate = data.setdefault(key, AmountAggregate(display_name=display_name))
    aggregate.amount += amount
    aggregate.row_count += 1


def build_index(index_path: Path = INDEX_PATH) -> dict[str, Any]:
    start = time.perf_counter()
    if not MAP_ALL_DIR.exists():
        raise FileNotFoundError(f"Missing MAP all-files directory: {MAP_ALL_DIR}")

    index_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(index_path)
    create_schema(conn)

    amount_data: dict[tuple[str, int | None, str], AmountAggregate] = {}
    employee_data: dict[tuple[int, str], EmployeeAggregate] = {}
    agency_vendor_data: dict[tuple[int, str, str], AgencyVendorAggregate] = {}
    file_summaries: list[dict[str, Any]] = []
    skipped_files: list[str] = []

    for path in sorted(MAP_ALL_DIR.rglob("*")):
        if not path.is_file():
            continue
        category = path.parent.name
        if path.suffix.lower() != ".txt":
            skipped_files.append(str(path.relative_to(PROJECT_ROOT)))
            continue
        if category == "tax_credits" and "current" in path.stem.lower():
            skipped_files.append(str(path.relative_to(PROJECT_ROOT)))
            continue

        row_count = 0
        columns: list[str] = []
        for row in rows_from_pipe_file(path):
            if not columns:
                columns = list(row.keys())
            row_count += 1
            if category == "expenditures":
                year = parse_year(row.get("Fiscal Year"), year_from_path(path))
                if year is None:
                    continue
                amount = parse_decimal(row.get("Payments Total"))
                vendor_name = row.get("Vendor Name", "")
                agency_name = row.get("Agency Name", "")
                add_amount(amount_data, "expenditure_vendor", year, vendor_name, amount)
                add_amount(amount_data, "expenditure_agency", year, agency_name, amount)
                add_amount(amount_data, "expenditure_category", year, row.get("Category Description", ""), amount)
                agency_norm = normalize_public_name(agency_name)
                vendor_norm = normalize_public_name(vendor_name)
                if agency_norm and vendor_norm:
                    key = (year, agency_norm, vendor_norm)
                    aggregate = agency_vendor_data.setdefault(
                        key,
                        AgencyVendorAggregate(agency_name=agency_name, vendor_name=vendor_name),
                    )
                    aggregate.amount += amount
                    aggregate.row_count += 1
            elif category == "employees":
                year = parse_year(row.get("Calendar Year"), year_from_path(path))
                if year is None:
                    continue
                employee_name = row.get("Employee Name", "")
                normalized = normalize_public_name(employee_name)
                if not normalized:
                    continue
                key = (year, normalized)
                aggregate = employee_data.setdefault(
                    key,
                    EmployeeAggregate(
                        employee_name=employee_name,
                        agency_name=row.get("Agency Name", ""),
                        position_title=row.get("Position Title", ""),
                    ),
                )
                aggregate.ytd_gross_pay += parse_decimal(row.get("YTD Gross Pay"))
                aggregate.row_count += 1
            elif category == "tax_credits":
                year = parse_year(row.get("Year Application Approved"), year_from_path(path))
                if year is None:
                    continue
                amount = parse_decimal(row.get("Issued Amount"))
                add_amount(amount_data, "tax_credit_customer", year, row.get("Customer Name", ""), amount)
                add_amount(amount_data, "tax_credit_program", year, row.get("Program Name", ""), amount)
                add_amount(amount_data, "tax_credit_category", year, row.get("Tax Credit Category Description", ""), amount)
            elif category == "federal_grants":
                year = parse_year(row.get("Fiscal Year"), year_from_path(path))
                if year is None:
                    continue
                amount = parse_decimal(row.get("Received Amount"))
                add_amount(amount_data, "federal_grant_agency", year, row.get("Agency Name", ""), amount)
                add_amount(amount_data, "federal_grant_federal_agency", year, row.get("Federal Agency Name", ""), amount)
            elif category == "budget_restrictions":
                year = parse_year(row.get("Budget Fiscal Year"), year_from_path(path))
                if year is None:
                    continue
                add_amount(amount_data, "budget_restricted_agency", year, row.get("Agency Name", ""), parse_decimal(row.get("Restricted Amount")))
                add_amount(amount_data, "budget_released_agency", year, row.get("Agency Name", ""), parse_decimal(row.get("Released Amount")))
            elif category == "bonds":
                add_amount(amount_data, "bond_subdivision_face", None, row.get("Political Subdivision Name", ""), parse_decimal(row.get("Face Amount")))
                add_amount(amount_data, "bond_subdivision_outstanding", None, row.get("Political Subdivision Name", ""), parse_decimal(row.get("Outstanding Balance")))
            elif category == "stimulus":
                amount = parse_decimal(row.get("Payments Total") or row.get("Amount"))
                add_amount(amount_data, "stimulus_vendor", None, row.get("Vendor Name", ""), amount)
                add_amount(amount_data, "stimulus_agency", None, row.get("Agency Name", ""), amount)

        file_summaries.append(
            {
                "category": category,
                "file_name": path.name,
                "row_count": row_count,
                "columns": columns,
                "bytes": path.stat().st_size,
            }
        )

    conn.executemany(
        """
        insert into file_summary (category, file_name, row_count, columns_json, bytes)
        values (?, ?, ?, ?, ?)
        """,
        [
            (
                summary["category"],
                summary["file_name"],
                summary["row_count"],
                json.dumps(summary["columns"]),
                summary["bytes"],
            )
            for summary in file_summaries
        ],
    )
    conn.executemany(
        """
        insert into public_amount_lookup
        (kind, year, name_norm, display_name, amount, row_count, source_category)
        values (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                kind,
                year,
                name_norm,
                aggregate.display_name,
                float(aggregate.amount),
                aggregate.row_count,
                kind.split("_", 1)[0],
            )
            for (kind, year, name_norm), aggregate in amount_data.items()
        ],
    )
    conn.executemany(
        """
        insert into employee_lookup
        (calendar_year, employee_norm, employee_name, agency_name, position_title, ytd_gross_pay, row_count)
        values (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                year,
                employee_norm,
                aggregate.employee_name,
                aggregate.agency_name,
                aggregate.position_title,
                float(aggregate.ytd_gross_pay),
                aggregate.row_count,
            )
            for (year, employee_norm), aggregate in employee_data.items()
        ],
    )
    conn.executemany(
        """
        insert into expenditure_agency_vendor
        (year, agency_norm, agency_name, vendor_norm, vendor_name, amount, row_count)
        values (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                year,
                agency_norm,
                aggregate.agency_name,
                vendor_norm,
                aggregate.vendor_name,
                float(aggregate.amount),
                aggregate.row_count,
            )
            for (year, agency_norm, vendor_norm), aggregate in agency_vendor_data.items()
        ],
    )
    conn.commit()

    report = {
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "index_path": str(index_path.relative_to(PROJECT_ROOT)),
        "index_bytes": index_path.stat().st_size,
        "file_count": len(file_summaries),
        "skipped_non_text_files": skipped_files,
        "file_rows_total": sum(summary["row_count"] for summary in file_summaries),
        "amount_lookup_rows": len(amount_data),
        "employee_lookup_rows": len(employee_data),
        "agency_vendor_lookup_rows": len(agency_vendor_data),
        "categories": {},
    }
    category_totals: defaultdict[str, dict[str, Any]] = defaultdict(lambda: {"files": 0, "rows": 0, "bytes": 0})
    for summary in file_summaries:
        category_totals[summary["category"]]["files"] += 1
        category_totals[summary["category"]]["rows"] += summary["row_count"]
        category_totals[summary["category"]]["bytes"] += summary["bytes"]
    report["categories"] = dict(category_totals)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    conn.close()
    return report


class MapPublicIndex:
    def __init__(self, index_path: Path = INDEX_PATH) -> None:
        self.index_path = index_path

    def available(self) -> bool:
        return self.index_path.exists() and self.index_path.stat().st_size > 0

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.index_path)
        conn.row_factory = sqlite3.Row
        return conn

    def snapshot(self) -> dict[str, Any]:
        if not self.available():
            return {"available": False, "schema_version": "map_public_lookup_v2"}
        if REPORT_PATH.exists():
            payload = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        else:
            payload = {"categories": self.summary()}
        stable = {
            "schema_version": "map_public_lookup_v2",
            "index_bytes": self.index_path.stat().st_size,
            "file_count": payload.get("file_count"),
            "file_rows_total": payload.get("file_rows_total"),
            "amount_lookup_rows": payload.get("amount_lookup_rows"),
            "employee_lookup_rows": payload.get("employee_lookup_rows"),
            "agency_vendor_lookup_rows": payload.get("agency_vendor_lookup_rows"),
            "categories": payload.get("categories"),
        }
        snapshot_id = hashlib.sha256(json.dumps(stable, sort_keys=True).encode("utf-8")).hexdigest()[:16]
        return {
            "available": True,
            "schema_version": stable["schema_version"],
            "snapshot_id": snapshot_id,
            "index_path": str(self.index_path.relative_to(PROJECT_ROOT)),
            "index_bytes": stable["index_bytes"],
            "file_count": stable["file_count"],
            "file_rows_total": stable["file_rows_total"],
            "amount_lookup_rows": stable["amount_lookup_rows"],
            "employee_lookup_rows": stable["employee_lookup_rows"],
            "agency_vendor_lookup_rows": stable["agency_vendor_lookup_rows"],
        }

    def summary(self) -> dict[str, Any]:
        if not self.available():
            return {}
        with self.connect() as conn:
            rows = conn.execute(
                """
                select category, count(*) as file_count, sum(row_count) as row_count, sum(bytes) as bytes
                from file_summary
                group by category
                """
            ).fetchall()
        return {
            row["category"]: {
                "label": CATEGORY_LABELS.get(row["category"], row["category"]),
                "file_count": row["file_count"],
                "row_count": row["row_count"],
                "bytes": row["bytes"],
            }
            for row in rows
        }

    def coverage(self) -> dict[str, Any]:
        if not self.available():
            return {}
        with self.connect() as conn:
            categories = conn.execute(
                """
                select category, count(*) as file_count, sum(row_count) as row_count, sum(bytes) as bytes
                from file_summary
                group by category
                order by category
                """
            ).fetchall()
            amount_kinds = conn.execute(
                """
                select kind, min(year) as min_year, max(year) as max_year,
                       count(*) as entity_count, sum(row_count) as source_rows
                from public_amount_lookup
                group by kind
                order by kind
                """
            ).fetchall()
            employee = conn.execute(
                """
                select min(calendar_year) as min_year, max(calendar_year) as max_year,
                       count(*) as entity_count, sum(row_count) as source_rows
                from employee_lookup
                """
            ).fetchone()
        return {
            "categories": [
                {
                    "category": row["category"],
                    "label": CATEGORY_LABELS.get(row["category"], row["category"]),
                    "file_count": row["file_count"],
                    "row_count": row["row_count"],
                    "bytes": row["bytes"],
                }
                for row in categories
            ],
            "amount_kinds": [
                {
                    "kind": row["kind"],
                    "label": KIND_LABELS.get(row["kind"], row["kind"]),
                    "min_year": row["min_year"],
                    "max_year": row["max_year"],
                    "entity_count": row["entity_count"],
                    "source_rows": row["source_rows"],
                }
                for row in amount_kinds
            ],
            "employee_lookup": dict(employee) if employee else {},
        }

    def source_files(self, category: str, year: int | None = None, limit: int = 8) -> list[dict[str, Any]]:
        if not self.available():
            return []
        with self.connect() as conn:
            rows = conn.execute(
                """
                select category, file_name, row_count, bytes
                from file_summary
                where category = ?
                order by file_name
                """,
                [category],
            ).fetchall()
        if year is not None:
            year_text = str(year)
            rows = [row for row in rows if year_text in row["file_name"]]
        return [
            {
                "category": row["category"],
                "category_label": CATEGORY_LABELS.get(row["category"], row["category"]),
                "file_name": row["file_name"],
                "row_count": row["row_count"],
                "bytes": row["bytes"],
            }
            for row in rows[:limit]
        ]

    def citation_for_kind(
        self,
        kind: str,
        year: int | None = None,
        lookup_table: str = "public_amount_lookup",
        entity_rows: int | None = None,
        year_range: str | None = None,
    ) -> dict[str, Any]:
        category = KIND_CATEGORIES.get(kind, kind.split("_", 1)[0])
        files = self.source_files(category, year=year)
        if not files and year is not None:
            files = self.source_files(category, year=None)
        total_source_rows = sum(file["row_count"] or 0 for file in files)
        return {
            "dataset": "Missouri Accountability Portal",
            "category": CATEGORY_LABELS.get(category, category),
            "kind": KIND_LABELS.get(kind, kind),
            "lookup_table": lookup_table,
            "year": year,
            "year_range": year_range,
            "source_files": files,
            "source_file_count": len(files),
            "source_rows": total_source_rows,
            "matched_rows": entity_rows,
        }

    def citation_for_employee(self, year: int | None = None, matched_rows: int | None = None) -> dict[str, Any]:
        files = self.source_files("employees", year=year)
        return {
            "dataset": "Missouri Accountability Portal",
            "category": CATEGORY_LABELS["employees"],
            "kind": "employee pay/profile record",
            "lookup_table": "employee_lookup",
            "year": year,
            "year_range": None,
            "source_files": files,
            "source_file_count": len(files),
            "source_rows": sum(file["row_count"] or 0 for file in files),
            "matched_rows": matched_rows,
        }

    def citation_for_agency_vendor(self, year: int | None = None, matched_rows: int | None = None) -> dict[str, Any]:
        files = self.source_files("expenditures", year=year)
        return {
            "dataset": "Missouri Accountability Portal",
            "category": CATEGORY_LABELS["expenditures"],
            "kind": "agency-vendor expenditure aggregate",
            "lookup_table": "expenditure_agency_vendor",
            "year": year,
            "year_range": None,
            "source_files": files,
            "source_file_count": len(files),
            "source_rows": sum(file["row_count"] or 0 for file in files),
            "matched_rows": matched_rows,
        }

    def source_row_previews(
        self,
        category: str,
        year: int | None,
        filters: dict[str, str],
        display_columns: list[str],
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        previews: list[dict[str, Any]] = []
        normalized_filters = {column: normalize_public_name(value) for column, value in filters.items()}
        for source_file in self.source_files(category, year=year, limit=50):
            path = MAP_ALL_DIR / category / source_file["file_name"]
            if not path.exists():
                continue
            with path.open("r", encoding="iso-8859-1", errors="replace", newline="") as handle:
                reader = csv.DictReader(handle, delimiter="|")
                for source_row_number, row in enumerate(reader, start=2):
                    if not row:
                        continue
                    clean_row = {
                        str(column).strip(): str(value).strip()
                        for column, value in row.items()
                        if column is not None
                    }
                    if any(
                        normalize_public_name(str(clean_row.get(column, ""))) != expected
                        for column, expected in normalized_filters.items()
                    ):
                        continue
                    values = {
                        column: str(clean_row.get(column, "")).strip()
                        for column in display_columns
                        if column in clean_row and str(clean_row.get(column, "")).strip()
                    }
                    previews.append(
                        {
                            "source_file": source_file["file_name"],
                            "source_row_number": source_row_number,
                            "values": values,
                        }
                    )
                    if len(previews) >= limit:
                        return previews
        return previews

    def amount_source_rows(self, kind: str, year: int | None, name_norm: str, limit: int = 5) -> list[dict[str, Any]]:
        if year is None:
            return []
        configs = {
            "expenditure_agency": (
                "expenditures",
                {"Agency Name": name_norm},
                ["Fiscal Year", "Agency Name", "Category Description", "Detail Description", "Vendor Name", "Payments Total"],
            ),
            "expenditure_category": (
                "expenditures",
                {"Category Description": name_norm},
                ["Fiscal Year", "Agency Name", "Category Description", "Detail Description", "Vendor Name", "Payments Total"],
            ),
            "expenditure_vendor": (
                "expenditures",
                {"Vendor Name": name_norm},
                ["Fiscal Year", "Agency Name", "Category Description", "Detail Description", "Vendor Name", "Payments Total"],
            ),
            "tax_credit_customer": (
                "tax_credits",
                {"Customer Name": name_norm},
                ["Year Application Approved", "Tax Credit Category Description", "Program Name", "Customer Name", "Project Name", "Issued Amount"],
            ),
            "tax_credit_program": (
                "tax_credits",
                {"Program Name": name_norm},
                ["Year Application Approved", "Tax Credit Category Description", "Program Name", "Customer Name", "Project Name", "Issued Amount"],
            ),
            "tax_credit_category": (
                "tax_credits",
                {"Tax Credit Category Description": name_norm},
                ["Year Application Approved", "Tax Credit Category Description", "Program Name", "Customer Name", "Project Name", "Issued Amount"],
            ),
            "federal_grant_agency": (
                "federal_grants",
                {"Agency Name": name_norm},
                ["Fiscal Year", "Agency Name", "Federal Agency Name", "Grant Name", "Grant Purpose", "Received Amount"],
            ),
            "federal_grant_federal_agency": (
                "federal_grants",
                {"Federal Agency Name": name_norm},
                ["Fiscal Year", "Agency Name", "Federal Agency Name", "Grant Name", "Grant Purpose", "Received Amount"],
            ),
            "budget_restricted_agency": (
                "budget_restrictions",
                {"Agency Name": name_norm},
                ["Budget Fiscal Year", "Agency Name", "Fund Name", "Restricted Amount", "Released Amount"],
            ),
            "budget_released_agency": (
                "budget_restrictions",
                {"Agency Name": name_norm},
                ["Budget Fiscal Year", "Agency Name", "Fund Name", "Restricted Amount", "Released Amount"],
            ),
        }
        config = configs.get(kind)
        if config is None:
            return []
        category, filters, display_columns = config
        return self.source_row_previews(category, year, filters, display_columns, limit=limit)

    def agency_vendor_source_rows(
        self,
        year: int,
        agency_norm: str,
        vendor_norm: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        return self.source_row_previews(
            "expenditures",
            year,
            {"Agency Name": agency_norm, "Vendor Name": vendor_norm},
            ["Fiscal Year", "Agency Name", "Category Description", "Detail Description", "Vendor Name", "Payments Total"],
            limit=limit,
        )

    def employee_source_rows(self, year: int, employee_norm: str, limit: int = 5) -> list[dict[str, Any]]:
        return self.source_row_previews(
            "employees",
            year,
            {"Employee Name": employee_norm},
            ["Calendar Year", "Agency Name", "Position Title", "Employee Name", "YTD Gross Pay"],
            limit=limit,
        )

    def find_amount(self, question: str, kinds: list[str]) -> sqlite3.Row | None:
        if not self.available():
            return None
        years = years_in_question(question)
        question_tokens = name_tokens(question)
        if not question_tokens:
            return None
        with self.connect() as conn:
            if years:
                placeholders = ",".join("?" for _ in years)
                rows = conn.execute(
                    f"select * from public_amount_lookup where kind in ({','.join('?' for _ in kinds)}) "
                    f"and year in ({placeholders})",
                    [*kinds, *years],
                ).fetchall()
            else:
                rows = conn.execute(
                    f"select * from public_amount_lookup where kind in ({','.join('?' for _ in kinds)})",
                    kinds,
                ).fetchall()
        return best_token_match(question_tokens, rows, "name_norm")

    def find_amount_any_year(self, question: str, kinds: list[str]) -> sqlite3.Row | None:
        if not self.available():
            return None
        question_tokens = name_tokens(question)
        if not question_tokens:
            return None
        with self.connect() as conn:
            rows = conn.execute(
                f"select * from public_amount_lookup where kind in ({','.join('?' for _ in kinds)})",
                kinds,
            ).fetchall()
        return best_token_match(question_tokens, rows, "name_norm")

    def kind_year_span(self, kind: str) -> dict[str, Any] | None:
        if not self.available():
            return None
        with self.connect() as conn:
            row = conn.execute(
                """
                select kind, min(year) as min_year, max(year) as max_year, count(distinct year) as year_count
                from public_amount_lookup
                where kind = ?
                """,
                [kind],
            ).fetchone()
        return dict(row) if row and row["year_count"] else None

    def amount_year_rows(self, kind: str, name_norm: str) -> list[dict[str, Any]]:
        if not self.available():
            return []
        with self.connect() as conn:
            rows = conn.execute(
                """
                select kind, year, name_norm, display_name, amount, row_count
                from public_amount_lookup
                where kind = ? and name_norm = ? and year is not null
                order by amount desc
                """,
                [kind, name_norm],
            ).fetchall()
        return [
            {
                "kind": row["kind"],
                "year": row["year"],
                "name_norm": row["name_norm"],
                "display_name": row["display_name"],
                "amount": row["amount"],
                "amount_label": format_money(row["amount"]),
                "row_count": row["row_count"],
            }
            for row in rows
        ]

    def amount_suggestions(self, question: str, kinds: list[str], limit: int = 5) -> list[dict[str, Any]]:
        if not self.available():
            return []
        years = years_in_question(question)
        tokens = sorted(name_tokens(question))
        if not tokens:
            return []
        where_parts = [f"kind in ({','.join('?' for _ in kinds)})"]
        params: list[Any] = [*kinds]
        if years:
            where_parts.append(f"year in ({','.join('?' for _ in years)})")
            params.extend(years)
        like_tokens = tokens[:4]
        where_parts.append("(" + " or ".join("name_norm like ?" for _ in like_tokens) + ")")
        params.extend([f"%{token}%" for token in like_tokens])
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                select * from public_amount_lookup
                where {' and '.join(where_parts)}
                order by amount desc
                limit 250
                """,
                params,
            ).fetchall()
        ranked = rank_token_matches(set(tokens), rows, "name_norm")
        return [
            {
                "label": row["display_name"],
                "kind": row["kind"],
                "kind_label": KIND_LABELS.get(row["kind"], row["kind"]),
                "year": row["year"],
                "amount": format_money(row["amount"]),
                "row_count": row["row_count"],
                "score": score,
            }
            for score, row in ranked[:limit]
        ]

    def find_agency_vendor_payment(self, question: str) -> sqlite3.Row | None:
        if not self.available():
            return None
        years = years_in_question(question)
        tokens = name_tokens(question)
        if len(tokens) < 2:
            return None
        where_parts: list[str] = []
        params: list[Any] = []
        if years:
            where_parts.append(f"year in ({','.join('?' for _ in years)})")
            params.extend(years)
        token_list = sorted(tokens)[:6]
        where_parts.extend("(agency_norm like ? or vendor_norm like ?)" for _ in token_list)
        for token in token_list:
            params.extend([f"%{token}%", f"%{token}%"])
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                select * from expenditure_agency_vendor
                where {' and '.join(where_parts)}
                order by amount desc
                limit 2000
                """,
                params,
            ).fetchall()
            if not rows and token_list:
                loose_where = ["(" + " or ".join("(agency_norm like ? or vendor_norm like ?)" for _ in token_list) + ")"]
                loose_params: list[Any] = []
                if years:
                    loose_where.insert(0, f"year in ({','.join('?' for _ in years)})")
                    loose_params.extend(years)
                for token in token_list:
                    loose_params.extend([f"%{token}%", f"%{token}%"])
                rows = conn.execute(
                    f"""
                    select * from expenditure_agency_vendor
                    where {' and '.join(loose_where)}
                    order by amount desc
                    limit 2000
                    """,
                    loose_params,
                ).fetchall()
        ranked: list[tuple[int, sqlite3.Row]] = []
        for row in rows:
            agency_tokens = name_tokens(row["agency_norm"])
            vendor_tokens = name_tokens(row["vendor_norm"])
            agency_overlap = len(tokens & agency_tokens)
            vendor_overlap = len(tokens & vendor_tokens)
            required_vendor_overlap = min(2, len(vendor_tokens))
            if agency_overlap < 1 or vendor_overlap < required_vendor_overlap or agency_overlap + vendor_overlap < 2:
                continue
            score = agency_overlap * 100 + vendor_overlap * 100 - abs(len(tokens) - len(agency_tokens | vendor_tokens))
            ranked.append((score, row))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return ranked[0][1] if ranked else None

    def top_vendors_for_agency(self, question: str, limit: int = 5) -> list[dict[str, Any]]:
        agency = self.find_amount(question, ["expenditure_agency"])
        if agency is None:
            return []
        years = years_in_question(question)
        year = years[0] if years else None
        with self.connect() as conn:
            if year is None:
                rows = conn.execute(
                    """
                    select vendor_norm, vendor_name, min(year) as min_year, max(year) as max_year,
                           sum(amount) as amount, sum(row_count) as row_count
                    from expenditure_agency_vendor
                    where agency_norm = ?
                    group by vendor_norm, vendor_name
                    order by amount desc
                    limit ?
                    """,
                    [agency["name_norm"], limit],
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    select vendor_norm, vendor_name, year as min_year, year as max_year, amount, row_count
                    from expenditure_agency_vendor
                    where agency_norm = ? and year = ?
                    order by amount desc
                    limit ?
                    """,
                    [agency["name_norm"], year, limit],
                ).fetchall()
        return [
            {
                "agency": agency["display_name"],
                "label": row["vendor_name"],
                "min_year": row["min_year"],
                "max_year": row["max_year"],
                "amount": format_money(row["amount"]),
                "row_count": row["row_count"],
            }
            for row in rows
        ]

    def top_agencies_for_vendor(self, question: str, limit: int = 5) -> list[dict[str, Any]]:
        vendor = self.find_amount(question, ["expenditure_vendor"])
        if vendor is None:
            return []
        years = years_in_question(question)
        year = years[0] if years else None
        with self.connect() as conn:
            if year is None:
                rows = conn.execute(
                    """
                    select agency_norm, agency_name, min(year) as min_year, max(year) as max_year,
                           sum(amount) as amount, sum(row_count) as row_count
                    from expenditure_agency_vendor
                    where vendor_norm = ?
                    group by agency_norm, agency_name
                    order by amount desc
                    limit ?
                    """,
                    [vendor["name_norm"], limit],
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    select agency_norm, agency_name, year as min_year, year as max_year, amount, row_count
                    from expenditure_agency_vendor
                    where vendor_norm = ? and year = ?
                    order by amount desc
                    limit ?
                    """,
                    [vendor["name_norm"], year, limit],
                ).fetchall()
        return [
            {
                "vendor": vendor["display_name"],
                "label": row["agency_name"],
                "min_year": row["min_year"],
                "max_year": row["max_year"],
                "amount": format_money(row["amount"]),
                "row_count": row["row_count"],
            }
            for row in rows
        ]

    def top_amounts(self, kind: str, year: int | None = None, limit: int = 5) -> list[dict[str, Any]]:
        if not self.available():
            return []
        with self.connect() as conn:
            if year is None:
                rows = conn.execute(
                    """
                    select kind, name_norm, display_name, min(year) as min_year, max(year) as max_year,
                           sum(amount) as amount, sum(row_count) as row_count
                    from public_amount_lookup
                    where kind = ?
                    group by kind, name_norm, display_name
                    order by amount desc
                    limit ?
                    """,
                    [kind, limit],
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    select kind, year as min_year, year as max_year, name_norm, display_name, amount, row_count
                    from public_amount_lookup
                    where kind = ? and year = ?
                    order by amount desc
                    limit ?
                    """,
                    [kind, year, limit],
                ).fetchall()
        return [
            {
                "label": row["display_name"],
                "kind": row["kind"],
                "kind_label": KIND_LABELS.get(row["kind"], row["kind"]),
                "min_year": row["min_year"],
                "max_year": row["max_year"],
                "amount": format_money(row["amount"]),
                "row_count": row["row_count"],
            }
            for row in rows
        ]

    def aggregate_amount(self, kind: str, name_norm: str) -> dict[str, Any] | None:
        if not self.available():
            return None
        with self.connect() as conn:
            row = conn.execute(
                """
                select kind, name_norm, display_name, min(year) as min_year, max(year) as max_year,
                       sum(amount) as amount, sum(row_count) as row_count, count(*) as year_count
                from public_amount_lookup
                where kind = ? and name_norm = ?
                group by kind, name_norm, display_name
                """,
                [kind, name_norm],
            ).fetchone()
        return dict(row) if row else None

    def find_employee(self, question: str) -> sqlite3.Row | None:
        if not self.available():
            return None
        years = years_in_question(question)
        question_tokens = name_tokens(question)
        if not question_tokens:
            return None
        with self.connect() as conn:
            if years:
                placeholders = ",".join("?" for _ in years)
                rows = conn.execute(
                    f"select * from employee_lookup where calendar_year in ({placeholders})",
                    years,
                ).fetchall()
            else:
                latest = conn.execute("select max(calendar_year) as year from employee_lookup").fetchone()["year"]
                rows = conn.execute(
                    "select * from employee_lookup where calendar_year = ?",
                    [latest],
                ).fetchall()
        return best_token_match(question_tokens, rows, "employee_norm")

    def employee_suggestions(self, question: str, limit: int = 5) -> list[dict[str, Any]]:
        if not self.available():
            return []
        years = years_in_question(question)
        tokens = sorted(name_tokens(question))
        if not tokens:
            return []
        where_parts: list[str] = []
        params: list[Any] = []
        if years:
            where_parts.append(f"calendar_year in ({','.join('?' for _ in years)})")
            params.extend(years)
        like_tokens = tokens[:4]
        where_parts.append("(" + " or ".join("employee_norm like ?" for _ in like_tokens) + ")")
        params.extend([f"%{token}%" for token in like_tokens])
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                select * from employee_lookup
                where {' and '.join(where_parts)}
                order by calendar_year desc, ytd_gross_pay desc
                limit 250
                """,
                params,
            ).fetchall()
        ranked = rank_token_matches(set(tokens), rows, "employee_norm")
        return [
            {
                "label": row["employee_name"],
                "year": row["calendar_year"],
                "amount": format_money(row["ytd_gross_pay"]),
                "agency": row["agency_name"],
                "position": row["position_title"],
                "score": score,
            }
            for score, row in ranked[:limit]
        ]


def best_token_match(tokens: set[str], rows: list[sqlite3.Row], field: str) -> sqlite3.Row | None:
    ranked = rank_token_matches(tokens, rows, field)
    return ranked[0][1] if ranked else None


def rank_token_matches(tokens: set[str], rows: list[sqlite3.Row], field: str) -> list[tuple[int, sqlite3.Row]]:
    ranked: list[tuple[int, sqlite3.Row]] = []
    for row in rows:
        candidate_tokens = name_tokens(row[field])
        if not candidate_tokens:
            continue
        overlap = len(tokens & candidate_tokens)
        required_overlap = min(2, len(candidate_tokens))
        if overlap < required_overlap:
            continue
        score = overlap * 100 - abs(len(candidate_tokens) - len(tokens))
        ranked.append((score, row))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()
    if INDEX_PATH.exists() and not args.rebuild:
        print(json.dumps({"index_path": str(INDEX_PATH.relative_to(PROJECT_ROOT)), "exists": True}, indent=2))
        return
    print(json.dumps(build_index(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
