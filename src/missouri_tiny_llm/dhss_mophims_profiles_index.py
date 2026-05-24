"""Build and query selected DHSS MOPHIMS statewide profile aggregates."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw_public" / "dhss_mophims_profiles"
INDEX_PATH = RAW_DIR / "dhss_mophims_profiles_index.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "dhss_mophims_profiles_index_report.json"
SOURCE_NAME = "DHSS MOPHIMS Community Data Profiles"

PROFILE_SPECS = {
    1: {
        "name": "Missouri Resident Child Health Profile",
        "short_name": "Child Health",
        "aliases": ["child health", "children", "wic participation", "ages 1", "ages 5"],
    },
    5: {
        "name": "Missouri Resident Chronic Disease Comparisons Profile",
        "short_name": "Chronic Disease Comparisons",
        "aliases": ["chronic disease", "chronic disease comparisons", "heart disease", "diabetes", "stroke"],
    },
    10: {
        "name": "Missouri Resident Death - Leading Causes Profile",
        "short_name": "Leading Causes of Death",
        "aliases": ["leading cause", "leading causes", "cause of death", "causes of death", "all causes"],
    },
    22: {
        "name": "Missouri Resident Emergency Room Profile",
        "short_name": "Emergency Room",
        "aliases": ["emergency room", "er visits", "emergency department", "ed visits"],
    },
    24: {
        "name": "Missouri Resident Inpatient Hospitalizations Profile",
        "short_name": "Inpatient Hospitalizations",
        "aliases": ["inpatient hospitalization", "inpatient hospitalizations", "hospitalization", "hospitalizations", "septicemia"],
    },
}

COUNTY_PROFILE_CODES = (24,)
SELECTED_COUNTIES = [
    {"code": "019", "label": "Boone", "aliases": ["boone", "boone county"]},
    {"code": "051", "label": "Cole", "aliases": ["cole", "cole county"]},
    {"code": "077", "label": "Greene", "aliases": ["greene", "greene county"]},
    {"code": "095", "label": "Jackson", "aliases": ["jackson", "jackson county"]},
    {"code": "189", "label": "St. Louis County", "aliases": ["st louis county", "st. louis county"]},
    {"code": "510", "label": "St. Louis City", "aliases": ["st louis city", "st. louis city"]},
]

TOTAL_LABELS = {
    "all causes",
    "all diseases conditions",
}

STOPWORDS = {
    "a",
    "about",
    "aggregate",
    "all",
    "and",
    "answer",
    "are",
    "category",
    "count",
    "counts",
    "data",
    "dhss",
    "do",
    "does",
    "for",
    "from",
    "give",
    "how",
    "in",
    "indexed",
    "is",
    "latest",
    "me",
    "mica",
    "missouri",
    "mophims",
    "of",
    "profile",
    "profiles",
    "rate",
    "reported",
    "source",
    "statewide",
    "the",
    "total",
    "totals",
    "value",
    "what",
    "which",
    "with",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip()


def normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def tokens_for(value: str) -> set[str]:
    return {token for token in normalize_text(value).split() if token and token not in STOPWORDS}


def parse_number(value: str) -> float | None:
    cleaned = clean_text(value).replace(",", "").replace("*", "").strip()
    if re.fullmatch(r"-?\d+(?:\.\d+)?", cleaned):
        return float(cleaned)
    return None


def format_number(value: float | int | None) -> str:
    if value is None:
        return "not listed"
    number = float(value)
    return f"{int(number):,}" if number.is_integer() else f"{number:,.2f}"


def safe_record_id(*parts: Any) -> str:
    return hashlib.sha1("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:16]


def profile_url(profile_code: int) -> str:
    return f"https://healthapps.dhss.mo.gov/MoPhims/ProfileBuilder?pc={profile_code}"


class TableTextParser(HTMLParser):
    """Small HTML table parser for DHSS ProfileBuilder output."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._table_depth = 0
        self._current_table: list[list[str]] | None = None
        self._current_row: list[str] | None = None
        self._current_cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "table":
            if self._table_depth == 0:
                self._current_table = []
            self._table_depth += 1
            return
        if self._table_depth <= 0:
            return
        if tag == "tr":
            self._current_row = []
        elif tag in {"td", "th"} and self._current_row is not None:
            self._current_cell = []
        elif tag == "br" and self._current_cell is not None:
            self._current_cell.append(" ")

    def handle_data(self, data: str) -> None:
        if self._current_cell is not None:
            self._current_cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._table_depth <= 0:
            return
        if tag in {"td", "th"} and self._current_cell is not None and self._current_row is not None:
            self._current_row.append(clean_text("".join(self._current_cell)))
            self._current_cell = None
        elif tag == "tr" and self._current_row is not None:
            if any(cell for cell in self._current_row):
                self._current_table = self._current_table or []
                self._current_table.append(self._current_row)
            self._current_row = None
        elif tag == "table":
            self._table_depth -= 1
            if self._table_depth == 0 and self._current_table is not None:
                self.tables.append(self._current_table)
                self._current_table = None


