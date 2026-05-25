"""Build and query selected DHSS statewide and county vital-statistics aggregates."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from pypdf import PdfReader


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw_public" / "dhss_vital_stats"
INDEX_PATH = RAW_DIR / "dhss_vital_stats_index.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "dhss_vital_stats_index_report.json"
FOCUS_PAGE = "https://health.mo.gov/data/focus/"
VITAL_STATS_DATA_PAGE = "https://health.mo.gov/data/vitalstatistics/data.php"
SOURCE_NAME = "DHSS Vital Statistics Focus Report"

MEASURE_ALIASES = {
    "births": ["birth", "births", "live birth", "live births", "infants born"],
    "deaths": ["death", "deaths", "resident deaths"],
    "natural increase": ["natural increase", "births outnumbered deaths"],
    "infant deaths": ["infant death", "infant deaths", "infant mortality"],
    "marriages": ["marriage", "marriages"],
    "divorces": ["divorce", "divorces"],
    "population": ["population"],
}

TABLE_1_MEASURES = tuple(MEASURE_ALIASES.keys())


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def parse_number(value: str) -> float | None:
    cleaned = value.replace(",", "").replace("*", "").strip()
    if re.fullmatch(r"-?\d+(?:\.\d+)?", cleaned):
        return float(cleaned)
    return None


def format_count(value: float | int | None) -> str:
    if value is None:
        return "not listed"
    return f"{int(value):,}" if float(value).is_integer() else f"{float(value):,.1f}"


def format_rate(value: float | int | None) -> str:
    if value is None:
        return "not listed"
    return f"{float(value):.1f}"


def safe_record_id(measure: str, year: int) -> str:
    return hashlib.sha1(f"{measure}:{year}".encode("utf-8")).hexdigest()[:16]


def safe_county_record_id(area: str, year: int) -> str:
    return hashlib.sha1(f"table16a:{area}:{year}".encode("utf-8")).hexdigest()[:16]


def normalize_area_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def download_text(url: str, path: Path, force: bool = False) -> str:
    session = requests.Session()
    session.headers.update({"User-Agent": "missouri-tiny-llm-case-study/1.0"})
    if force or not path.exists():
        response = session.get(url, timeout=60)
        response.raise_for_status()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(response.text, encoding="utf-8")
    return path.read_text(encoding="utf-8", errors="replace")


def download_bytes(url: str, path: Path, force: bool = False) -> bytes:
    session = requests.Session()
    session.headers.update({"User-Agent": "missouri-tiny-llm-case-study/1.0"})
    if force or not path.exists():
        response = session.get(url, timeout=90)
        response.raise_for_status()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(response.content)
    return path.read_bytes()


def discover_latest_vital_pdf(page_html: str) -> tuple[int, str, str]:
    candidates: list[tuple[int, str, str]] = []
    for match in re.finditer(
        r'href="(?P<href>[^"]+\.pdf)"[^>]*>\s*(?P<label>(?P<year>20\d{2})\s+Vital Statistics)',
        page_html,
        flags=re.IGNORECASE,
    ):
        year = int(match.group("year"))
        url = urljoin(FOCUS_PAGE, match.group("href"))
        candidates.append((year, match.group("label"), url))
    if not candidates:
        raise ValueError("Could not find a Vital Statistics PDF link on the DHSS FOCUS page")
    return sorted(candidates, key=lambda item: item[0], reverse=True)[0]


def discover_latest_annual_report(page_html: str) -> tuple[int, str, str]:
    candidates: list[tuple[int, str, str]] = []
    for match in re.finditer(
        r'href="(?P<href>[^"]*mvs(?P<yy>\d{2})/Preface\.pdf)"[^>]*>\s*(?P<year>20\d{2})\s*<',
        page_html,
        flags=re.IGNORECASE,
    ):
        year = int(match.group("year"))
        full_report = urljoin(VITAL_STATS_DATA_PAGE, f"mvs{str(year)[-2:]}/{year}MissouriVitalStatistics.pdf")
        candidates.append((year, f"{year} Missouri Vital Statistics", full_report))
    if not candidates:
        raise ValueError("Could not find an annual Missouri Vital Statistics report link")
    return sorted(candidates, key=lambda item: item[0], reverse=True)[0]


def extract_pdf_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def years_from_table_header(text: str, report_year: int) -> list[int]:
    match = re.search(r"Numbers Rates per 1,000 Population\s+((?:\d{4}\s+){5}\d{4})", text)
    if not match:
        return [report_year - 10, report_year - 1, report_year]
    header_years = [int(value) for value in re.findall(r"\d{4}", match.group(1))]
    return header_years[:3] if len(header_years) >= 3 else [report_year - 10, report_year - 1, report_year]


def parse_table_1(text: str, report_year: int, pdf_url: str) -> list[dict[str, Any]]:
    table_text = text.split("continued on page 2", 1)[0]
    years = years_from_table_header(table_text, report_year)
    records: list[dict[str, Any]] = []
    row_pattern = re.compile(
        r"^(Births|Deaths|Natural increase|Marriages|Divorces|Infant deaths|Population \(1,000s\))\s+(.+)$",
        re.MULTILINE,
    )
    for match in row_pattern.finditer(table_text):
        label = match.group(1)
        measure = "population" if label.startswith("Population") else label.lower()
        values = re.findall(r"-?\d[\d,]*(?:\.\d+)?\*?", match.group(2))
        counts = [parse_number(value) for value in values[:3]]
        rates = [parse_number(value) for value in values[3:6]]
        for index, year in enumerate(years):
            count = counts[index] if index < len(counts) else None
            rate = rates[index] if index < len(rates) else None
            if count is None:
                continue
            rate_unit = None
            if measure == "infant deaths":
                rate_unit = "per 1,000 live births"
            elif measure != "population":
                rate_unit = "per 1,000 population"
            records.append(
                {
                    "record_id": safe_record_id(measure, year),
                    "measure": measure,
                    "year": year,
                    "count": count,
                    "rate": rate,
                    "rate_unit": rate_unit,
                    "source_url": pdf_url,
                    "source_table": "Table 1: Vital Statistics for Missouri",
                }
            )
    return records


def parse_int(value: str) -> int:
    return int(value.replace(",", "").strip())


def parse_table_16a_county_records(pdf_path: Path, report_year: int, pdf_url: str) -> list[dict[str, Any]]:
    reader = PdfReader(str(pdf_path))
    records: list[dict[str, Any]] = []
    row_pattern = re.compile(
        r"^(?P<area>[A-Za-z. ]+?)\s+"
        r"(?P<population>-?\d[\d,]*)\s+"
        r"(?P<resident_live_births>-?\d[\d,]*)\s+"
        r"(?P<resident_deaths>-?\d[\d,]*)\s+"
        r"(?P<natural_increase>-?\d[\d,]*)\s+"
        r"(?P<recorded_live_births>-?\d[\d,]*)\s+"
        r"(?P<recorded_deaths>-?\d[\d,]*)\s+"
        r"(?P<resident_birth_rate>-?\d+(?:\.\d+)?)\s+"
        r"(?P<resident_death_rate>-?\d+(?:\.\d+)?)\s+"
        r"(?P<natural_increase_rate>-?\d+(?:\.\d+)?)$"
    )
    for page_index, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if "Table 16A." not in text:
            continue
        for raw_line in text.splitlines():
            line = clean_text(raw_line)
            match = row_pattern.match(line)
            if not match:
                continue
            area = clean_text(match.group("area"))
            if area in {"Counties", "Population"}:
                continue
            area_type = "state" if area == "State Total" else "county"
            label = "Missouri" if area_type == "state" else f"{area} County"
            if area.endswith("City") or area.endswith("County"):
                label = area
            records.append(
                {
                    "record_id": safe_county_record_id(area, report_year),
                    "area": area,
                    "area_label": label,
                    "area_norm": normalize_area_name(label),
                    "area_type": area_type,
                    "year": report_year,
                    "population": parse_int(match.group("population")),
                    "resident_live_births": parse_int(match.group("resident_live_births")),
                    "resident_deaths": parse_int(match.group("resident_deaths")),
                    "natural_increase": parse_int(match.group("natural_increase")),
                    "recorded_live_births": parse_int(match.group("recorded_live_births")),
                    "recorded_deaths": parse_int(match.group("recorded_deaths")),
                    "resident_birth_rate": float(match.group("resident_birth_rate")),
                    "resident_death_rate": float(match.group("resident_death_rate")),
                    "natural_increase_rate": float(match.group("natural_increase_rate")),
                    "source_url": pdf_url,
                    "source_table": "Table 16A: Resident and Recorded Live Births, Deaths, and Natural Increase by County",
                    "source_page_index": page_index,
                }
            )
    return records


def build_dhss_vital_stats_index(force: bool = False) -> dict[str, Any]:
    if INDEX_PATH.exists() and not force:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))

    start = time.perf_counter()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    page_path = RAW_DIR / "focus.html"
    page_html = download_text(FOCUS_PAGE, page_path, force=force)
    report_year, label, pdf_url = discover_latest_vital_pdf(page_html)
    pdf_path = RAW_DIR / Path(pdf_url).name
    pdf_bytes = download_bytes(pdf_url, pdf_path, force=force)
    pdf_text = extract_pdf_text(pdf_path)
    records = parse_table_1(pdf_text, report_year, pdf_url)
    annual_page_path = RAW_DIR / "vitalstatistics_data.html"
    annual_page_html = download_text(VITAL_STATS_DATA_PAGE, annual_page_path, force=force)
    annual_year, annual_label, annual_report_url = discover_latest_annual_report(annual_page_html)
    annual_pdf_path = RAW_DIR / Path(annual_report_url).name
    annual_pdf_bytes = download_bytes(annual_report_url, annual_pdf_path, force=force)
    county_records = parse_table_16a_county_records(annual_pdf_path, annual_year, annual_report_url)
    years = sorted({record["year"] for record in records})
    measures = sorted({record["measure"] for record in records})
    payload = {
        "generated_at_utc": utc_now(),
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "source": SOURCE_NAME,
        "focus_page": FOCUS_PAGE,
        "report_label": label,
        "report_year": report_year,
        "report_url": pdf_url,
        "annual_report_label": annual_label,
        "annual_report_year": annual_year,
        "annual_report_url": annual_report_url,
        "index_path": str(INDEX_PATH.relative_to(PROJECT_ROOT)),
        "record_count": len(records),
        "county_record_count": len(county_records),
        "years": years,
        "measures": measures,
        "files": {
            "focus_page": {
                "url": FOCUS_PAGE,
                "local_file": str(page_path.relative_to(PROJECT_ROOT)),
                "bytes": len(page_html.encode("utf-8", errors="replace")),
                "sha256": hashlib.sha256(page_html.encode("utf-8", errors="replace")).hexdigest(),
            },
            "report_pdf": {
                "url": pdf_url,
                "local_file": str(pdf_path.relative_to(PROJECT_ROOT)),
                "bytes": len(pdf_bytes),
                "sha256": sha256_bytes(pdf_bytes),
            },
            "annual_reports_page": {
                "url": VITAL_STATS_DATA_PAGE,
                "local_file": str(annual_page_path.relative_to(PROJECT_ROOT)),
                "bytes": len(annual_page_html.encode("utf-8", errors="replace")),
                "sha256": hashlib.sha256(annual_page_html.encode("utf-8", errors="replace")).hexdigest(),
            },
            "annual_report_pdf": {
                "url": annual_report_url,
                "local_file": str(annual_pdf_path.relative_to(PROJECT_ROOT)),
                "bytes": len(annual_pdf_bytes),
                "sha256": sha256_bytes(annual_pdf_bytes),
            },
        },
        "notes": [
            "This index parses Table 1 from the latest DHSS Vital Statistics FOCUS PDF found on the official FOCUS page.",
            "It also parses Table 16A from the latest annual Missouri Vital Statistics PDF for county resident/recorded births, deaths, and natural increase.",
            "It stores statewide and county aggregate counts and rates for selected vital-statistics measures only.",
            "It does not parse vital-record certificates, patient/person records, city tables, demographic slices, or MOPHIMS/MICA query results.",
        ],
        "records": records,
        "county_records": county_records,
    }
    write_json(INDEX_PATH, payload)
    latest_year = max(years) if years else report_year
    write_json(
        REPORT_PATH,
        {
            key: value
            for key, value in payload.items()
            if key not in {"records", "county_records"}
        }
        | {
            "latest_year_records": [
                {
                    "measure": record["measure"],
                    "year": record["year"],
                    "count": record["count"],
                    "rate": record["rate"],
                    "rate_unit": record["rate_unit"],
                }
                for record in records
                if record["year"] == latest_year
            ],
            "county_examples": [
                {
                    "area_label": record["area_label"],
                    "resident_live_births": record["resident_live_births"],
                    "resident_deaths": record["resident_deaths"],
                    "natural_increase": record["natural_increase"],
                    "resident_birth_rate": record["resident_birth_rate"],
                    "resident_death_rate": record["resident_death_rate"],
                }
                for record in county_records
                if record["area_type"] == "county" and record["area"] in {"Boone", "Cole", "Greene", "Jackson"}
            ],
            "top_counties_by_resident_live_births": [
                {
                    "area_label": record["area_label"],
                    "resident_live_births": record["resident_live_births"],
                    "resident_birth_rate": record["resident_birth_rate"],
                }
                for record in sorted(
                    [record for record in county_records if record["area_type"] == "county"],
                    key=lambda item: item["resident_live_births"],
                    reverse=True,
                )[:5]
            ],
            "top_counties_by_resident_deaths": [
                {
                    "area_label": record["area_label"],
                    "resident_deaths": record["resident_deaths"],
                    "resident_death_rate": record["resident_death_rate"],
                }
                for record in sorted(
                    [record for record in county_records if record["area_type"] == "county"],
                    key=lambda item: item["resident_deaths"],
                    reverse=True,
                )[:5]
            ],
        },
    )
    return payload


def asks_for_summary(question: str) -> bool:
    lowered = question.lower()
    if "focus report" in lowered or "focus reports" in lowered:
        return False
    return any(term in lowered for term in ["indexed", "coverage", "what data", "available", "summary"])


def asks_for_source(question: str) -> bool:
    lowered = question.lower()
    return "source" in lowered and any(term in lowered for term in ["aggregate", "index", "indexed"])


def asks_for_latest_year(question: str) -> bool:
    lowered = question.lower()
    return "latest" in lowered and "year" in lowered


class DhssVitalStatsIndex:
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

    def citation(self, matched_rows: int = 0) -> list[dict[str, Any]]:
        payload = self.payload()
        files = payload.get("files", {})
        return [
            {
                "dataset": payload.get("source", SOURCE_NAME),
                "category": "Public health",
                "kind": "DHSS vital statistics aggregate lookup",
                "lookup_table": "dhss_vital_stats_index",
                "year": payload.get("report_year"),
                "year_range": (
                    ", ".join(str(year) for year in payload.get("years", []))
                    if payload.get("years")
                    else None
                ),
                "source_files": [
                    {
                        "category": key,
                        "category_label": key.replace("_", " ").title(),
                        "file_name": value.get("url"),
                        "row_count": (
                            payload.get("record_count")
                            if key == "report_pdf"
                            else payload.get("county_record_count")
                            if key == "annual_report_pdf"
                            else None
                        ),
                        "bytes": value.get("bytes"),
                        "sha256": value.get("sha256"),
                    }
                    for key, value in files.items()
                ],
                "source_file_count": len(files),
                "source_rows": payload.get("record_count", 0) + payload.get("county_record_count", 0),
                "matched_rows": matched_rows,
            }
        ]

    def unavailable_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "The DHSS vital-statistics aggregate index has not been built yet. Run "
                "`python scripts/build_dhss_vital_stats_index.py --force` to index the official FOCUS report."
            ),
            "retrieved_context_id": "dhss_vital_stats_index:missing",
            "retrieved_source": "dhss_vital_stats_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "citations": [],
            "source_rows": [],
        }

    def summary_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        measures = ", ".join(payload.get("measures", []))
        years = payload.get("years", [])
        year_text = ", ".join(str(year) for year in years) if years else "the indexed report years"
        return {
            "question": question,
            "answer": (
                f"The DHSS vital-statistics exact aggregate layer indexes {payload.get('record_count', 0)} statewide Table 1 row(s) "
                f"from the {payload.get('report_label')} FOCUS PDF for {year_text}. It also indexes "
                f"{payload.get('county_record_count', 0)} Table 16A county/state row(s) from the "
                f"{payload.get('annual_report_label', 'annual Missouri Vital Statistics report')}. Measures: {measures}. "
                "It returns aggregate counts and rates only; it does not parse vital-record certificates, "
                "person records, city tables, demographic slices, or MOPHIMS/MICA query results."
            ),
            "retrieved_context_id": "dhss_vital_stats_index:summary",
            "retrieved_source": "dhss_vital_stats_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local DHSS Vital Statistics FOCUS report index.",
            "citations": self.citation(matched_rows=payload.get("record_count", 0)),
            "source_rows": [],
        }

    def latest_year_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        latest_year = max(payload.get("years", []) or [payload.get("report_year")])
        return {
            "question": question,
            "answer": (
                f"The latest year parsed in the DHSS vital-statistics aggregate index is {latest_year}, "
                f"from the {payload.get('report_label')} FOCUS PDF."
            ),
            "retrieved_context_id": f"dhss_vital_stats_index:latest_year:{latest_year}",
            "retrieved_source": "dhss_vital_stats_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local DHSS Vital Statistics FOCUS report index.",
            "citations": self.citation(matched_rows=0),
            "source_rows": [],
        }

    def match_measure(self, question: str) -> str | None:
        lowered = question.lower()
        for measure, aliases in MEASURE_ALIASES.items():
            if any(alias in lowered for alias in aliases):
                return measure
        return None

    def county_measure(self, question: str) -> str | None:
        lowered = question.lower()
        if "natural increase" in lowered:
            return "natural_increase"
        if "birth rate" in lowered:
            return "resident_birth_rate"
        if "death rate" in lowered:
            return "resident_death_rate"
        if any(term in lowered for term in ["live birth", "births", "birth"]):
            return "resident_live_births"
        if any(term in lowered for term in ["deaths", "death"]):
            return "resident_deaths"
        return None

    def requested_year(self, question: str) -> int | None:
        years = [int(match) for match in re.findall(r"\b(20\d{2}|19\d{2})\b", question)]
        return years[-1] if years else None

    def record_for(self, measure: str, year: int | None) -> dict[str, Any] | None:
        rows = [record for record in self.records() if record["measure"] == measure]
        if not rows:
            return None
        if year is None:
            return sorted(rows, key=lambda item: item["year"], reverse=True)[0]
        for record in rows:
            if record["year"] == year:
                return record
        return None

    def match_county_record(self, question: str) -> dict[str, Any] | None:
        normalized_question = normalize_area_name(question)
        candidates: list[tuple[int, dict[str, Any]]] = []
        for record in self.county_records():
            if record.get("area_type") != "county":
                continue
            area = str(record.get("area", ""))
            label = str(record.get("area_label", ""))
            names = {normalize_area_name(area), normalize_area_name(label)}
            if not area.endswith(("City", "County")):
                names.add(normalize_area_name(f"{area} county"))
            for name in names:
                if name and re.search(rf"\b{re.escape(name)}\b", normalized_question):
                    candidates.append((len(name), record))
                    break
        if not candidates:
            return None
        return sorted(candidates, key=lambda item: item[0], reverse=True)[0][1]

    def county_record_for(self, question: str) -> dict[str, Any] | None:
        record = self.match_county_record(question)
        if record is None:
            return None
        year = self.requested_year(question)
        if year is not None and year != record["year"]:
            return None
        return record

    def county_births_deaths_answer(self, question: str) -> dict[str, Any] | None:
        record = self.county_record_for(question)
        if record is None:
            return None
        return {
            "question": question,
            "answer": (
                f"For {record['year']}, the DHSS annual Missouri Vital Statistics report lists "
                f"{format_count(record['resident_live_births'])} resident live births and "
                f"{format_count(record['resident_deaths'])} resident deaths for {record['area_label']}. "
                f"Natural increase: {format_count(record['natural_increase'])}. "
                f"Resident rates per 1,000 population: birth {format_rate(record['resident_birth_rate'])}, "
                f"death {format_rate(record['resident_death_rate'])}, natural increase {format_rate(record['natural_increase_rate'])}. "
                "These are county aggregate vital-statistics values, not person-level vital records."
            ),
            "retrieved_context_id": f"dhss_vital_stats_index:county:{record['record_id']}",
            "retrieved_source": "dhss_vital_stats_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from Table 16A in the local DHSS annual Missouri Vital Statistics report index.",
            "citations": self.citation(matched_rows=1),
            "source_rows": [{"source_file": record["source_url"], "values": record}],
        }

    def county_measure_answer(self, question: str, measure: str) -> dict[str, Any] | None:
        record = self.county_record_for(question)
        if record is None:
            return None
        labels = {
            "resident_live_births": "resident live births",
            "resident_deaths": "resident deaths",
            "natural_increase": "natural increase",
            "resident_birth_rate": "resident birth rate",
            "resident_death_rate": "resident death rate",
        }
        value = record[measure]
        unit = " per 1,000 population" if measure.endswith("_rate") else ""
        value_text = format_rate(value) if measure.endswith("_rate") else format_count(value)
        return {
            "question": question,
            "answer": (
                f"For {record['year']}, the DHSS annual Missouri Vital Statistics report lists "
                f"{labels[measure]} for {record['area_label']} as {value_text}{unit}. "
                "This is a county aggregate Table 16A value, not a person-level vital record."
            ),
            "retrieved_context_id": f"dhss_vital_stats_index:county:{record['record_id']}:{measure}",
            "retrieved_source": "dhss_vital_stats_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from Table 16A in the local DHSS annual Missouri Vital Statistics report index.",
            "citations": self.citation(matched_rows=1),
            "source_rows": [{"source_file": record["source_url"], "values": record}],
        }

    def top_county_answer(self, question: str, measure: str) -> dict[str, Any] | None:
        rows = [record for record in self.county_records() if record.get("area_type") == "county"]
        if not rows:
            return None
        reverse = True
        if "lowest" in question.lower() or "smallest" in question.lower() or "least" in question.lower():
            reverse = False
        rows = sorted(rows, key=lambda item: item[measure], reverse=reverse)
        best = rows[0]
        labels = {
            "resident_live_births": "resident live births",
            "resident_deaths": "resident deaths",
            "natural_increase": "natural increase",
            "resident_birth_rate": "resident birth rate",
            "resident_death_rate": "resident death rate",
        }
        value = best[measure]
        unit = " per 1,000 population" if measure.endswith("_rate") else ""
        value_text = format_rate(value) if measure.endswith("_rate") else format_count(value)
        direction = "lowest" if not reverse else "highest"
        return {
            "question": question,
            "answer": (
                f"In the {best['year']} DHSS annual Missouri Vital Statistics Table 16A county rows, "
                f"{best['area_label']} has the {direction} indexed {labels[measure]} at {value_text}{unit}. "
                "This ranking uses county aggregate values only."
            ),
            "retrieved_context_id": f"dhss_vital_stats_index:county_rank:{measure}:{direction}:{best['record_id']}",
            "retrieved_source": "dhss_vital_stats_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from Table 16A in the local DHSS annual Missouri Vital Statistics report index.",
            "citations": self.citation(matched_rows=len(rows)),
            "source_rows": [{"source_file": best["source_url"], "values": best}],
        }

    def combined_births_deaths_answer(self, question: str) -> dict[str, Any]:
        year = self.requested_year(question)
        birth = self.record_for("births", year)
        death = self.record_for("deaths", year)
        if birth is None or death is None:
            return self.missing_answer(question)
        natural = self.record_for("natural increase", birth["year"])
        natural_text = f" Natural increase: {format_count(natural['count'])}." if natural else ""
        return {
            "question": question,
            "answer": (
                f"For {birth['year']}, the DHSS Vital Statistics FOCUS report lists {format_count(birth['count'])} Missouri resident live births "
                f"and {format_count(death['count'])} Missouri resident deaths.{natural_text} "
                "These are statewide aggregate counts from Table 1, not person-level vital records."
            ),
            "retrieved_context_id": f"dhss_vital_stats_index:births_deaths:{birth['year']}",
            "retrieved_source": "dhss_vital_stats_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local DHSS Vital Statistics FOCUS report index.",
            "citations": self.citation(matched_rows=2 + int(natural is not None)),
            "source_rows": [
                {"source_file": birth["source_url"], "values": birth},
                {"source_file": death["source_url"], "values": death},
            ]
            + ([{"source_file": natural["source_url"], "values": natural}] if natural else []),
        }

    def measure_answer(self, question: str, measure: str) -> dict[str, Any]:
        record = self.record_for(measure, self.requested_year(question))
        if record is None:
            return self.missing_answer(question)
        rate_sentence = ""
        if record.get("rate") is not None and record.get("rate_unit"):
            rate_sentence = f" Rate: {format_rate(record['rate'])} {record['rate_unit']}."
        return {
            "question": question,
            "answer": (
                f"The DHSS Vital Statistics FOCUS report lists {measure} for Missouri in {record['year']} as "
                f"{format_count(record['count'])}.{rate_sentence} "
                "This is a statewide aggregate Table 1 value, not a person-level vital record."
            ),
            "retrieved_context_id": f"dhss_vital_stats_index:{record['record_id']}",
            "retrieved_source": "dhss_vital_stats_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local DHSS Vital Statistics FOCUS report index.",
            "citations": self.citation(matched_rows=1),
            "source_rows": [{"source_file": record["source_url"], "values": record}],
        }

    def source_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        return {
            "question": question,
            "answer": (
                "The DHSS births/deaths aggregate index uses the official DHSS FOCUS page and the latest "
                f"Vital Statistics FOCUS PDF found there: {payload.get('report_url')}. It also uses the annual "
                f"Missouri Vital Statistics report for county Table 16A values: {payload.get('annual_report_url')}. "
                "It parses aggregate counts only."
            ),
            "retrieved_context_id": "dhss_vital_stats_index:source",
            "retrieved_source": "dhss_vital_stats_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local DHSS Vital Statistics FOCUS report index.",
            "citations": self.citation(matched_rows=0),
            "source_rows": [],
        }

    def missing_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        year_text = ", ".join(str(year) for year in payload.get("years", []))
        return {
            "question": question,
            "answer": (
                "I could not match that question to a supported DHSS vital-statistics aggregate row. "
                f"Indexed years: {year_text}. Try asking about statewide births, deaths, natural increase, infant deaths, marriages, divorces, population, or county births/deaths from the annual report."
            ),
            "retrieved_context_id": "dhss_vital_stats_index:no_match",
            "retrieved_source": "dhss_vital_stats_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "No row matched the local DHSS Vital Statistics FOCUS report index.",
            "citations": self.citation(matched_rows=0),
            "source_rows": [],
        }

    def answer(self, question: str) -> dict[str, Any] | None:
        if not self.available():
            return self.unavailable_answer(question)
        lowered = question.lower()
        if asks_for_source(question):
            return self.source_answer(question)
        county_measure = self.county_measure(question)
        county_record = self.county_record_for(question)
        if county_record is not None and ("birth" in lowered or "births" in lowered) and "death" in lowered:
            return self.county_births_deaths_answer(question)
        if county_measure is not None and any(term in lowered for term in ["which county", "what county", "top county", "highest", "lowest", "most", "least"]):
            ranked = self.top_county_answer(question, county_measure)
            if ranked is not None:
                return ranked
        if county_record is not None and county_measure is not None:
            return self.county_measure_answer(question, county_measure)
        if ("birth" in lowered or "births" in lowered) and "death" in lowered:
            return self.combined_births_deaths_answer(question)
        if asks_for_summary(question):
            return self.summary_answer(question)
        if asks_for_latest_year(question):
            return self.latest_year_answer(question)
        measure = self.match_measure(question)
        if measure is not None:
            return self.measure_answer(question, measure)
        return self.missing_answer(question)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    payload = build_dhss_vital_stats_index(force=args.force)
    print(
        json.dumps(
            {key: value for key, value in payload.items() if key not in {"records", "county_records"}},
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
