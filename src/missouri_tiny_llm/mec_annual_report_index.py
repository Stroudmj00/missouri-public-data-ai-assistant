"""Build and query Missouri Ethics Commission annual-report aggregates."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw_public" / "mec_annual_report"
INDEX_PATH = RAW_DIR / "mec_annual_report_index.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "mec_annual_report_index_report.json"
BASE_URL = "https://www.mec.mo.gov"
REPORT_URL_TEMPLATE = f"{BASE_URL}/AnnualReport/{{year}}"
SOURCE_NAME = "Missouri Ethics Commission electronic annual report aggregates"


@dataclass(frozen=True)
class MecAnnualPartial:
    key: str
    section: str
    metric_group: str
    endpoint: str
    anchor: str


PARTIALS: tuple[MecAnnualPartial, ...] = (
    MecAnnualPartial(
        "total_campaign_finance_activity",
        "Campaign Finance",
        "Total Campaign Finance Activity",
        "/AnnualReport/Home/TotalCampaignFinanceActivity",
        "TotalCampaignFinanceActivity",
    ),
    MecAnnualPartial(
        "registered_campaign_finance_committees",
        "Campaign Finance",
        "Registered Campaign Finance Committees",
        "/AnnualReport/Home/RegisteredCFCommittees",
        "RegisteredCampaignFinanceCommittees",
    ),
    MecAnnualPartial(
        "candidate_committees_by_election",
        "Campaign Finance",
        "Candidate Committees by Election",
        "/AnnualReport/Home/CandidateCommitteeByElection",
        "CandidateCommitteesbyElection",
    ),
    MecAnnualPartial(
        "campaign_committees_by_election",
        "Campaign Finance",
        "Campaign Committees by Election",
        "/AnnualReport/Home/CampaignCommitteeByElection",
        "CampaignCommitteesbyElection",
    ),
    MecAnnualPartial(
        "large_contributions_reported",
        "Campaign Finance",
        "Large Contributions Over $5,000",
        "/AnnualReport/Home/LargeContributionsReported",
        "LargeContributionsOver$5,000",
    ),
    MecAnnualPartial(
        "total_receipts_reported_state",
        "Campaign Finance",
        "Total Receipts Reported - State Candidates",
        "/AnnualReport/Home/TotalReceiptsReported",
        "TotalReceiptsReported",
    ),
    MecAnnualPartial(
        "total_receipts_reported_local",
        "Campaign Finance",
        "Total Receipts Reported - Local Candidates",
        "/AnnualReport/Home/TotalReceiptsReportedLocal",
        "TotalReceiptsReported-LocalCandidates",
    ),
    MecAnnualPartial(
        "registered_lobbyists",
        "Lobbying",
        "Registered Lobbyists",
        "/AnnualReport/Home/RegisteredLobbyists",
        "RegisteredLobbyists",
    ),
    MecAnnualPartial(
        "reported_lobbying_expenditures",
        "Lobbying",
        "Reported Expenditures by Official Type",
        "/AnnualReport/Home/ReportedExpenditures",
        "ReportedExpendituresbyOfficialType",
    ),
    MecAnnualPartial(
        "reported_lobbying_expenditures_group",
        "Lobbying",
        "Reported Expenditures by Group",
        "/AnnualReport/Home/ReportedExpendituresGroup",
        "ReportedExpendituresbyGroup",
    ),
    MecAnnualPartial(
        "subdivisions_subject_to_pfd",
        "Personal Financial Disclosure",
        "Subdivisions Subject to PFD Requirements",
        "/AnnualReport/Home/SubdivisionsSubjectToPFD",
        "SubdivisionsSubjecttoPFDRequirements",
    ),
    MecAnnualPartial(
        "annual_operating_budget",
        "Personal Financial Disclosure",
        "Annual Operating Budget",
        "/AnnualReport/Home/AnnualOperatingBudget",
        "AnnualOperatingBudget",
    ),
    MecAnnualPartial(
        "ordinances",
        "Personal Financial Disclosure",
        "Ordinances",
        "/AnnualReport/Home/Ordinances",
        "Ordinances",
    ),
)

GENERIC_TOKENS = {
    "ABOUT",
    "ACTIVITY",
    "AGGREGATE",
    "ANNUAL",
    "ANSWER",
    "ARE",
    "COMMISSION",
    "COUNT",
    "DATA",
    "ETHICS",
    "FOR",
    "FROM",
    "HOW",
    "INDEX",
    "INDEXED",
    "MEC",
    "MISSOURI",
    "REPORT",
    "REPORTS",
    "SHOW",
    "SOURCE",
    "THE",
    "TOTAL",
    "VALUE",
    "WHAT",
    "WHICH",
}

METRIC_GROUP_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Total Campaign Finance Activity",
        (
            r"\bcampaign\s+finance\s+activity\b",
            r"\btotal\s+(?:campaign\s+finance\s+)?(?:activity|receipts?|expenditures?|contributions?)\b",
            r"\bcampaign\s+finance\b.*\b(receipts?|expenditures?|contributions?|activity|total)\b",
        ),
    ),
    (
        "Registered Campaign Finance Committees",
        (
            r"\bregistered\s+campaign\s+finance\s+committees\b",
            r"\bregistered\s+committees\b",
            r"\bcampaign\s+finance\s+committees\b.*\b(count|how\s+many|registered|total)\b",
        ),
    ),
    (
        "Candidate Committees by Election",
        (
            r"\bcandidate\s+committees?\b.*\belection\b",
            r"\belection\s+dates?\b.*\bcandidate\s+committees?\b",
        ),
    ),
    (
        "Campaign Committees by Election",
        (
            r"\bcampaign\s+committees?\b.*\belection\b",
            r"\belection\s+dates?\b.*\bcampaign\s+committees?\b",
        ),
    ),
    (
        "Large Contributions Over $5,000",
        (
            r"\blarge\s+contributions?\b",
            r"\bcontributions?\s+over\s+\$?5,?000\b",
            r"\bover\s+\$?5,?000\b",
        ),
    ),
    (
        "Total Receipts Reported - State Candidates",
        (
            r"\bstate\s+(?:candidate\s+)?receipts?\b",
            r"\bstate\s+candidate\s+positions?\b.*\breceipts?\b",
            r"\bcandidate\s+positions?\b.*\b(state|receipts?)\b",
            r"\breceipts?\s+reported\b.*\b(state|statewide|governor|senator|representative|attorney|treasurer|auditor|secretary)\b",
            r"\b(state\s+senator|state\s+representative|governor|lieutenant\s+governor|attorney\s+general|secretary\s+of\s+state|state\s+auditor|state\s+treasurer)\b",
        ),
    ),
    (
        "Total Receipts Reported - Local Candidates",
        (
            r"\blocal\s+(?:candidate\s+)?receipts?\b",
            r"\breceipts?\s+reported\b.*\b(local|mayor|sheriff|county|council|alderperson|municipal)\b",
            r"\b(mayor|sheriff|county\s+executive|council\s+person|alderperson|municipal\s+judge)\b",
        ),
    ),
    (
        "Registered Lobbyists",
        (
            r"\bregistered\s+lobbyists?\b",
            r"\blobbyists?\b.*\b(count|how\s+many|registered|total)\b",
            r"\bexecutive\s+lobbyists?\b|\blegislative\s+lobbyists?\b|\bjudicial\s+lobbyists?\b",
        ),
    ),
    (
        "Reported Expenditures by Official Type",
        (
            r"\blobby(?:ing|ist)?\s+expenditures?\b",
            r"\breported\s+expenditures?\b.*\bofficial\b",
            r"\bspent\s+on\s+(?:official|staff|family)\b",
        ),
    ),
    (
        "Reported Expenditures by Group",
        (
            r"\breported\s+expenditures?\b.*\bgroup\b",
            r"\blobby(?:ing|ist)?\s+expenditures?\b.*\bgroup\b",
        ),
    ),
    (
        "Subdivisions Subject to PFD Requirements",
        (
            r"\bsubdivisions?\b.*\bpfd\b",
            r"\bpersonal\s+financial\s+disclosure\b.*\bsubdivisions?\b",
            r"\bpfd\b.*\b(school|city|village|county|district|subdivision)\b",
        ),
    ),
    (
        "Annual Operating Budget",
        (
            r"\bannual\s+operating\s+budget\b",
            r"\bover\s+\$?1\s+million\b|\bunder\s+\$?1\s+million\b",
            r"\boperating\s+budget\b.*\bpfd\b",
        ),
    ),
    (
        "Ordinances",
        (
            r"\bordinances?\b.*\bpfd\b",
            r"\bhas\s+ordinance\b|\bno\s+ordinance\b",
            r"\bconflict\s+of\s+interest\s+ordinance\b",
        ),
    ),
)


class TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._in_table = False
        self._in_row = False
        self._in_cell = False
        self._current_table: list[list[str]] = []
        self._current_row: list[str] = []
        self._current_cell: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if lowered == "table":
            self._in_table = True
            self._current_table = []
        elif self._in_table and lowered == "tr":
            self._in_row = True
            self._current_row = []
        elif self._in_table and self._in_row and lowered in {"td", "th"}:
            self._in_cell = True
            self._current_cell = []

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if self._in_table and self._in_row and self._in_cell and lowered in {"td", "th"}:
            self._current_row.append(clean_text(" ".join(self._current_cell)))
            self._current_cell = []
            self._in_cell = False
        elif self._in_table and self._in_row and lowered == "tr":
            if any(cell for cell in self._current_row):
                self._current_table.append(self._current_row)
            self._current_row = []
            self._in_row = False
        elif self._in_table and lowered == "table":
            if self._current_table:
                self.tables.append(self._current_table)
            self._current_table = []
            self._in_table = False

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._current_cell.append(data)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def clean_text(value: Any) -> str:
    decoded = html.unescape(str(value or "")).replace("\xa0", " ")
    decoded = re.sub(r"<[^>]+>", " ", decoded, flags=re.S)
    return re.sub(r"\s+", " ", decoded).strip()


def normalize_text(value: Any) -> str:
    cleaned = re.sub(r"[^A-Z0-9$/.%]+", " ", clean_text(value).upper())
    return re.sub(r"\s+", " ", cleaned).strip()


def normalize_key(value: Any) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", clean_text(value).lower())
    return re.sub(r"_+", "_", cleaned).strip("_")


def search_tokens(value: Any) -> set[str]:
    return {
        token.strip("$.,/%")
        for token in normalize_text(value).replace("/", " ").replace("-", " ").split()
        if len(token.strip("$.,/%")) > 2 and token.strip("$.,/%") not in GENERIC_TOKENS
    }


def numeric_value(value: Any) -> float | None:
    text = clean_text(value)
    if not text:
        return None
    text = re.sub(r"\bBreak Down\b", "", text, flags=re.I).strip()
    text = text.replace("$", "").replace(",", "").replace("%", "")
    try:
        return float(text)
    except ValueError:
        return None


def value_kind(value: Any) -> str:
    text = clean_text(value)
    if "$" in text:
        return "money"
    if "%" in text:
        return "percent"
    return "count" if numeric_value(text) is not None else "text"


def format_value(value_raw: Any) -> str:
    return clean_text(re.sub(r"\bBreak Down\b", "", clean_text(value_raw), flags=re.I))


def report_years_from_page(page_text: str) -> list[int]:
    years = sorted({int(year) for year in re.findall(r"<option[^>]+value=['\"](20\d{2})['\"]", page_text, flags=re.I)})
    return years or list(range(2017, datetime.now().year + 1))


def data_retrieved_on(page_text: str) -> str | None:
    match = re.search(r"Data\s+retrieved\s+on\s+(\d{1,2}/\d{1,2}/20\d{2})", clean_text(page_text), flags=re.I)
    if not match:
        return None
    month, day, year = match.group(1).split("/")
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def parse_tables(page_text: str) -> list[list[list[str]]]:
    parser = TableParser()
    parser.feed(page_text)
    return parser.tables


def table_records(
    table: list[list[str]],
    partial: MecAnnualPartial,
    report_year: int,
    source_url: str,
    partial_url: str,
    local_file: Path,
    source_hash: str,
    retrieved_on: str | None,
) -> list[dict[str, Any]]:
    if len(table) < 2:
        return []
    header = [clean_text(cell) for cell in table[0]]
    rows = [[clean_text(cell) for cell in row] for row in table[1:] if any(clean_text(cell) for cell in row)]
    records: list[dict[str, Any]] = []

    if len(header) > 2 and len(rows) == 1 and len(rows[0]) == len(header):
        for column_index, label in enumerate(header):
            value_raw = rows[0][column_index]
            records.append(
                make_record(
                    partial=partial,
                    report_year=report_year,
                    label=label,
                    value_label=label,
                    value_raw=value_raw,
                    source_url=source_url,
                    partial_url=partial_url,
                    local_file=local_file,
                    source_hash=source_hash,
                    retrieved_on=retrieved_on,
                )
            )
        return records

    for row in rows:
        if len(row) == 1:
            continue
        label = row[0]
        for column_index, value_raw in enumerate(row[1:], start=1):
            if not clean_text(value_raw):
                continue
            value_label = header[column_index] if column_index < len(header) else header[-1] if header else "Value"
            record_label = label if len(row) == 2 else f"{label} - {value_label}"
            records.append(
                make_record(
                    partial=partial,
                    report_year=report_year,
                    label=record_label,
                    value_label=value_label,
                    value_raw=value_raw,
                    source_url=source_url,
                    partial_url=partial_url,
                    local_file=local_file,
                    source_hash=source_hash,
                    retrieved_on=retrieved_on,
                )
            )
    return records


def make_record(
    *,
    partial: MecAnnualPartial,
    report_year: int,
    label: str,
    value_label: str,
    value_raw: str,
    source_url: str,
    partial_url: str,
    local_file: Path,
    source_hash: str,
    retrieved_on: str | None,
) -> dict[str, Any]:
    cleaned_value = format_value(value_raw)
    record_key = "|".join([str(report_year), partial.key, clean_text(label), clean_text(value_label), cleaned_value])
    return {
        "record_id": hashlib.sha1(record_key.encode("utf-8")).hexdigest()[:16],
        "report_year": report_year,
        "section": partial.section,
        "metric_group": partial.metric_group,
        "metric_group_key": partial.key,
        "label": clean_text(label),
        "label_key": normalize_key(label),
        "value_label": clean_text(value_label),
        "value_raw": cleaned_value,
        "value_number": numeric_value(cleaned_value),
        "value_kind": value_kind(cleaned_value),
        "retrieved_on": retrieved_on,
        "source_url": source_url,
        "partial_url": partial_url,
        "local_file": str(local_file.relative_to(PROJECT_ROOT)),
        "sha256": source_hash,
    }


def dedupe_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    unique: list[dict[str, Any]] = []
    for record in records:
        key = (
            record.get("report_year"),
            record.get("metric_group_key"),
            record.get("label_key"),
            record.get("value_label"),
            record.get("value_raw"),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(record)
    return unique


def build_mec_annual_report_index(force: bool = False, delay_seconds: float = 0.05) -> dict[str, Any]:
    if INDEX_PATH.exists() and not force:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))

    start = time.perf_counter()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (compatible; MissouriPublicDataChat/1.0; +https://github.com/Stroudmj00/missouri-tiny-llm-case-study)",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        }
    )

    seed_year = max(2025, min(datetime.now().year, 2026))
    seed_response = session.get(REPORT_URL_TEMPLATE.format(year=seed_year), timeout=60)
    seed_response.raise_for_status()
    years = report_years_from_page(seed_response.text)

    records: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []
    for year in years:
        year_session = requests.Session()
        year_session.headers.update(session.headers)
        report_url = REPORT_URL_TEMPLATE.format(year=year)
        home_response = year_session.get(report_url, timeout=60)
        home_response.raise_for_status()
        home_text = home_response.text
        home_path = RAW_DIR / f"annual_report_{year}.html"
        home_path.write_text(home_text, encoding="utf-8")
        files.append(
            {
                "year": year,
                "url": report_url,
                "local_file": str(home_path.relative_to(PROJECT_ROOT)),
                "bytes": len(home_text.encode("utf-8", errors="replace")),
                "sha256": sha256_text(home_text),
                "kind": "annual_report_page",
            }
        )
        time.sleep(delay_seconds)
        for partial in PARTIALS:
            partial_url = urljoin(BASE_URL, partial.endpoint)
            response = year_session.get(
                partial_url,
                timeout=60,
                headers={"Referer": report_url, "X-Requested-With": "XMLHttpRequest"},
            )
            response.raise_for_status()
            page_text = response.text
            local_path = RAW_DIR / f"{year}_{partial.key}.html"
            local_path.write_text(page_text, encoding="utf-8")
            source_hash = sha256_text(page_text)
            source_url = f"{report_url}#{partial.anchor}"
            retrieved_on = data_retrieved_on(page_text)
            files.append(
                {
                    "year": year,
                    "url": source_url,
                    "partial_url": partial_url,
                    "local_file": str(local_path.relative_to(PROJECT_ROOT)),
                    "bytes": len(page_text.encode("utf-8", errors="replace")),
                    "sha256": source_hash,
                    "kind": "annual_report_partial",
                    "metric_group": partial.metric_group,
                    "retrieved_on": retrieved_on,
                }
            )
            for table in parse_tables(page_text):
                records.extend(
                    table_records(
                        table=table,
                        partial=partial,
                        report_year=year,
                        source_url=source_url,
                        partial_url=partial_url,
                        local_file=local_path,
                        source_hash=source_hash,
                        retrieved_on=retrieved_on,
                    )
                )
            time.sleep(delay_seconds)

    records = dedupe_records(records)
    years_with_rows = sorted({int(record["report_year"]) for record in records})
    metric_groups = Counter(record["metric_group"] for record in records)
    sections = Counter(record["section"] for record in records)
    payload = {
        "generated_at_utc": utc_now(),
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "source": SOURCE_NAME,
        "source_home": f"{BASE_URL}/AnnualReport/{years[-1] if years else seed_year}",
        "index_path": str(INDEX_PATH.relative_to(PROJECT_ROOT)),
        "record_count": len(records),
        "year_count": len(years_with_rows),
        "years": years_with_rows,
        "metric_group_counts": dict(sorted(metric_groups.items())),
        "section_counts": dict(sorted(sections.items())),
        "files": files,
        "notes": [
            "This index parses official MEC Electronic Annual Report aggregate tables for available report years.",
            "It stores annual aggregate rows for campaign finance, lobbying, and personal financial disclosure sections.",
            "It does not parse individual filings, donor identities, complaint files, commission action details, or legal conclusions.",
        ],
        "records": records,
    }
    write_json(INDEX_PATH, payload)
    write_json(REPORT_PATH, {key: value for key, value in payload.items() if key != "records"})
    return payload


def requested_year(question: str, years: list[int]) -> int | None:
    requested = [int(year) for year in re.findall(r"\b(20\d{2})\b", question)]
    if requested:
        return requested[-1]
    lowered = question.lower()
    if any(term in lowered for term in ["latest", "newest", "current", "this year"]):
        return max(years) if years else None
    return None


def requested_metric_groups(question: str) -> list[str]:
    lowered = question.lower()
    matches: list[str] = []
    for group, patterns in METRIC_GROUP_ALIASES:
        if any(re.search(pattern, lowered) for pattern in patterns):
            matches.append(group)
    return matches


def asks_for_summary(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["indexed", "coverage", "available", "what data", "what metrics", "summary"])


def asks_for_ranking(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["highest", "largest", "most", "top"])


def should_exclude_total(question: str) -> bool:
    lowered = question.lower()
    return not re.search(r"\b(total|overall|all)\b", lowered)


def requested_label_keys(question: str) -> set[str]:
    lowered = question.lower()
    labels: set[str] = set()
    if re.search(r"\breceipts?\b", lowered):
        labels.add("receipts")
    if re.search(r"\bexpenditures?\b", lowered):
        labels.add("expenditures")
    if re.search(r"\bcontributions?\s+made\b|\bmade\s+to\s+other\s+committees\b", lowered):
        labels.add("contributions_made_to_other_committees")
    if re.search(r"\bspent\s+on\s+official\b", lowered):
        labels.add("spent_on_official")
    if re.search(r"\bspent\s+on\s+staff\b", lowered):
        labels.add("spent_on_staff")
    if re.search(r"\bspent\s+on\s+family\b", lowered):
        labels.add("spent_on_family")
    return labels


def asks_for_total_count(question: str) -> bool:
    return bool(re.search(r"\b(how\s+many|count|number\s+of|total|overall|all)\b", question, flags=re.I))


def should_prefer_total_row(question: str, rows: list[dict[str, Any]]) -> bool:
    if not asks_for_total_count(question):
        return False
    if requested_label_keys(question):
        return False
    if any(row.get("label_key") not in {"total", "totals"} and row_score(question, row) >= 12 for row in rows):
        return False
    groups = {row.get("metric_group") for row in rows}
    return bool(
        groups
        & {
            "Registered Lobbyists",
            "Registered Campaign Finance Committees",
            "Candidate Committees by Election",
            "Campaign Committees by Election",
            "Large Contributions Over $5,000",
        }
    )


def row_score(question: str, row: dict[str, Any]) -> int:
    question_norm = normalize_text(question)
    score = 0
    row_blob = " ".join(str(row.get(key, "")) for key in ["metric_group", "label", "value_label", "section"])
    overlap = search_tokens(question) & search_tokens(row_blob)
    score += len(overlap)
    if normalize_text(row.get("label", "")) and normalize_text(row.get("label", "")) in question_norm:
        score += 8
    if normalize_text(row.get("metric_group", "")) and normalize_text(row.get("metric_group", "")) in question_norm:
        score += 6
    if row.get("label_key") == "total" and re.search(r"\b(overall|all)\b", question, flags=re.I):
        score += 4
    if row.get("label_key") == "total" and re.search(r"\btotal\b", question, flags=re.I) and not requested_label_keys(question):
        score += 4
    if row.get("value_label", "").lower() == "total" and re.search(r"\b(total|count|how many|amount|how much)\b", question, flags=re.I):
        score += 2
    return score


def format_metric_value(row: dict[str, Any]) -> str:
    value = row.get("value_raw") or "not reported"
    return str(value)


class MecAnnualReportIndex:
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

    def citation(self, matched_rows: int = 0, rows: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        payload = self.payload()
        row_list = rows or []
        source_files: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in row_list[:8]:
            url = row.get("source_url") or payload.get("source_home") or BASE_URL
            if url in seen:
                continue
            seen.add(url)
            source_files.append(
                {
                    "category": "mec_annual_report",
                    "category_label": f"MEC {row.get('report_year')} Annual Report - {row.get('metric_group')}",
                    "file_name": url,
                    "source_url": url,
                    "row_count": matched_rows,
                    "bytes": None,
                    "sha256": row.get("sha256"),
                }
            )
        if not source_files:
            source_files.append(
                {
                    "category": "mec_annual_report",
                    "category_label": "MEC Electronic Annual Report",
                    "file_name": payload.get("source_home") or BASE_URL,
                    "source_url": payload.get("source_home") or BASE_URL,
                    "row_count": payload.get("record_count"),
                    "bytes": None,
                    "sha256": None,
                }
            )
        years = payload.get("years", [])
        return [
            {
                "dataset": payload.get("source", SOURCE_NAME),
                "category": "Ethics and campaign finance",
                "kind": "MEC annual-report aggregate lookup",
                "lookup_table": "mec_annual_report_index",
                "year": row_list[0].get("report_year") if row_list and len({row.get("report_year") for row in row_list}) == 1 else None,
                "year_range": f"{min(years)}-{max(years)}" if years else None,
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
                "The MEC annual-report aggregate index has not been built yet. Run "
                "`python scripts/build_mec_annual_report_index.py --force` to index the official Electronic Annual Report tables."
            ),
            "retrieved_context_id": "mec_annual_report_index:missing",
            "retrieved_source": "mec_annual_report_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "The MEC annual-report route exists, but the local ignored index is missing.",
            "citations": [],
            "source_rows": [],
        }

    def summary_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        years = payload.get("years", [])
        year_text = f"{min(years)}-{max(years)}" if years else "the available report years"
        groups = "; ".join(
            f"{label}: {count}"
            for label, count in sorted(payload.get("metric_group_counts", {}).items(), key=lambda item: item[0])[:8]
        )
        return {
            "question": question,
            "answer": (
                f"The MEC annual-report exact layer indexes {payload.get('record_count', 0):,} aggregate table row(s) "
                f"from official Electronic Annual Report pages for {year_text}. It covers campaign finance activity, "
                "registered campaign-finance committees, candidate/campaign committees by election, large contributions, "
                "receipts by office, registered lobbyists, lobbying expenditures, and PFD subdivision/budget/ordinance aggregates. "
                f"Example groups: {groups}. It does not parse individual campaign filings, donor identities, complaint files, "
                "commission-action details, or legal conclusions."
            ),
            "retrieved_context_id": "mec_annual_report_index:summary",
            "retrieved_source": "mec_annual_report_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local MEC annual-report aggregate index.",
            "citations": self.citation(matched_rows=payload.get("record_count", 0)),
            "source_rows": [],
        }

    def rows_for_question(self, question: str) -> list[dict[str, Any]]:
        records = self.records()
        years = sorted({int(row["report_year"]) for row in records})
        year = requested_year(question, years)
        if year is not None:
            records = [row for row in records if int(row.get("report_year", 0)) == year]
        elif years:
            records = [row for row in records if int(row.get("report_year", 0)) == max(years)]

        groups = requested_metric_groups(question)
        if groups:
            records = [row for row in records if row.get("metric_group") in groups]

        label_keys = requested_label_keys(question)
        if label_keys:
            matching_labels = [row for row in records if row.get("label_key") in label_keys or normalize_key(row.get("value_label")) in label_keys]
            if matching_labels:
                records = matching_labels

        if (
            should_exclude_total(question)
            and not asks_for_total_count(question)
            and not any(term in question.lower() for term in ["total receipts", "total campaign"])
        ):
            non_total = [row for row in records if row.get("label_key") not in {"total", "totals"}]
            if non_total:
                records = non_total

        if should_prefer_total_row(question, records):
            total_rows = [row for row in records if row.get("label_key") in {"total", "totals"}]
            if total_rows:
                return total_rows

        scored = [(row_score(question, row), row) for row in records]
        scored = [(score, row) for score, row in scored if score > 0]
        if not scored:
            return []
        scored.sort(key=lambda item: (-item[0], str(item[1].get("metric_group")), str(item[1].get("label"))))
        best_score = scored[0][0]
        return [row for score, row in scored if score == best_score]

    def metric_answer(self, question: str, row: dict[str, Any]) -> dict[str, Any]:
        retrieved = f", data retrieved {row['retrieved_on']}" if row.get("retrieved_on") else ""
        answer = (
            f"MEC's {row['report_year']} Electronic Annual Report lists {row['metric_group']} - "
            f"{row['label']} as {format_metric_value(row)}{retrieved}."
        )
        return {
            "question": question,
            "answer": answer,
            "retrieved_context_id": f"mec_annual_report_index:{row['record_id']}",
            "retrieved_source": "mec_annual_report_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local MEC annual-report aggregate index.",
            "citations": self.citation(matched_rows=1, rows=[row]),
            "source_rows": [{"source_file": row["source_url"], "values": row}],
        }

    def ranking_answer(self, question: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
        numeric_rows = [row for row in rows if row.get("value_number") is not None and row.get("label_key") not in {"total", "totals"}]
        if not numeric_rows:
            return self.rows_answer(question, rows)
        top = sorted(numeric_rows, key=lambda item: item["value_number"], reverse=True)[:5]
        rendered = "; ".join(
            f"{index}. {row['label']} ({row['report_year']} {row['metric_group']}): {row['value_raw']}"
            for index, row in enumerate(top, start=1)
        )
        return {
            "question": question,
            "answer": f"The highest matching MEC annual-report aggregate rows are: {rendered}.",
            "retrieved_context_id": "mec_annual_report_index:ranking",
            "retrieved_source": "mec_annual_report_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local MEC annual-report aggregate index.",
            "citations": self.citation(matched_rows=len(top), rows=top),
            "source_rows": [{"source_file": row["source_url"], "values": row} for row in top],
        }

    def rows_answer(self, question: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
        preview = rows[:5]
        rendered = "; ".join(
            f"{row['report_year']} {row['metric_group']} - {row['label']}: {row['value_raw']}" for row in preview
        )
        return {
            "question": question,
            "answer": f"Showing {len(preview)} matching MEC annual-report aggregate row(s): {rendered}.",
            "retrieved_context_id": "mec_annual_report_index:match",
            "retrieved_source": "mec_annual_report_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local MEC annual-report aggregate index.",
            "citations": self.citation(matched_rows=len(rows), rows=preview),
            "source_rows": [{"source_file": row["source_url"], "values": row} for row in preview],
        }

    def missing_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "I have indexed MEC annual-report aggregate tables, but this question did not match a supported aggregate row. "
                "Try `How many registered lobbyists were listed in the 2025 MEC annual report?`, "
                "`What were total campaign finance receipts in 2025?`, or "
                "`How many school districts were subject to PFD requirements in 2025?`"
            ),
            "retrieved_context_id": "mec_annual_report_index:no_match",
            "retrieved_source": "mec_annual_report_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "No aggregate row matched the local MEC annual-report index.",
            "citations": self.citation(),
            "source_rows": [],
        }

    def answer(self, question: str) -> dict[str, Any] | None:
        if not self.available():
            return self.unavailable_answer(question)
        if asks_for_summary(question) and not requested_metric_groups(question):
            return self.summary_answer(question)
        rows = self.rows_for_question(question)
        if rows and asks_for_ranking(question):
            return self.ranking_answer(question, rows)
        if len(rows) == 1:
            return self.metric_answer(question, rows[0])
        if rows:
            return self.rows_answer(question, rows)
        if asks_for_summary(question):
            return self.summary_answer(question)
        return self.missing_answer(question)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--delay-seconds", type=float, default=0.05)
    args = parser.parse_args()
    payload = build_mec_annual_report_index(force=args.force, delay_seconds=args.delay_seconds)
    print(json.dumps({key: value for key, value in payload.items() if key != "records"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