class ProfileFormParser(HTMLParser):
    """Parse the ASP.NET form fields needed to request selected MOPHIMS views."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.fields: dict[str, str] = {}
        self.selects: dict[str, list[dict[str, Any]]] = {}
        self._current_select: str | None = None
        self._current_option: dict[str, Any] | None = None
        self._current_option_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key.lower(): value or "" for key, value in attrs}
        tag = tag.lower()
        if tag == "input":
            input_type = attributes.get("type", "").lower()
            if input_type in {"submit", "button", "image"}:
                return
            name = attributes.get("name")
            if name:
                self.fields[name] = unescape(attributes.get("value", ""))
            return
        if tag == "select":
            name = attributes.get("name")
            if name:
                self._current_select = name
                self.selects.setdefault(name, [])
            return
        if tag == "option" and self._current_select:
            self._current_option = {
                "value": unescape(attributes.get("value", "")),
                "selected": "selected" in attributes,
            }
            self._current_option_text = []

    def handle_data(self, data: str) -> None:
        if self._current_option is not None:
            self._current_option_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "option" and self._current_select and self._current_option is not None:
            option = dict(self._current_option)
            option["text"] = clean_text("".join(self._current_option_text))
            self.selects[self._current_select].append(option)
            self._current_option = None
            self._current_option_text = []
        elif tag == "select":
            self._current_select = None


def parse_profile_form(html: str) -> tuple[dict[str, str], dict[str, list[dict[str, Any]]]]:
    parser = ProfileFormParser()
    parser.feed(html)
    fields = dict(parser.fields)
    for name, options in parser.selects.items():
        selected = next((option for option in options if option.get("selected")), None) or (options[0] if options else None)
        if selected is not None:
            fields[name] = str(selected.get("value") or "")
    return fields, parser.selects


def parse_years(value: str) -> tuple[int | None, int | None]:
    years = [int(match) for match in re.findall(r"\b(19\d{2}|20\d{2})\b", value)]
    if not years:
        return None, None
    return min(years), max(years)


def parse_profile_rows(
    html: str,
    profile_code: int,
    source_url: str,
    geography: str = "STATEWIDE",
    geography_label: str = "State: Missouri",
    geography_code: str | None = None,
) -> list[dict[str, Any]]:
    parser = TableTextParser()
    parser.feed(html)
    table: list[list[str]] | None = None
    for candidate in parser.tables:
        if not candidate:
            continue
        header = [normalize_text(cell) for cell in candidate[0]]
        if "data category" in header and "data years" in header and "count" in header and "rate" in header:
            table = candidate
            break
    if table is None:
        raise ValueError(f"Could not find ProfileBuilder data table for pc={profile_code}")

    spec = PROFILE_SPECS[profile_code]
    records: list[dict[str, Any]] = []
    current_group: str | None = None
    for raw_row in table[1:]:
        cells = (raw_row + ["", "", "", "", "", "", ""])[:7]
        data_category, data_years, count_text, rate_text, state_rate_text, different_text, quintile_text = [
            clean_text(cell) for cell in cells
        ]
        if not data_category:
            continue
        if not data_years and not count_text and not rate_text:
            current_group = data_category
            continue
        count = parse_number(count_text)
        rate = parse_number(rate_text)
        if count is None and rate is None:
            continue
        first_year, last_year = parse_years(data_years)
        display_name = data_category
        if current_group and normalize_text(current_group) != normalize_text(data_category):
            display_name = f"{current_group} - {data_category}"
        state_rate = parse_number(state_rate_text)
        record_id = safe_record_id(
            profile_code,
            geography,
            geography_code or "",
            current_group or "",
            data_category,
            data_years,
            count_text,
            rate_text,
        )
        records.append(
            {
                "record_id": record_id,
                "profile_code": profile_code,
                "profile_name": spec["name"],
                "profile_short_name": spec["short_name"],
                "geography": geography,
                "geography_code": geography_code,
                "geography_label": geography_label,
                "demographic": "All",
                "group": current_group,
                "indicator": data_category,
                "display_name": display_name,
                "data_years": data_years,
                "first_year": first_year,
                "last_year": last_year,
                "count": count,
                "rate": rate,
                "state_rate": state_rate,
                "significantly_different": different_text or None,
                "ranking_quintile": quintile_text or None,
                "rate_unreliable": "*" in count_text or "*" in rate_text,
                "source_url": source_url,
            }
        )
    return records


def download_profile(profile_code: int, force: bool = False) -> tuple[str, dict[str, Any]]:
    url = profile_url(profile_code)
    local_path = RAW_DIR / f"profile_pc_{profile_code}.html"
    if force or not local_path.exists():
        response = requests.get(
            url,
            timeout=90,
            headers={"User-Agent": "missouri-tiny-llm-case-study/1.0"},
        )
        response.raise_for_status()
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_text(response.text, encoding="utf-8")
        html = response.text
        final_url = response.url
    else:
        html = local_path.read_text(encoding="utf-8", errors="replace")
        final_url = url
    html_bytes = html.encode("utf-8", errors="replace")
    return html, {
        "url": url,
        "final_url": final_url,
        "local_file": str(local_path.relative_to(PROJECT_ROOT)),
        "bytes": len(html_bytes),
        "sha256": hashlib.sha256(html_bytes).hexdigest(),
        "profile_code": profile_code,
        "profile_name": PROFILE_SPECS[profile_code]["name"],
    }


def selected_county_map() -> dict[str, dict[str, Any]]:
    return {str(row["code"]): row for row in SELECTED_COUNTIES}


def county_alias_map() -> dict[str, dict[str, Any]]:
    aliases: dict[str, dict[str, Any]] = {}
    for row in SELECTED_COUNTIES:
        for alias in row["aliases"]:
            aliases[normalize_text(alias)] = row
    return aliases


def county_display_label(county: dict[str, Any]) -> str:
    label = str(county.get("label") or "").strip()
    if not label:
        return str(county.get("code") or "selected county")
    if "county" in label.lower() or "city" in label.lower():
        return label
    return f"{label} County"


def post_profile_form(
    session: requests.Session,
    url: str,
    data: dict[str, str],
    timeout: int = 90,
) -> requests.Response:
    response = session.post(
        url,
        data=data,
        timeout=timeout,
        headers={
            "User-Agent": "missouri-tiny-llm-case-study/1.0",
            "Referer": url,
        },
    )
    response.raise_for_status()
    return response


def county_profile_cache_path(profile_code: int, county_code: str) -> Path:
    return RAW_DIR / f"profile_pc_{profile_code}_county_{county_code}.html"


def download_county_profiles(profile_code: int, force: bool = False) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Download selected county aggregate profile views for one profile code."""

    url = profile_url(profile_code)
    records: list[dict[str, Any]] = []
    files: dict[str, Any] = {}
    selected_codes = set(selected_county_map())
    missing_codes = [
        county["code"]
        for county in SELECTED_COUNTIES
        if force or not county_profile_cache_path(profile_code, str(county["code"])).exists()
    ]

    session = requests.Session()
    county_options: dict[str, str] = {}
    county_form_fields: dict[str, str] | None = None
    if missing_codes:
        response = session.get(
            url,
            timeout=90,
            headers={"User-Agent": "missouri-tiny-llm-case-study/1.0"},
        )
        response.raise_for_status()
        form_fields, _ = parse_profile_form(response.text)
        form_fields["ctl00$MainContent$ddlGeography"] = "CNTY"
        form_fields["ctl00$MainContent$ddlDemographys"] = "All"
        form_fields["ctl00$MainContent$btnSubmit"] = "Submit"
        county_response = post_profile_form(session, url, form_fields)
        county_form_fields, selects = parse_profile_form(county_response.text)
        county_options = {
            str(option.get("value") or ""): str(option.get("text") or "")
            for option in selects.get("ctl00$MainContent$ddlCounty", [])
            if option.get("value")
        }
        missing = sorted(selected_codes - set(county_options))
        if missing:
            raise ValueError(f"Selected county code(s) not present in DHSS form for pc={profile_code}: {missing}")

    for county in SELECTED_COUNTIES:
        county_code = str(county["code"])
        local_path = county_profile_cache_path(profile_code, county_code)
        if force or not local_path.exists():
            if county_form_fields is None:
                raise RuntimeError("County form was not initialized")
            post_data = dict(county_form_fields)
            post_data["ctl00$MainContent$ddlGeography"] = "CNTY"
            post_data["ctl00$MainContent$ddlCounty"] = county_code
            post_data["ctl00$MainContent$ddlDemographys"] = "All"
            post_data["ctl00$MainContent$btnSubmit"] = "Submit"
            response = post_profile_form(session, url, post_data)
            html = response.text
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_text(html, encoding="utf-8")
            final_url = response.url
            county_label = county_options.get(county_code, county["label"])
        else:
            html = local_path.read_text(encoding="utf-8", errors="replace")
            final_url = url
            county_label = county["label"]

        html_bytes = html.encode("utf-8", errors="replace")
        file_meta = {
            "url": url,
            "final_url": final_url,
            "local_file": str(local_path.relative_to(PROJECT_ROOT)),
            "bytes": len(html_bytes),
            "sha256": hashlib.sha256(html_bytes).hexdigest(),
            "profile_code": profile_code,
            "profile_name": PROFILE_SPECS[profile_code]["name"],
            "county_code": county_code,
            "county_label": county_label,
        }
        files[f"profile_pc_{profile_code}_county_{county_code}"] = file_meta
        records.extend(
            parse_profile_rows(
                html,
                profile_code,
                url,
                geography="COUNTY",
                geography_code=county_code,
                geography_label=f"County: {county_label}",
            )
        )

    return records, files


