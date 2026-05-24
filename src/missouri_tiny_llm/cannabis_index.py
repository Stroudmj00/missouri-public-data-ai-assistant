"""Build and query selected Missouri cannabis regulation data."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from pypdf import PdfReader


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw_public" / "cannabis"
INDEX_PATH = RAW_DIR / "cannabis_index.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "cannabis_index_report.json"
LANDING_PAGE = "https://health.mo.gov/safety/cannabis/"
LICENSED_FACILITIES_PAGE = "https://health.mo.gov/safety/cannabis/licensed-facilities.php"
STATS_PAGE = "https://health.mo.gov/safety/cannabis/stats.php?lv=true"
ARCGIS_ITEM_DATA = "https://www.arcgis.com/sharing/rest/content/items/{item_id}/data"
SELECTED_FIELDS = ["Dispensary", "License", "City", "Zip_code", "County", "Last_updated", "ObjectId"]

REPORT_PATTERNS = {
    2024: {
        "medical_retail_sales_current": r"Recorded\s+\$([\d.]+)\s+million\s+in\s+medical\s+cannabis\s+retail\s+sales",
        "medical_retail_sales_cumulative": r"medical\s+cannabis\s+retail\s+sales,\s+for\s+a\s+total\s+of\s+\$([\d.]+)\s+billion",
        "medical_sales_tax_current": r"resulted\s+in\s+\$([\d.]+)\s+million\s+in\s+sales\s+tax\s+deposited\s+into\s+the\s+Veterans",
        "medical_sales_tax_cumulative": r"total\s+of\s+\$([\d.]+)\s+million\s+in\s+sales\s+tax\s+deposited\s+since\s+program\s+inception",
        "veterans_transfer_current": r"Transferred\s+\$([\d.]+)\s+million\s+from\s+the\s+Veterans",
        "veterans_transfer_cumulative": r"cumulative\s+amount\s+transferred\s+to\s+\$([\d.]+)\s+million",
        "adult_use_retail_sales_current": r"Recorded\s+\$([\d.]+)\s+billion\s+in\s+adult-use\s+cannabis\s+product\s+retail\s+sales",
        "adult_use_retail_sales_cumulative": r"adult-use\s+cannabis\s+product\s+retail\s+sales,\s+for\s+a\s+total\s+of\s+\$([\d.]+)\s+billion",
        "adult_use_sales_tax_current": r"resulted\s+in\s+\$([\d.]+)\s+million\s+in\s+sales\s+tax\s+deposited\s+into\s+the\s+Veterans,\s+Health\s+and\s+Community\s+Reinvestment\s+Fund",
        "adult_use_sales_tax_cumulative": r"total\s+of\s+\$([\d.]+)\s+million\s+in\s+sales\s+tax\s+deposited\s+since\s+program\s+inception\.\s+Transferred\s+\$31\.6",
        "reinvestment_transfer_current": r"Transferred\s+\$([\d.]+)\s+million\s+from\s+the\s+Reinvestment\s+Fund",
        "reinvestment_transfer_each": r"\$([\d.]+)\s+million\s+each\s+to\s+MVC",
        "new_microbusiness_licenses": r"Issued\s+(\d+)\s+new\s+microbusiness\s+licenses",
        "cumulative_microbusiness_licenses": r"total\s+of\s+(\d+)\s+licenses\s+since",
    },
    2023: {
        "medical_retail_sales_cumulative": r"\$([\d.]+)\s+million\s+in\s+cumulative\s+medical\s+retail\s+product\s+sales",
        "medical_sales_tax_cumulative": r"medical\s+retail\s+product\s+sales\s+with\s+\$([\d.]+)\s+million\s+in\s+cumulative\s+taxes",
        "veterans_transfer_current": r"\$([\d.]+)\s+million\s+transferred\s+from\s+the\s+Veterans",
        "veterans_transfer_cumulative": r"cumulative\s+amount\s+transferred\s+to\s+\$([\d.]+)\s+million",
        "adult_use_retail_sales_cumulative": r"\$([\d.]+)\s+million\s+in\s+cumulative\s+adult\s+use\s+retail\s+product\s+sales",
        "adult_use_sales_tax_cumulative": r"adult\s+use\s+retail\s+product\s+sales\s+with\s+\$([\d.]+)\s+million\s+in\s+cumulative\s+taxes",
        "reinvestment_transfer_current": r"\$([\d.]+)\s+million\s+transferred\s+from\s+the\s+Reinvestment\s+Fund",
        "reinvestment_transfer_each": r"\$([\d.]+)\s+million\s+each\s+to\s+Missouri\s+Veterans",
        "new_microbusiness_licenses": r"(\d+)\s+microbusiness\s+licenses\s+issued",
        "agent_id_cards_issued": r"(\d{1,3}(?:,\d{3})*)\s+agent\s+ID\s+cards\s+issued",
    },
    2022: {
        "medical_retail_sales_cumulative": r"\$([\d.]+)\s+million\s+in\s+cumulative\s+retail\s+product\s+sales",
        "medical_sales_tax_cumulative": r"\$([\d.]+)\s+million\s+in\s+taxes\s+deposited\s+into\s+the\s+Missouri\s+Veterans",
        "veterans_transfer_current": r"\$([\d.]+)\s+million\s+transferred\s+to\s+the\s+Missouri\s+Veterans\s+Commission",
        "veterans_transfer_cumulative": r"cumulative\s+amount\s+transferred\s+to\s+\$([\d.]+)\s+million",
        "new_approvals_to_operate": r"(\d+)\s+Approvals\s+to\s+Operate",
        "operating_facilities_total": r"total\s+of\s+(\d+)\s+operating\s+facilities",
        "agent_id_cards_issued": r"(\d{1,3}(?:,\d{3})*)\s+agent\s+identification\s+cards\s+issued",
    },
}

METRIC_LABELS = {
    "medical_retail_sales_current": "medical cannabis retail sales in the program year",
    "medical_retail_sales_cumulative": "cumulative medical cannabis retail sales",
    "medical_sales_tax_current": "medical cannabis sales tax deposited in the program year",
    "medical_sales_tax_cumulative": "cumulative medical cannabis sales tax deposited",
    "veterans_transfer_current": "transfer from the Veterans' Health and Care Fund in the program year",
    "veterans_transfer_cumulative": "cumulative transfer to the Missouri Veterans Commission",
    "adult_use_retail_sales_current": "adult-use cannabis product retail sales in the program year",
    "adult_use_retail_sales_cumulative": "cumulative adult-use cannabis product retail sales",
    "adult_use_sales_tax_current": "adult-use cannabis sales tax deposited in the program year",
    "adult_use_sales_tax_cumulative": "cumulative adult-use cannabis sales tax deposited",
    "reinvestment_transfer_current": "transfer from the Veterans, Health and Community Reinvestment Fund in the program year",
    "reinvestment_transfer_each": "amount transferred to each named Reinvestment Fund beneficiary",
    "new_microbusiness_licenses": "new microbusiness licenses issued",
    "cumulative_microbusiness_licenses": "cumulative microbusiness licenses issued",
    "agent_id_cards_issued": "agent ID cards issued",
    "new_approvals_to_operate": "new approvals to operate",
    "operating_facilities_total": "operating facilities total",
}

METRIC_UNITS = {
    "medical_retail_sales_current": "million dollars",
    "medical_retail_sales_cumulative": "billion dollars",
    "medical_sales_tax_current": "million dollars",
    "medical_sales_tax_cumulative": "million dollars",
    "veterans_transfer_current": "million dollars",
    "veterans_transfer_cumulative": "million dollars",
    "adult_use_retail_sales_current": "billion dollars",
    "adult_use_retail_sales_cumulative": "billion dollars",
    "adult_use_sales_tax_current": "million dollars",
    "adult_use_sales_tax_cumulative": "million dollars",
    "reinvestment_transfer_current": "million dollars",
    "reinvestment_transfer_each": "million dollars",
    "new_microbusiness_licenses": "licenses",
    "cumulative_microbusiness_licenses": "licenses",
    "agent_id_cards_issued": "cards",
    "new_approvals_to_operate": "approvals",
    "operating_facilities_total": "facilities",
}

COUNTY_ALIASES = {
    "SAINT LOUIS": "ST. LOUIS",
    "ST LOUIS": "ST. LOUIS",
    "ST. LOUIS": "ST. LOUIS",
    "SAINT CHARLES": "ST. CHARLES",
    "ST CHARLES": "ST. CHARLES",
    "ST. CHARLES": "ST. CHARLES",
    "SAINTE GENEVIEVE": "STE. GENEVIEVE",
    "STE GENEVIEVE": "STE. GENEVIEVE",
    "STE. GENEVIEVE": "STE. GENEVIEVE",
}


class LinkParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.links: list[dict[str, str]] = []
        self.viz_sources: list[str] = []
        self._current_href: str | None = None
        self._current_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        if tag == "a" and values.get("href"):
            self._current_href = urljoin(self.base_url, values["href"])
            self._current_text = []
        if tag == "tableau-viz" and values.get("src"):
            self.viz_sources.append(urljoin(self.base_url, values["src"]))

    def handle_data(self, data: str) -> None:
        if self._current_href:
            self._current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._current_href:
            self.links.append(
                {
                    "text": clean_text(" ".join(self._current_text)),
                    "href": self._current_href,
                }
            )
            self._current_href = None
            self._current_text = []


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_text(value: str) -> str:
    cleaned = re.sub(r"[^A-Z0-9&./-]+", " ", clean_text(value).upper())
    return re.sub(r"\s+", " ", cleaned).strip()


def canonical_county(value: str) -> str:
    cleaned = normalize_text(value.replace(" COUNTY", ""))
    return COUNTY_ALIASES.get(cleaned, cleaned)


def parse_program_year(text: str, href: str) -> int | None:
    match = re.search(r"\bPY\s?(\d{2})\b", text, re.IGNORECASE)
    if match:
        return 2000 + int(match.group(1))
    match = re.search(r"\b(20\d{2})\b", href)
    return int(match.group(1)) if match else None


def parse_report_date(text: str) -> str | None:
    match = re.search(r"\((\d{1,2}/\d{1,2}/20\d{2})\)", text)
    return match.group(1) if match else None


def discover_annual_reports(stats_html: str) -> list[dict[str, Any]]:
    parser = LinkParser(STATS_PAGE)
    parser.feed(stats_html)
    reports: list[dict[str, Any]] = []
    seen: set[str] = set()
    for link in parser.links:
        href = link["href"]
        text = clean_text(link["text"])
        if "annual" not in text.lower() or "report" not in text.lower() or not href.lower().endswith(".pdf"):
            continue
        if href in seen:
            continue
        seen.add(href)
        reports.append(
            {
                "program_year": parse_program_year(text, href),
                "title": text,
                "published_label": parse_report_date(text),
                "url": href,
            }
        )
    return sorted(reports, key=lambda item: item.get("program_year") or 0, reverse=True)


def discover_arcgis_layer(licensed_html: str, session: requests.Session) -> str:
    parser = LinkParser(LICENSED_FACILITIES_PAGE)
    parser.feed(licensed_html)
    experience_urls = [url for url in parser.viz_sources if "experience.arcgis.com/experience/" in url]
    if not experience_urls:
        raise RuntimeError("Could not find ArcGIS experience URL on licensed facilities page.")
    match = re.search(r"/experience/([a-f0-9]{32})", experience_urls[0], re.IGNORECASE)
    if not match:
        raise RuntimeError("Could not extract ArcGIS item id from experience URL.")
    item_id = match.group(1)
    response = session.get(ARCGIS_ITEM_DATA.format(item_id=item_id), params={"f": "json"}, timeout=60)
    response.raise_for_status()
    data = response.json()
    urls: list[str] = []

    def collect(obj: Any) -> None:
        if isinstance(obj, dict):
            url = obj.get("url")
            if isinstance(url, str) and "FeatureServer/0" in url and "DCR_Verified_Dispensary_Map_layer" in url:
                urls.append(url)
            for value in obj.values():
                collect(value)
        elif isinstance(obj, list):
            for value in obj:
                collect(value)

    collect(data)
    if not urls:
        raise RuntimeError("Could not find verified dispensary FeatureServer layer URL.")
    return urls[0]


def query_arcgis_records(layer_url: str, session: requests.Session) -> tuple[dict[str, Any], list[dict[str, Any]], bytes]:
    metadata_response = session.get(layer_url, params={"f": "json"}, timeout=60)
    metadata_response.raise_for_status()
    metadata_bytes = metadata_response.content
    metadata = metadata_response.json()
    count_response = session.get(
        f"{layer_url}/query",
        params={"f": "json", "where": "1=1", "returnCountOnly": "true"},
        timeout=60,
    )
    count_response.raise_for_status()
    expected_count = int(count_response.json().get("count", 0))
    page_size = int(metadata.get("maxRecordCount") or 1000)
    features: list[dict[str, Any]] = []
    offset = 0
    while offset < expected_count:
        response = session.get(
            f"{layer_url}/query",
            params={
                "f": "json",
                "where": "1=1",
                "outFields": ",".join(SELECTED_FIELDS),
                "returnGeometry": "false",
                "resultOffset": offset,
                "resultRecordCount": page_size,
                "orderByFields": "County ASC, City ASC, Dispensary ASC",
            },
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
        features.extend(payload.get("features", []))
        if len(payload.get("features", [])) < page_size:
            break
        offset += page_size
    return metadata, features, metadata_bytes


def normalize_feature(feature: dict[str, Any], layer_url: str) -> dict[str, Any]:
    attrs = feature.get("attributes", {})
    name = clean_text(attrs.get("Dispensary"))
    license_number = clean_text(attrs.get("License")).upper()
    city = clean_text(attrs.get("City"))
    county = clean_text(attrs.get("County"))
    return {
        "dispensary": name,
        "dispensary_norm": normalize_text(name),
        "license": license_number,
        "license_norm": normalize_text(license_number),
        "city": city,
        "city_norm": normalize_text(city),
        "county": county,
        "county_norm": canonical_county(county),
        "zip_code": clean_text(attrs.get("Zip_code")),
        "last_updated": clean_text(attrs.get("Last_updated")),
        "object_id": attrs.get("ObjectId"),
        "source_layer": layer_url,
        "source_page": LICENSED_FACILITIES_PAGE,
    }


def selected_report_metrics(report: dict[str, Any], text: str) -> dict[str, dict[str, Any]]:
    program_year = report.get("program_year")
    compact_text = clean_text(text)
    metrics: dict[str, dict[str, Any]] = {}
    for key, pattern in REPORT_PATTERNS.get(program_year, {}).items():
        match = re.search(pattern, compact_text, re.IGNORECASE)
        if not match:
            continue
        raw_value = match.group(1).replace(",", "")
        value: int | float
        value = int(raw_value) if raw_value.isdigit() else float(raw_value)
        metrics[key] = {
            "label": METRIC_LABELS.get(key, key.replace("_", " ")),
            "value": value,
            "unit": metric_unit(key, match.group(0)),
            "program_year": program_year,
            "source_url": report["url"],
        }
    return metrics


def metric_unit(key: str, matched_text: str) -> str:
    default = METRIC_UNITS.get(key, "")
    if default not in {"million dollars", "billion dollars"}:
        return default
    return "billion dollars" if "billion" in matched_text.lower() else "million dollars"


def extract_report_text(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def build_cannabis_index(force: bool = False) -> dict[str, Any]:
    if INDEX_PATH.exists() and not force:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (compatible; MissouriPublicDataChat/1.0; +https://github.com/Stroudmj00/missouri-tiny-llm-case-study)",
            "Accept": "application/json,text/html,application/pdf,*/*;q=0.8",
        }
    )
    start = time.perf_counter()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    licensed_response = session.get(LICENSED_FACILITIES_PAGE, timeout=60)
    licensed_response.raise_for_status()
    stats_response = session.get(STATS_PAGE, timeout=60)
    stats_response.raise_for_status()
    layer_url = discover_arcgis_layer(licensed_response.text, session)
    layer_metadata, features, layer_metadata_bytes = query_arcgis_records(layer_url, session)
    records = sorted(
        [normalize_feature(feature, layer_url) for feature in features],
        key=lambda item: (item["county_norm"], item["city_norm"], item["dispensary_norm"], item["license_norm"]),
    )
    annual_reports = discover_annual_reports(stats_response.text)
    selected_reports = [report for report in annual_reports if report.get("program_year") in {2024, 2023, 2022}]
    reports_with_metrics: list[dict[str, Any]] = []
    pdf_bytes_total = 0
    pdf_snapshots: list[bytes] = []
    for report in selected_reports:
        pdf_response = session.get(report["url"], timeout=90)
        pdf_response.raise_for_status()
        pdf_bytes = pdf_response.content
        pdf_bytes_total += len(pdf_bytes)
        pdf_snapshots.append(pdf_bytes)
        pdf_path = RAW_DIR / f"annual_report_py{str(report['program_year'])[-2:]}.pdf"
        pdf_path.write_bytes(pdf_bytes)
        text = extract_report_text(pdf_path)
        reports_with_metrics.append(
            {
                **report,
                "local_pdf": str(pdf_path.relative_to(PROJECT_ROOT)),
                "bytes": len(pdf_bytes),
                "sha256": sha256_bytes(pdf_bytes),
                "metrics": selected_report_metrics(report, text),
            }
        )
    write_json(RAW_DIR / "licensed_facilities_page.html.json", {"url": LICENSED_FACILITIES_PAGE, "html": licensed_response.text})
    write_json(RAW_DIR / "stats_page.html.json", {"url": STATS_PAGE, "html": stats_response.text})
    write_json(RAW_DIR / "dispensary_features_sanitized.json", records)
    county_counts = Counter(record["county"] for record in records if record.get("county"))
    city_counts = Counter(record["city"] for record in records if record.get("city"))
    update_counts = Counter(record["last_updated"] for record in records if record.get("last_updated"))
    payload = {
        "generated_at_utc": utc_now(),
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "source": "DHSS Division of Cannabis Regulation verified dispensary locator and annual reports",
        "landing_page": LANDING_PAGE,
        "licensed_facilities_page": LICENSED_FACILITIES_PAGE,
        "stats_page": STATS_PAGE,
        "arcgis_layer_url": layer_url,
        "index_path": str(INDEX_PATH.relative_to(PROJECT_ROOT)),
        "bytes": len(licensed_response.content)
        + len(stats_response.content)
        + len(layer_metadata_bytes)
        + pdf_bytes_total,
        "sha256": sha256_bytes(
            licensed_response.content
            + stats_response.content
            + layer_metadata_bytes
            + json.dumps(records, sort_keys=True).encode("utf-8")
            + b"".join(pdf_snapshots)
        ),
        "record_count": len(records),
        "county_count": len(county_counts),
        "city_count": len(city_counts),
        "latest_facility_update": sorted(update_counts)[-1] if update_counts else None,
        "top_counties": top_counts(county_counts),
        "top_cities": top_counts(city_counts),
        "annual_report_count": len(annual_reports),
        "selected_annual_report_count": len(reports_with_metrics),
        "selected_report_years": [report.get("program_year") for report in reports_with_metrics],
        "layer_fields": [field.get("name") for field in layer_metadata.get("fields", []) if field.get("name")],
        "records": records,
        "annual_reports": annual_reports,
        "selected_annual_reports": reports_with_metrics,
    }
    write_json(INDEX_PATH, payload)
    write_json(
        REPORT_PATH,
        {
            "generated_at_utc": payload["generated_at_utc"],
            "elapsed_seconds": payload["elapsed_seconds"],
            "source": payload["source"],
            "landing_page": payload["landing_page"],
            "licensed_facilities_page": payload["licensed_facilities_page"],
            "stats_page": payload["stats_page"],
            "arcgis_layer_url": payload["arcgis_layer_url"],
            "index_path": payload["index_path"],
            "bytes": payload["bytes"],
            "sha256": payload["sha256"],
            "record_count": payload["record_count"],
            "county_count": payload["county_count"],
            "city_count": payload["city_count"],
            "latest_facility_update": payload["latest_facility_update"],
            "top_counties": payload["top_counties"],
            "top_cities": payload["top_cities"],
            "annual_report_count": payload["annual_report_count"],
            "selected_annual_report_count": payload["selected_annual_report_count"],
            "selected_report_years": payload["selected_report_years"],
            "selected_report_metrics": {
                str(report["program_year"]): report["metrics"] for report in payload["selected_annual_reports"]
            },
        },
    )
    return payload


def top_counts(counter: Counter[str], limit: int = 12) -> list[dict[str, Any]]:
    return [
        {"label": label, "count": count}
        for label, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:limit]
        if label
    ]


def asks_for_count(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["how many", "count", "number of", "total"])


def asks_for_top(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["top", "highest", "largest", "most"])


def asks_for_list(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["list", "which", "show", "what dispensaries", "what are"])


def license_in_question(question: str) -> str | None:
    match = re.search(r"\bDIS\d{6}\b", question.upper())
    return match.group(0) if match else None


def program_year_in_question(question: str) -> int | None:
    lowered = question.lower()
    match = re.search(r"\bpy\s?(\d{2})\b", lowered)
    if match:
        return 2000 + int(match.group(1))
    match = re.search(r"\b(202[234])\b", lowered)
    return int(match.group(1)) if match else None


def format_metric(metric: dict[str, Any]) -> str:
    value = metric.get("value")
    unit = metric.get("unit", "")
    if unit == "million dollars":
        return f"${value:g} million"
    if unit == "billion dollars":
        return f"${value:g} billion"
    if unit:
        return f"{value:,} {unit}" if isinstance(value, int) else f"{value:g} {unit}"
    return str(value)


class CannabisIndex:
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

    def citation(self, matched_rows: int = 0, include_report: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        payload = self.payload()
        files = [
            {
                "category": "verified_dispensary_locator",
                "category_label": "DHSS Cannabis verified dispensary locator",
                "file_name": payload.get("licensed_facilities_page", LICENSED_FACILITIES_PAGE),
                "row_count": payload.get("record_count"),
                "bytes": None,
                "sha256": None,
            },
            {
                "category": "verified_dispensary_locator_layer",
                "category_label": "DCR verified dispensary ArcGIS feature layer",
                "file_name": payload.get("arcgis_layer_url"),
                "row_count": payload.get("record_count"),
                "bytes": None,
                "sha256": payload.get("sha256"),
            },
        ]
        if include_report:
            files.append(
                {
                    "category": "cannabis_annual_report",
                    "category_label": include_report.get("title", "DHSS cannabis annual report"),
                    "file_name": include_report.get("url"),
                    "row_count": None,
                    "bytes": include_report.get("bytes"),
                    "sha256": include_report.get("sha256"),
                }
            )
        return [
            {
                "dataset": payload.get("source", "DHSS Division of Cannabis Regulation selected cannabis index"),
                "category": "Cannabis Regulation",
                "kind": "verified dispensary and annual report lookup",
                "lookup_table": "cannabis_index",
                "year": include_report.get("program_year") if include_report else None,
                "year_range": payload.get("selected_report_years"),
                "source_files": files,
                "source_file_count": len(files),
                "source_rows": payload.get("record_count"),
                "matched_rows": matched_rows,
            }
        ]

    def unavailable_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "The selected cannabis index has not been built yet. Run "
                "`python scripts/build_cannabis_index.py --force` to download the public DHSS facility layer and selected annual reports."
            ),
            "retrieved_context_id": "cannabis_index:missing",
            "retrieved_source": "cannabis_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "The cannabis route exists, but the local ignored index is missing.",
            "citations": [],
            "source_rows": [],
        }

    def summary_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        top_counties = "; ".join(f"{item['label']}: {item['count']}" for item in payload.get("top_counties", [])[:5])
        report_years = ", ".join(str(year) for year in payload.get("selected_report_years", []))
        return {
            "question": question,
            "answer": (
                "The selected cannabis exact lookup layer indexes the official DHSS verified dispensary locator "
                f"and selected annual reports. It contains {payload.get('record_count', 0):,} verified dispensary "
                f"records across {payload.get('county_count', 0):,} counties and {payload.get('city_count', 0):,} cities. "
                f"Latest facility update label: {payload.get('latest_facility_update')}. "
                f"Selected annual report metric years: {report_years}. "
                "It can answer verified dispensary counts, county/city rankings, license/name lookups, and selected annual-report metrics. "
                f"Top counties by listed dispensaries: {top_counties}."
            ),
            "retrieved_context_id": "cannabis_index:summary",
            "retrieved_source": "cannabis_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local DHSS cannabis index built from official public sources.",
            "citations": self.citation(matched_rows=payload.get("record_count", 0)),
            "source_rows": [],
        }

    def reports_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        reports = payload.get("annual_reports", [])
        rendered = "; ".join(f"PY{str(report.get('program_year'))[-2:]}: {report.get('url')}" for report in reports[:6])
        return {
            "question": question,
            "answer": (
                f"The DHSS cannabis source page links {len(reports):,} annual report PDF(s). "
                f"Selected parsed metric years in this local index: {', '.join(str(y) for y in payload.get('selected_report_years', []))}. "
                f"Report links: {rendered}."
            ),
            "retrieved_context_id": "cannabis_index:annual_reports",
            "retrieved_source": "cannabis_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Annual report links are parsed from the official DHSS cannabis data and reports page.",
            "citations": self.citation(matched_rows=len(reports)),
            "source_rows": [{"source_file": STATS_PAGE, "values": report} for report in reports[:5]],
        }

    def county_from_question(self, question: str) -> str | None:
        question_norm = canonical_county(question)
        counties = sorted({record["county_norm"] for record in self.records() if record.get("county_norm")}, key=len, reverse=True)
        for county in counties:
            if re.search(rf"\b{re.escape(county)}\b", question_norm):
                return county
        return None

    def city_from_question(self, question: str) -> str | None:
        question_norm = normalize_text(question)
        cities = sorted({record["city_norm"] for record in self.records() if record.get("city_norm")}, key=len, reverse=True)
        for city in cities:
            if re.search(rf"\b{re.escape(city)}\b", question_norm):
                return city
        return None

    def records_for_county(self, county_norm: str) -> list[dict[str, Any]]:
        return [record for record in self.records() if record.get("county_norm") == county_norm]

    def records_for_city(self, city_norm: str) -> list[dict[str, Any]]:
        return [record for record in self.records() if record.get("city_norm") == city_norm]

    def find_by_license(self, license_number: str) -> dict[str, Any] | None:
        for record in self.records():
            if record.get("license_norm") == normalize_text(license_number):
                return record
        return None

    def find_by_name(self, question: str) -> dict[str, Any] | None:
        question_norm = normalize_text(question)
        candidates: list[tuple[int, dict[str, Any]]] = []
        generic = {
            "CANNABIS",
            "DISPENSARY",
            "DISPENSARIES",
            "MISSOURI",
            "WHERE",
            "WHAT",
            "WHICH",
            "CITY",
            "COUNTY",
            "LICENSE",
            "LISTED",
            "VERIFIED",
        }
        question_tokens = {token for token in question_norm.split() if token not in generic}
        for record in self.records():
            name_norm = record.get("dispensary_norm", "")
            name_tokens = {token for token in name_norm.split() if token not in generic}
            score = 0
            if name_norm and name_norm in question_norm:
                score += 100 + len(name_norm)
            overlap = name_tokens & question_tokens
            if len(overlap) >= 2:
                score += 10 * len(overlap)
            if score:
                candidates.append((score, record))
        return sorted(candidates, key=lambda item: item[0], reverse=True)[0][1] if candidates else None

    def count_answer(self, question: str, label: str, records: list[dict[str, Any]]) -> dict[str, Any]:
        examples = "; ".join(f"{record['dispensary']} ({record['city']})" for record in records[:6])
        suffix = f" Example listed dispensaries: {examples}." if examples else ""
        return {
            "question": question,
            "answer": f"The DHSS verified dispensary locator lists {len(records):,} verified dispensary record(s) for {label}.{suffix}",
            "retrieved_context_id": f"cannabis_index:count:{normalize_text(label)}",
            "retrieved_source": "cannabis_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from sanitized non-contact fields in the official DHSS verified dispensary locator.",
            "citations": self.citation(matched_rows=len(records)),
            "source_rows": [{"source_file": self.payload().get("arcgis_layer_url"), "values": record} for record in records[:5]],
        }

    def rank_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        use_city = "city" in question.lower() and "county" not in question.lower()
        key = "top_cities" if use_city else "top_counties"
        label = "city" if use_city else "county"
        top = payload.get(key, [])
        rendered = "; ".join(f"{item['label']}: {item['count']}" for item in top[:6])
        winner = top[0] if top else {"label": "unknown", "count": 0}
        return {
            "question": question,
            "answer": (
                f"In the DHSS verified dispensary locator, the {label} with the most listed dispensaries is "
                f"{winner['label']} with {winner['count']} record(s). Top {label} counts: {rendered}."
            ),
            "retrieved_context_id": f"cannabis_index:rank:{label}",
            "retrieved_source": "cannabis_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed by ranking sanitized facility rows in the local DHSS cannabis index.",
            "citations": self.citation(matched_rows=payload.get("record_count", 0)),
            "source_rows": [{"source_file": self.payload().get("arcgis_layer_url"), "values": item} for item in top[:5]],
        }

    def facility_answer(self, question: str, record: dict[str, Any]) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                f"{record['dispensary']} is listed in the DHSS verified dispensary locator with license "
                f"{record['license']}, city {record['city']}, county {record['county']}, ZIP {record['zip_code']}. "
                f"The row's last-updated label is {record['last_updated']}."
            ),
            "retrieved_context_id": f"cannabis_index:facility:{record['license']}",
            "retrieved_source": "cannabis_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from sanitized non-contact fields in the official DHSS verified dispensary locator.",
            "citations": self.citation(matched_rows=1),
            "source_rows": [{"source_file": self.payload().get("arcgis_layer_url"), "values": record}],
        }

    def metric_for_question(self, question: str, year: int) -> tuple[dict[str, Any], dict[str, Any]] | None:
        lowered = question.lower()
        reports = {report.get("program_year"): report for report in self.payload().get("selected_annual_reports", [])}
        report = reports.get(year)
        if not report:
            return None
        metric_keys: list[str] = []
        if "microbusiness" in lowered:
            metric_keys = ["new_microbusiness_licenses", "cumulative_microbusiness_licenses"]
        elif "agent" in lowered and ("id" in lowered or "card" in lowered):
            metric_keys = ["agent_id_cards_issued"]
        elif "approval" in lowered or "operate" in lowered or "operating facilities" in lowered:
            metric_keys = ["new_approvals_to_operate", "operating_facilities_total"]
        elif "adult" in lowered and "tax" in lowered:
            metric_keys = ["adult_use_sales_tax_current", "adult_use_sales_tax_cumulative"]
        elif "adult" in lowered and ("sale" in lowered or "retail" in lowered):
            metric_keys = ["adult_use_retail_sales_current", "adult_use_retail_sales_cumulative"]
        elif ("medical" in lowered or "veterans" in lowered) and "tax" in lowered:
            metric_keys = ["medical_sales_tax_current", "medical_sales_tax_cumulative"]
        elif "medical" in lowered and ("sale" in lowered or "retail" in lowered):
            metric_keys = ["medical_retail_sales_current", "medical_retail_sales_cumulative"]
        elif "reinvestment" in lowered or "public defender" in lowered or "substance use" in lowered:
            metric_keys = ["reinvestment_transfer_current", "reinvestment_transfer_each"]
        elif "veterans" in lowered or "veterans commission" in lowered:
            metric_keys = ["veterans_transfer_current", "veterans_transfer_cumulative"]
        for key in metric_keys:
            metric = report.get("metrics", {}).get(key)
            if metric:
                return report, metric
        return None

    def metric_answer(self, question: str, report: dict[str, Any], metric: dict[str, Any]) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                f"For PY{str(metric['program_year'])[-2:]}, the DHSS annual report lists "
                f"{metric['label']} as {format_metric(metric)}."
            ),
            "retrieved_context_id": f"cannabis_index:annual_metric:{metric['program_year']}:{normalize_text(metric['label'])}",
            "retrieved_source": "cannabis_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from selected extracted metrics in official DHSS cannabis annual report PDFs.",
            "citations": self.citation(matched_rows=1, include_report=report),
            "source_rows": [{"source_file": report.get("url"), "values": metric}],
        }

    def missing_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "The selected cannabis index covers verified dispensary counts/lookups and selected annual-report metrics, "
                "but this question did not match a supported facility, place, report year, or metric. Try `What cannabis data is indexed?`, "
                "`How many verified cannabis dispensaries are in Boone County?`, `Which county has the most verified dispensaries?`, "
                "or `How much adult-use cannabis retail sales were recorded in PY24?`."
            ),
            "retrieved_context_id": "cannabis_index:no_match",
            "retrieved_source": "cannabis_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Answered from cannabis coverage metadata because no exact supported lookup matched.",
            "citations": self.citation(),
            "source_rows": [],
        }

    def answer(self, question: str) -> dict[str, Any] | None:
        if not self.available():
            return self.unavailable_answer(question)
        lowered = question.lower()
        if "annual" in lowered and "report" in lowered and any(term in lowered for term in ["indexed", "linked", "available", "which"]):
            return self.reports_answer(question)
        year = program_year_in_question(question)
        if year:
            metric_result = self.metric_for_question(question, year)
            if metric_result:
                report, metric = metric_result
                return self.metric_answer(question, report, metric)
        if (
            re.search(r"\b(cannabis|marijuana)\b.*\b(indexed|lookup|data|dispensar(?:y|ies)|facility|facilities)\b", lowered)
            and not asks_for_count(question)
            and not asks_for_top(question)
        ):
            if not self.county_from_question(question) and not self.city_from_question(question) and not license_in_question(question):
                return self.summary_answer(question)
        license_number = license_in_question(question)
        if license_number:
            record = self.find_by_license(license_number)
            return self.facility_answer(question, record) if record else self.missing_answer(question)
        name_record = self.find_by_name(question)
        if name_record and any(term in lowered for term in ["license", "city", "county", "where", "listed"]):
            return self.facility_answer(question, name_record)
        if asks_for_top(question):
            return self.rank_answer(question)
        county = self.county_from_question(question)
        if county:
            records = self.records_for_county(county)
            label = f"{records[0]['county']} County" if records else f"{county} County"
            return self.count_answer(question, label, records)
        city = self.city_from_question(question)
        if city:
            records = self.records_for_city(city)
            label = records[0]["city"] if records else city
            return self.count_answer(question, label, records)
        if asks_for_count(question) and re.search(r"\b(dispensar(?:y|ies)|facilit(?:y|ies))\b", lowered):
            return self.count_answer(question, "Missouri", self.records())
        return self.missing_answer(question)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    payload = build_cannabis_index(force=args.force)
    print(json.dumps({key: value for key, value in payload.items() if key not in {"records", "annual_reports", "selected_annual_reports"}}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
