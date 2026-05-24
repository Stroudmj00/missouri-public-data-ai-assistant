"""Build and query structured MERIC LAUS labor-market data."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw_public" / "meric_labor"
INDEX_PATH = RAW_DIR / "meric_labor_index.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "meric_labor_index_report.json"
LAUS_URL = "https://meric.mo.gov/data/economic/local-area-unemployment-statistics/laus"
SOURCE_PAGE_URL = "https://meric.mo.gov/data/unemployment"
MISSOURI_AREA_CODE = "2901000029"
UNITED_STATES_AREA_CODE = "0000000000"
TOTAL_SELECTED_AREAS_CODE = "9999999903"
TOTAL_SELECTED_AREAS_PREFIX = "999999990"

AREA_ALIASES = {
    "MISSOURI": ("MISSOURI", "STATE OF MISSOURI"),
    "UNITED STATES": ("US", "U S", "U.S.", "UNITED STATES"),
    "ST. LOUIS CO.": (
        "ST LOUIS",
        "ST. LOUIS",
        "SAINT LOUIS",
        "ST LOUIS COUNTY",
        "SAINT LOUIS COUNTY",
        "ST. LOUIS COUNTY",
        "ST LOUIS CO",
        "ST. LOUIS CO",
    ),
    "ST. LOUIS CITY": ("ST LOUIS CITY", "SAINT LOUIS CITY", "CITY OF ST LOUIS", "CITY OF ST. LOUIS"),
    "ST. CHARLES": ("ST CHARLES", "ST CHARLES COUNTY", "SAINT CHARLES", "SAINT CHARLES COUNTY"),
    "ST. CLAIR": ("ST CLAIR", "ST CLAIR COUNTY", "SAINT CLAIR", "SAINT CLAIR COUNTY"),
    "ST. FRANCOIS": ("ST FRANCOIS", "ST FRANCOIS COUNTY", "SAINT FRANCOIS", "SAINT FRANCOIS COUNTY"),
    "STE. GENEVIEVE": ("STE GENEVIEVE", "STE GENEVIEVE COUNTY", "SAINTE GENEVIEVE", "SAINTE GENEVIEVE COUNTY"),
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


def normalize_area(value: str) -> str:
    normalized = clean_text(value).upper()
    normalized = normalized.replace("SAINT ", "ST ")
    normalized = normalized.replace("SAINTE ", "STE ")
    normalized = re.sub(r"\s+COUNTY\b", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if normalized in {"ST LOUIS", "ST. LOUIS", "ST LOUIS COUNTY", "ST. LOUIS COUNTY", "ST LOUIS CO", "ST. LOUIS CO"}:
        return "ST. LOUIS CO."
    if normalized in {"ST LOUIS CITY", "CITY OF ST LOUIS", "CITY OF ST. LOUIS"}:
        return "ST. LOUIS CITY"
    if normalized.startswith("ST ") and "." not in normalized.split(" ", 1)[0]:
        normalized = normalized.replace("ST ", "ST. ", 1)
    if normalized.startswith("STE ") and "." not in normalized.split(" ", 1)[0]:
        normalized = normalized.replace("STE ", "STE. ", 1)
    return normalized


def display_area(value: str) -> str:
    if value == "MISSOURI":
        return "Missouri"
    if value == "UNITED STATES":
        return "United States"
    return clean_text(value).title().replace("Co.", "County").replace("St.", "St.").replace("Ste.", "Ste.")


def number_label(value: int | float, metric: str) -> str:
    if metric == "unemployment_rate":
        return f"{float(value):.1f}%"
    return f"{int(value):,}"


def form_build_id(page_text: str) -> str:
    matches = re.findall(r'name="form_build_id" value="([^"]+)"', page_text)
    if not matches:
        raise ValueError("MERIC LAUS form_build_id was not found")
    return matches[-1]


def selected_year(page_text: str) -> int:
    match = re.search(r'<select[^>]+name="years\[\]"[^>]*>.*?<option\s+value="(\d{4})"\s+selected="selected"', page_text, re.I | re.S)
    if match:
        return int(match.group(1))
    match = re.search(r'<select[^>]+name="years\[\]"[^>]*>.*?<option\s+value="(\d{4})"', page_text, re.I | re.S)
    if not match:
        raise ValueError("MERIC LAUS year options were not found")
    return int(match.group(1))


def csv_response_rows(response: requests.Response) -> tuple[str, list[dict[str, str]]]:
    content_type = response.headers.get("content-type", "")
    text = response.text
    if "text/csv" not in content_type or not text.startswith("AreaCode,AreaName"):
        raise ValueError(f"Expected MERIC CSV response, got {content_type}: {text[:160]!r}")
    return text, list(csv.DictReader(io.StringIO(text)))


def post_download_csv(
    session: requests.Session,
    form_id_value: str,
    seasonal_adjustment: str,
    area_general: str,
    years: list[int],
    months: list[str],
    area_sub: list[str] | None = None,
) -> tuple[str, list[dict[str, str]]]:
    data: list[tuple[str, str]] = [
        ("form_id", "laus_form"),
        ("form_build_id", form_id_value),
        ("seasonal_adjustment", seasonal_adjustment),
        ("area_general", area_general),
        ("format", "csv"),
        ("op", "Download"),
    ]
    for year in years:
        data.append(("years[]", str(year)))
    for month in months:
        data.append(("months[]", month))
    for area in area_sub or []:
        data.append(("area_sub[]", area))
    response = session.post(LAUS_URL, data=data, timeout=90)
    response.raise_for_status()
    return csv_response_rows(response)


def ajax_update(
    session: requests.Session,
    form_id_value: str,
    seasonal_adjustment: str,
    area_general: str,
    trigger: str,
    year: int,
) -> tuple[str, str]:
    data = {
        "form_id": "laus_form",
        "form_build_id": form_id_value,
        "seasonal_adjustment": seasonal_adjustment,
        "area_general": area_general,
        "months[]": "13",
        "years[]": str(year),
        "_triggering_element_name": trigger,
    }
    response = session.post(
        f"{LAUS_URL}?ajax_form=1",
        data=data,
        headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json, text/javascript, */*; q=0.01"},
        timeout=90,
    )
    response.raise_for_status()
    response_text = response.text.strip()
    if response_text.startswith("<textarea>") and response_text.endswith("</textarea>"):
        response_text = re.sub(r"^<textarea>|</textarea>$", "", response_text, flags=re.I)
    commands = json.loads(response_text)
    new_id = form_id_value
    html_parts: list[str] = []
    for command in commands:
        if command.get("command") == "update_build_id":
            new_id = command.get("new") or new_id
        if command.get("data"):
            html_parts.append(str(command["data"]))
    return new_id, "\n".join(html_parts)


def county_options(session: requests.Session, page_text: str, year: int) -> tuple[str, list[dict[str, str]]]:
    build_id = form_build_id(page_text)
    build_id, _ = ajax_update(session, build_id, "not_adjusted", MISSOURI_AREA_CODE, "seasonal_adjustment", year)
    build_id, html_text = ajax_update(session, build_id, "not_adjusted", "counties", "area_general", year)
    select_match = re.search(r'<select[^>]+name="area_sub\[\]"[^>]*>(.*?)</select>', html_text, re.I | re.S)
    if not select_match:
        raise ValueError("MERIC county area_sub options were not found")
    options = []
    for value, label in re.findall(r'<option[^>]+value="([^"]+)"[^>]*>(.*?)</option>', select_match.group(1), re.I | re.S):
        options.append({"area_code": value, "area_name": clean_text(re.sub(r"<[^>]+>", " ", label))})
    if not options:
        raise ValueError("MERIC county option list was empty")
    return build_id, options


def row_to_record(row: dict[str, str], source_file: str, source_sha256: str) -> dict[str, Any] | None:
    area_code = clean_text(row.get("AreaCode"))
    area_name = clean_text(row.get("AreaName"))
    row_type = clean_text(row.get("RowType"))
    if (
        area_code == TOTAL_SELECTED_AREAS_CODE
        or area_code.startswith(TOTAL_SELECTED_AREAS_PREFIX)
        or "total, selected areas" in area_name.lower()
    ):
        return None
    if row_type and row_type != "1":
        return None
    area_norm = normalize_area(area_name)
    seasonal = clean_text(row.get("SeasonalAdjustment"))
    return {
        "area_code": area_code,
        "area_name": area_name,
        "area_norm": area_norm,
        "area_type": "state" if area_norm == "MISSOURI" else "national" if area_norm == "UNITED STATES" else "county",
        "year": int(row["Year"]),
        "month": clean_text(row.get("Month")),
        "period": clean_text(row.get("Period")),
        "period_type": clean_text(row.get("PeriodType")),
        "labor_force": int(row["LaborForce"]),
        "employment": int(row["Employment"]),
        "unemployed": int(row["Unemployment"]),
        "unemployment_rate": round(float(row["UnemploymentRate"]), 1),
        "seasonal_adjustment": seasonal,
        "seasonal_key": "adjusted" if "seasonally adjusted" in seasonal.lower() and not seasonal.lower().startswith("not") else "not_adjusted",
        "row_type": int(row_type or 0),
        "source_file": source_file,
        "source_url": LAUS_URL,
        "source_sha256": source_sha256,
    }


def build_meric_labor_index(force: bool = False, county_chunk_size: int = 5) -> dict[str, Any]:
    if INDEX_PATH.exists() and not force:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (compatible; MissouriPublicDataChat/1.0; +https://github.com/Stroudmj00/missouri-tiny-llm-case-study)",
            "Accept": "text/html,text/csv;q=0.9,*/*;q=0.8",
        }
    )
    start = time.perf_counter()
    page_response = session.get(LAUS_URL, timeout=60)
    page_response.raise_for_status()
    page_text = page_response.text
    year = selected_year(page_text)
    build_id = form_build_id(page_text)
    raw_files: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []

    for seasonal_key in ["adjusted", "not_adjusted"]:
        csv_text, rows = post_download_csv(
            session,
            build_id,
            seasonal_key,
            MISSOURI_AREA_CODE,
            years=[year],
            months=["13"],
        )
        file_name = f"meric_laus_missouri_{seasonal_key}_{year}.csv"
        sha = sha256_text(csv_text)
        (RAW_DIR / file_name).parent.mkdir(parents=True, exist_ok=True)
        (RAW_DIR / file_name).write_text(csv_text, encoding="utf-8")
        parsed = [record for row in rows if (record := row_to_record(row, file_name, sha)) is not None]
        records.extend(parsed)
        raw_files.append(
            {
                "key": f"missouri_{seasonal_key}",
                "label": f"MERIC LAUS Missouri {seasonal_key.replace('_', ' ')} CSV",
                "file_name": file_name,
                "url": LAUS_URL,
                "bytes": len(csv_text.encode("utf-8")),
                "sha256": sha,
                "record_count": len(parsed),
                "year": year,
            }
        )

    fresh_page_response = session.get(LAUS_URL, timeout=60)
    fresh_page_response.raise_for_status()
    _county_build_id, counties = county_options(session, fresh_page_response.text, year)
    for chunk_index in range(0, len(counties), county_chunk_size):
        chunk = counties[chunk_index : chunk_index + county_chunk_size]
        # The Drupal form token can be consumed by a CSV download, so refresh the
        # county flow for every safe-sized chunk.
        chunk_page_response = session.get(LAUS_URL, timeout=60)
        chunk_page_response.raise_for_status()
        county_build_id, _ = county_options(session, chunk_page_response.text, year)
        csv_text, rows = post_download_csv(
            session,
            county_build_id,
            "not_adjusted",
            "counties",
            years=[year],
            months=["13"],
            area_sub=[item["area_code"] for item in chunk],
        )
        file_name = f"meric_laus_counties_not_adjusted_{year}_{chunk_index // county_chunk_size + 1:02d}.csv"
        sha = sha256_text(csv_text)
        (RAW_DIR / file_name).write_text(csv_text, encoding="utf-8")
        parsed = [record for row in rows if (record := row_to_record(row, file_name, sha)) is not None]
        records.extend(parsed)
        raw_files.append(
            {
                "key": f"counties_not_adjusted_{chunk_index // county_chunk_size + 1:02d}",
                "label": "MERIC LAUS county not seasonally adjusted CSV chunk",
                "file_name": file_name,
                "url": LAUS_URL,
                "bytes": len(csv_text.encode("utf-8")),
                "sha256": sha,
                "record_count": len(parsed),
                "year": year,
                "area_count": len(chunk),
            }
        )
        time.sleep(0.05)

    months = sorted({record["period"] for record in records})
    payload = {
        "generated_at_utc": utc_now(),
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "source": "MERIC Local Area Unemployment Statistics",
        "source_url": LAUS_URL,
        "index_path": str(INDEX_PATH.relative_to(PROJECT_ROOT)),
        "file_count": len(raw_files),
        "record_count": len(records),
        "area_count": len({record["area_norm"] for record in records}),
        "county_count": len({record["area_norm"] for record in records if record["area_type"] == "county"}),
        "year": year,
        "months": months,
        "files": raw_files,
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
            "index_path": payload["index_path"],
            "file_count": payload["file_count"],
            "record_count": payload["record_count"],
            "area_count": payload["area_count"],
            "county_count": payload["county_count"],
            "year": payload["year"],
            "months": payload["months"],
            "files": raw_files,
        },
    )
    return payload


def metric_for_question(question: str) -> tuple[str, str]:
    lowered = question.lower()
    if "labor force" in lowered or "workforce" in lowered:
        return "labor_force", "labor force"
    if ("employment" in lowered and "unemployment" not in lowered) or ("employed" in lowered and "unemployed" not in lowered):
        return "employment", "employment"
    if "unemployed" in lowered or "unemployment count" in lowered or "number unemployed" in lowered:
        return "unemployed", "unemployed people"
    return "unemployment_rate", "unemployment rate"


def requested_month_for_question(question: str, months: list[str]) -> str | None:
    lowered = question.lower()
    month_names = {
        "january": "01",
        "february": "02",
        "march": "03",
        "april": "04",
        "may": "05",
        "june": "06",
        "july": "07",
        "august": "08",
        "september": "09",
        "october": "10",
        "november": "11",
        "december": "12",
    }
    for name, period in month_names.items():
        if name in lowered:
            return period if period in months else "missing"
    return None


def years_for_question(question: str) -> list[int]:
    return sorted({int(year) for year in re.findall(r"\b(19\d{2}|20\d{2})\b", question)})


def seasonal_for_question(question: str, area_norm: str) -> str:
    lowered = question.lower()
    if "seasonally adjusted" in lowered and "not seasonally adjusted" not in lowered:
        return "adjusted"
    if "not seasonally adjusted" in lowered or "unadjusted" in lowered:
        return "not_adjusted"
    return "adjusted" if area_norm == "MISSOURI" else "not_adjusted"


def asks_for_top(question: str) -> bool:
    lowered = question.lower()
    return any(word in lowered for word in ["top", "highest", "largest", "most", "biggest", "lowest", "smallest"])


def asks_for_lowest(question: str) -> bool:
    lowered = question.lower()
    return any(word in lowered for word in ["lowest", "smallest"])


class MericLaborIndex:
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

    def file_info(self, file_name: str) -> dict[str, Any] | None:
        for item in self.payload().get("files", []):
            if item.get("file_name") == file_name:
                return item
        return None

    def coverage_citation(self, matched_rows: int = 0) -> list[dict[str, Any]]:
        files = self.payload().get("files", [])
        return [
            {
                "dataset": "MERIC Local Area Unemployment Statistics",
                "category": "Labor market",
                "kind": "LAUS structured CSV coverage",
                "lookup_table": "meric_labor_index",
                "year": self.payload().get("year"),
                "year_range": str(self.payload().get("year")),
                "source_files": [
                    {
                        "category": item.get("key"),
                        "category_label": item.get("label"),
                        "file_name": item.get("url"),
                        "row_count": item.get("record_count"),
                        "bytes": item.get("bytes"),
                        "sha256": item.get("sha256"),
                    }
                    for item in files[:5]
                ],
                "source_file_count": len(files),
                "source_rows": sum(item.get("record_count") or 0 for item in files),
                "matched_rows": matched_rows,
            }
        ]

    def citation(self, record: dict[str, Any], matched_rows: int = 1) -> list[dict[str, Any]]:
        file_info = self.file_info(record["source_file"]) or {}
        return [
            {
                "dataset": "MERIC Local Area Unemployment Statistics",
                "category": "Labor market",
                "kind": "LAUS structured CSV row",
                "lookup_table": "meric_labor_index",
                "year": record["year"],
                "year_range": str(self.payload().get("year")),
                "source_files": [
                    {
                        "category": file_info.get("key"),
                        "category_label": file_info.get("label"),
                        "file_name": LAUS_URL,
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

    def summary_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        month_names = ", ".join(payload.get("months", []))
        return {
            "question": question,
            "answer": (
                f"The MERIC exact lookup layer is built from structured LAUS CSV downloads with "
                f"{payload.get('record_count', 0):,} aggregate rows across {payload.get('area_count', 0):,} areas "
                f"({payload.get('county_count', 0):,} counties) for {payload.get('year')}. "
                f"Indexed month periods: {month_names}. It can answer unemployment rate, labor force, employment, "
                "and unemployed-count questions for Missouri and indexed counties."
            ),
            "retrieved_context_id": "meric_labor_index:summary",
            "retrieved_source": "meric_labor_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local MERIC LAUS index.",
            "citations": self.coverage_citation(matched_rows=payload.get("record_count", 0)),
            "source_rows": [],
        }

    def unavailable_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "The MERIC labor-force index has not been built yet. Run "
                "`python scripts/build_meric_labor_index.py --force` to download structured public LAUS CSV data and build exact lookups."
            ),
            "retrieved_context_id": "meric_labor_index:missing",
            "retrieved_source": "meric_labor_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "The MERIC source route exists, but the local ignored index is missing.",
            "citations": [],
            "source_rows": [],
        }

    def find_area(self, question: str) -> str | None:
        question_norm = normalize_area(question)
        if re.search(r"\bmissouri\b", question, flags=re.I):
            return "MISSOURI"
        by_area = sorted({record["area_norm"] for record in self.records()}, key=len, reverse=True)
        for area in by_area:
            aliases = [area, *(normalize_area(alias) for alias in AREA_ALIASES.get(area, ()))]
            if not area.endswith(("CITY", "CO.")) and area not in {"MISSOURI", "UNITED STATES"}:
                aliases.append(f"{area} COUNTY")
            for alias in aliases:
                if re.search(rf"\b{re.escape(alias)}\b", question_norm):
                    return area
        return None

    def matching_row(self, area_norm: str, period: str, seasonal_key: str) -> dict[str, Any] | None:
        rows = [
            record
            for record in self.records()
            if record["area_norm"] == area_norm and record["period"] == period and record["seasonal_key"] == seasonal_key
        ]
        if rows:
            return rows[0]
        if seasonal_key == "adjusted":
            for record in self.records():
                if record["area_norm"] == area_norm and record["period"] == period and record["seasonal_key"] == "not_adjusted":
                    return record
        return None

    def latest_period(
        self,
        area_norm: str | None = None,
        seasonal_key: str | None = None,
        area_type: str | None = None,
    ) -> str | None:
        periods = sorted(
            {
                record["period"]
                for record in self.records()
                if (area_norm is None or record["area_norm"] == area_norm)
                and (seasonal_key is None or record["seasonal_key"] == seasonal_key)
                and (area_type is None or record["area_type"] == area_type)
            }
        )
        return periods[-1] if periods else None

    def rank_answer(self, question: str, period: str, metric: str, metric_label: str) -> dict[str, Any] | None:
        rows = [
            record
            for record in self.records()
            if record["area_type"] == "county" and record["period"] == period and record["seasonal_key"] == "not_adjusted"
        ]
        if not rows:
            return None
        reverse = not asks_for_lowest(question)
        ranked = sorted(rows, key=lambda item: float(item[metric]), reverse=reverse)
        top = ranked[0]
        direction = "highest" if reverse else "lowest"
        rendered = "; ".join(f"{display_area(row['area_norm'])}: {number_label(row[metric], metric)}" for row in ranked[:5])
        return {
            "question": question,
            "answer": (
                f"In the indexed MERIC LAUS data for {top['month']} {top['year']}, the {direction} county "
                f"{metric_label} is {display_area(top['area_norm'])}: {number_label(top[metric], metric)}. "
                f"Top matching counties: {rendered}."
            ),
            "retrieved_context_id": f"meric_labor_index:rank:{period}:{metric}:{direction}",
            "retrieved_source": "meric_labor_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed by ranking county rows in the local MERIC LAUS index.",
            "citations": self.citation(top, matched_rows=len(rows)),
            "source_rows": [{"source_file": top["source_file"], "values": top}],
        }

    def missing_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "I have exact MERIC LAUS data for Missouri and indexed counties, but I could not match this question "
                f"to a supported area, metric, or indexed period. Indexed year: {self.payload().get('year')}; "
                f"indexed month periods: {', '.join(self.payload().get('months', []))}."
            ),
            "retrieved_context_id": "meric_labor_index:no_match",
            "retrieved_source": "meric_labor_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Answered from MERIC coverage metadata because no exact aggregate row matched.",
            "citations": self.coverage_citation(),
            "source_rows": [],
        }

    def answer(self, question: str) -> dict[str, Any] | None:
        if not self.available():
            return self.unavailable_answer(question)
        lowered = question.lower()
        if (
            re.search(r"\b(what|which|show|list)\b.*\b(meric|labor|unemployment)\b.*\b(data|reports?|indexed|connected|sources?)\b", lowered)
            or re.search(r"\b(meric|labor|unemployment)\b.*\b(data|reports?)\b.*\b(indexed|connected|available)\b", lowered)
        ):
            return self.summary_answer(question)
        requested_years = years_for_question(question)
        indexed_year = self.payload().get("year")
        if requested_years and indexed_year not in requested_years:
            return self.missing_answer(question)
        requested_period = requested_month_for_question(question, self.payload().get("months", []))
        if requested_period == "missing":
            return self.missing_answer(question)
        metric, metric_label = metric_for_question(question)
        if asks_for_top(question):
            period = requested_period or self.latest_period(area_type="county", seasonal_key="not_adjusted")
            if period is None:
                return self.missing_answer(question)
            ranked = self.rank_answer(question, period, metric, metric_label)
            if ranked is not None:
                return ranked
        area_norm = self.find_area(question)
        if area_norm is None:
            return self.missing_answer(question)
        seasonal_key = seasonal_for_question(question, area_norm)
        period = requested_period or self.latest_period(area_norm=area_norm, seasonal_key=seasonal_key)
        if period is None:
            return self.missing_answer(question)
        record = self.matching_row(area_norm, period, seasonal_key)
        if record is None:
            return self.missing_answer(question)
        return {
            "question": question,
            "answer": (
                f"The indexed MERIC LAUS data lists {display_area(record['area_norm'])} {metric_label} "
                f"for {record['month']} {record['year']} as {number_label(record[metric], metric)}. "
                f"Labor force: {record['labor_force']:,}; employment: {record['employment']:,}; "
                f"unemployed: {record['unemployed']:,}; unemployment rate: {record['unemployment_rate']:.1f}%. "
                f"Seasonal adjustment: {record['seasonal_adjustment']}."
            ),
            "retrieved_context_id": f"meric_labor_index:{record['area_norm']}:{record['year']}:{record['period']}:{record['seasonal_key']}:{metric}",
            "retrieved_source": "meric_labor_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local MERIC LAUS structured CSV index.",
            "citations": self.citation(record),
            "source_rows": [{"source_file": record["source_file"], "values": record}],
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--county-chunk-size", type=int, default=5)
    args = parser.parse_args()
    payload = build_meric_labor_index(force=args.force, county_chunk_size=args.county_chunk_size)
    print(json.dumps({key: value for key, value in payload.items() if key != "records"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