def build_dhss_mophims_profiles_index(force: bool = False) -> dict[str, Any]:
    if INDEX_PATH.exists() and not force:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))

    start = time.perf_counter()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    county_records: list[dict[str, Any]] = []
    files: dict[str, Any] = {}
    county_files: dict[str, Any] = {}
    for profile_code in PROFILE_SPECS:
        html, file_meta = download_profile(profile_code, force=force)
        records.extend(parse_profile_rows(html, profile_code, file_meta["url"]))
        files[f"profile_pc_{profile_code}"] = file_meta
        if profile_code in COUNTY_PROFILE_CODES:
            downloaded_records, downloaded_files = download_county_profiles(profile_code, force=force)
            county_records.extend(downloaded_records)
            county_files.update(downloaded_files)

    profile_counts: dict[str, int] = {}
    for record in records:
        profile_counts[record["profile_short_name"]] = profile_counts.get(record["profile_short_name"], 0) + 1
    payload = {
        "generated_at_utc": utc_now(),
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "source": SOURCE_NAME,
        "index_path": str(INDEX_PATH.relative_to(PROJECT_ROOT)),
        "record_count": len(records),
        "county_record_count": len(county_records),
        "selected_counties": SELECTED_COUNTIES,
        "profile_count": len(PROFILE_SPECS),
        "profiles": [
            {
                "profile_code": code,
                "profile_name": spec["name"],
                "profile_short_name": spec["short_name"],
                "url": profile_url(code),
                "record_count": profile_counts.get(spec["short_name"], 0),
            }
            for code, spec in PROFILE_SPECS.items()
        ],
        "files": files,
        "county_files": county_files,
        "notes": [
            "This index parses selected official DHSS MOPHIMS ProfileBuilder pages for the default STATEWIDE / All demographic view.",
            "It also parses selected county aggregate inpatient-hospitalization profile pages for Boone, Cole, Greene, Jackson, St. Louis County, and St. Louis City.",
            "It stores aggregate profile counts and rates only.",
            "It does not parse all counties, city, region, race, patient-level PAS, discharge records, certificates, or individual health records.",
        ],
        "records": records,
        "county_records": county_records,
    }
    write_json(INDEX_PATH, payload)
    top_by_profile: dict[str, list[dict[str, Any]]] = {}
    for profile in payload["profiles"]:
        rows = [
            record
            for record in records
            if record["profile_short_name"] == profile["profile_short_name"]
            and normalize_text(record["indicator"]) not in TOTAL_LABELS
            and record.get("count") is not None
        ]
        rows.sort(key=lambda item: item["count"], reverse=True)
        top_by_profile[profile["profile_short_name"]] = [
            {
                "display_name": record["display_name"],
                "data_years": record["data_years"],
                "count": record["count"],
                "rate": record["rate"],
            }
            for record in rows[:5]
        ]
    write_json(
        REPORT_PATH,
        {key: value for key, value in payload.items() if key not in {"records", "county_records"}}
        | {"top_by_profile": top_by_profile},
    )
    return payload


def asks_for_summary(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["indexed", "coverage", "what data", "summary", "available"])


def asks_for_source(question: str) -> bool:
    lowered = question.lower()
    return "source" in lowered or "link" in lowered


def asks_for_top(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["highest", "largest", "top", "most common", "most frequent"])


def is_total_record(record: dict[str, Any]) -> bool:
    return normalize_text(record.get("indicator", "")) in TOTAL_LABELS


class DhssMophimsProfilesIndex:
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

    def county_records(self) -> list[dict[str, Any]]:
        return list(self.payload().get("county_records", []))

    def county_for_question(self, question: str) -> dict[str, Any] | None:
        question_norm = normalize_text(question)
        matches = [
            row
            for alias, row in county_alias_map().items()
            if alias and re.search(rf"\b{re.escape(alias)}\b", question_norm)
        ]
        if not matches:
            return None
        matches.sort(key=lambda row: len(" ".join(row["aliases"])), reverse=True)
        return matches[0]

    def citation(self, matched_rows: int = 0, profile_code: int | None = None) -> list[dict[str, Any]]:
        payload = self.payload()
        files = payload.get("files", {})
        selected_files = {
            key: value
            for key, value in files.items()
            if profile_code is None or int(value.get("profile_code", -1)) == int(profile_code)
        }
        return [
            {
                "dataset": payload.get("source", SOURCE_NAME),
                "category": "Public health",
                "kind": "DHSS MOPHIMS statewide profile aggregate lookup",
                "lookup_table": "dhss_mophims_profiles_index",
                "year": None,
                "year_range": "varies by profile row",
                "source_files": [
                    {
                        "category": key,
                        "category_label": value.get("profile_name"),
                        "file_name": value.get("url"),
                        "row_count": None,
                        "bytes": value.get("bytes"),
                        "sha256": value.get("sha256"),
                    }
                    for key, value in selected_files.items()
                ],
                "source_file_count": len(selected_files),
                "source_rows": payload.get("record_count"),
                "matched_rows": matched_rows,
            }
        ]

    def unavailable_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "The DHSS MOPHIMS statewide profile aggregate index has not been built yet. Run "
                "`python scripts/build_dhss_mophims_profiles_index.py --force` to index selected official ProfileBuilder pages."
            ),
            "retrieved_context_id": "dhss_mophims_profiles_index:missing",
            "retrieved_source": "dhss_mophims_profiles_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "citations": [],
            "source_rows": [],
        }

    def profile_for_question(self, question: str) -> int | None:
        lowered = question.lower()
        if any(term in lowered for term in ["inpatient", "septicemia"]):
            return 24
        if any(term in lowered for term in ["emergency room", "er visit", "ed visit", "emergency department"]):
            return 22
        if "leading cause" in lowered or "cause of death" in lowered or "causes of death" in lowered:
            return 10
        if "chronic disease" in lowered:
            return 5
        if "child health" in lowered or "wic participation" in lowered:
            return 1
        for profile_code, spec in PROFILE_SPECS.items():
            if any(alias in lowered for alias in spec["aliases"]):
                return profile_code
        return None

    def summary_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        profiles = "; ".join(
            f"{profile['profile_short_name']} ({profile['record_count']} row(s))"
            for profile in payload.get("profiles", [])
        )
        county_labels = ", ".join(county_display_label(row) for row in payload.get("selected_counties", []))
        return {
            "question": question,
            "answer": (
                f"The DHSS MOPHIMS statewide profile layer indexes {payload.get('record_count', 0)} aggregate row(s) "
                f"from {payload.get('profile_count', 0)} selected ProfileBuilder page(s): {profiles}. "
                f"It also indexes {payload.get('county_record_count', 0)} selected county aggregate inpatient-hospitalization row(s) "
                f"for {county_labels}. City, region, race, all-county, and patient-level PAS values are not parsed."
            ),
            "retrieved_context_id": "dhss_mophims_profiles_index:summary",
            "retrieved_source": "dhss_mophims_profiles_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from selected local DHSS MOPHIMS ProfileBuilder page snapshots.",
            "citations": self.citation(matched_rows=payload.get("record_count", 0)),
            "source_rows": [],
        }

    def profile_summary_answer(self, question: str, profile_code: int) -> dict[str, Any]:
        rows = [record for record in self.records() if record["profile_code"] == profile_code]
        county_rows = [record for record in self.county_records() if record["profile_code"] == profile_code]
        spec = PROFILE_SPECS[profile_code]
        sample = "; ".join(row["display_name"] for row in rows[:6])
        return {
            "question": question,
            "answer": (
                f"The DHSS MOPHIMS {spec['short_name']} statewide profile has {len(rows)} indexed aggregate row(s) "
                f"plus {len(county_rows)} selected county aggregate row(s). "
                f"Example rows: {sample}. Counts and rates use the data years shown on each profile row."
            ),
            "retrieved_context_id": f"dhss_mophims_profiles_index:profile:{profile_code}",
            "retrieved_source": "dhss_mophims_profiles_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from selected local DHSS MOPHIMS ProfileBuilder page snapshots.",
            "citations": self.citation(matched_rows=len(rows), profile_code=profile_code),
            "source_rows": [],
        }

    def source_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        links = "; ".join(f"{profile['profile_short_name']}: {profile['url']}" for profile in payload.get("profiles", []))
        return {
            "question": question,
            "answer": (
                "The DHSS MOPHIMS aggregate index uses selected official ProfileBuilder pages for STATEWIDE / All demographic profile tables. "
                "Selected county inpatient-hospitalization values are produced from the same official ProfileBuilder form after selecting COUNTY. "
                f"Indexed source pages: {links}."
            ),
            "retrieved_context_id": "dhss_mophims_profiles_index:source",
            "retrieved_source": "dhss_mophims_profiles_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from selected local DHSS MOPHIMS ProfileBuilder page snapshots.",
            "citations": self.citation(matched_rows=0),
            "source_rows": [],
        }

    def find_record(
        self,
        question: str,
        profile_code: int | None,
        county: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        question_norm = normalize_text(question)
        question_tokens = tokens_for(question)
        wants_hospitalization = any(term in question_norm for term in ["hospitalization", "hospitalizations", "inpatient"])
        wants_er = any(term in question_norm for term in ["emergency room", "er visit", "er visits", "ed visit", "ed visits"])
        wants_death = "death" in question_norm or "deaths" in question_norm
        if county is not None:
            rows = [
                record
                for record in self.county_records()
                if (profile_code is None or record["profile_code"] == profile_code)
                and str(record.get("geography_code")) == str(county["code"])
            ]
        else:
            rows = [record for record in self.records() if profile_code is None or record["profile_code"] == profile_code]
        ranked: list[tuple[int, dict[str, Any]]] = []
        for record in rows:
            searchable = " ".join(
                str(record.get(key, "") or "")
                for key in ["profile_short_name", "group", "indicator", "display_name"]
            )
            record_norm = normalize_text(searchable)
            record_tokens = tokens_for(searchable)
            score = len(question_tokens & record_tokens)
            if normalize_text(record["indicator"]) and normalize_text(record["indicator"]) in question_norm:
                score += 20
            if normalize_text(record["display_name"]) and normalize_text(record["display_name"]) in question_norm:
                score += 30
            if record.get("group") and normalize_text(record["group"]) in question_norm:
                score += 8
            indicator_norm = normalize_text(record.get("indicator", ""))
            if wants_hospitalization and "hospitalization" in indicator_norm:
                score += 25
            if wants_er and ("er visits" in indicator_norm or "emergency" in indicator_norm):
                score += 25
            if wants_death and indicator_norm == "deaths":
                score += 25
            if score:
                ranked.append((score, record))
        if not ranked:
            return None
        ranked.sort(key=lambda item: (-item[0], item[1]["profile_code"], item[1]["display_name"]))
        return ranked[0][1]

    def record_answer(self, question: str, record: dict[str, Any]) -> dict[str, Any]:
        unreliable = " The rate is marked unreliable by the source." if record.get("rate_unreliable") else ""
        comparison = ""
        if record.get("state_rate") is not None:
            different = record.get("significantly_different")
            quintile = record.get("ranking_quintile")
            comparison = (
                f" State rate: {format_number(record.get('state_rate'))}."
                + (f" Significantly different marker: {different}." if different else "")
                + (f" Ranking quintile: {quintile}." if quintile else "")
            )
        return {
            "question": question,
            "answer": (
                f"The DHSS MOPHIMS {record['profile_short_name']} profile lists {record['display_name']} "
                f"for {record['data_years']} with count {format_number(record.get('count'))} and rate {format_number(record.get('rate'))}. "
                f"Geography: {record['geography_label']}; demographic: All.{comparison}{unreliable} "
                "This is an aggregate profile value, not patient-level PAS or discharge data."
            ),
            "retrieved_context_id": f"dhss_mophims_profiles_index:{record['record_id']}",
            "retrieved_source": "dhss_mophims_profiles_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from selected local DHSS MOPHIMS ProfileBuilder page snapshots.",
            "citations": self.citation(matched_rows=1, profile_code=record["profile_code"]),
            "source_rows": [{"source_file": record["source_url"], "values": record}],
        }

    def ranking_answer(self, question: str, profile_code: int | None) -> dict[str, Any]:
        county = self.county_for_question(question)
        rows = [
            record
            for record in (self.county_records() if county is not None else self.records())
            if (profile_code is None or record["profile_code"] == profile_code)
            and (county is None or str(record.get("geography_code")) == str(county["code"]))
            and record.get("count") is not None
            and not is_total_record(record)
        ]
        rows.sort(key=lambda item: item["count"], reverse=True)
        rows = rows[:5]
        profile_label = PROFILE_SPECS[profile_code]["short_name"] if profile_code is not None else "selected MOPHIMS"
        geography_label = county_display_label(county) if county is not None else "statewide"
        rendered = "; ".join(
            f"{index}. {row['display_name']} ({row['data_years']}): {format_number(row['count'])}, rate {format_number(row.get('rate'))}"
            for index, row in enumerate(rows, start=1)
        )
        return {
            "question": question,
            "answer": (
                f"Top {geography_label} DHSS MOPHIMS {profile_label} profile counts, excluding all-cause/all-condition totals: {rendered}."
            ),
            "retrieved_context_id": f"dhss_mophims_profiles_index:top:{profile_code or 'all'}",
            "retrieved_source": "dhss_mophims_profiles_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from selected local DHSS MOPHIMS ProfileBuilder page snapshots.",
            "citations": self.citation(matched_rows=len(rows), profile_code=profile_code),
            "source_rows": [{"source_file": row["source_url"], "values": row} for row in rows],
        }

    def missing_answer(self, question: str) -> dict[str, Any]:
        county = self.county_for_question(question)
        county_note = ""
        if county is not None:
            county_note = " The requested selected county was recognized, but no indexed row matched the requested indicator."
        return {
            "question": question,
            "answer": (
                "I could not match that question to a selected statewide DHSS MOPHIMS profile row. "
                "Try asking about MOPHIMS inpatient hospitalizations, emergency room visits, leading causes of death, chronic disease comparisons, or child health profile counts."
                f"{county_note}"
            ),
            "retrieved_context_id": "dhss_mophims_profiles_index:no_match",
            "retrieved_source": "dhss_mophims_profiles_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "No row matched the selected local DHSS MOPHIMS ProfileBuilder page snapshots.",
            "citations": self.citation(matched_rows=0),
            "source_rows": [],
        }

    def answer(self, question: str) -> dict[str, Any] | None:
        if not self.available():
            return self.unavailable_answer(question)
        profile_code = self.profile_for_question(question)
        county = self.county_for_question(question)
        if asks_for_source(question):
            return self.source_answer(question)
        if asks_for_summary(question):
            if profile_code is not None:
                return self.profile_summary_answer(question, profile_code)
            return self.summary_answer(question)
        if asks_for_top(question):
            return self.ranking_answer(question, profile_code)
        record = self.find_record(question, profile_code, county=county)
        if record is not None:
            return self.record_answer(question, record)
        return self.missing_answer(question)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    payload = build_dhss_mophims_profiles_index(force=args.force)
    print(
        json.dumps(
            {key: value for key, value in payload.items() if key not in {"records", "county_records"}},
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
