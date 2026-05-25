"""Preflight source registry for planned Missouri public-data expansion."""

from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPORTS_DIR = PROJECT_ROOT / "reports"


@dataclass(frozen=True)
class ExpansionSource:
    key: str
    label: str
    domain: str
    url: str
    phase_one_scope: str
    ingestion_mode: str
    risk: str


SOURCES = [
    ExpansionSource(
        key="missouri_contracts",
        label="MissouriBUYS / Office of Administration contract metadata",
        domain="contracts",
        url="https://missouribuys.mo.gov/contractboard",
        phase_one_scope="Index contract number, contractor, description, category, contract period, detail URL, and document URLs.",
        ingestion_mode="HTML form/list/detail pages; metadata only; no contract-document downloads by default.",
        risk="moderate: HTML parsing and legacy CGI pages can change.",
    ),
    ExpansionSource(
        key="dese_school_data",
        label="DESE School Data",
        domain="education",
        url="https://dese.mo.gov/school-data",
        phase_one_scope="Index official DESE resource metadata for accountability/APR/MSIP, Core Data/MOSIS file layouts and code sets, school finance, assessment, special education, and dashboard source links.",
        ingestion_mode="Public source-page metadata and resource links; exact numeric school values require separate parsers for selected exports or dashboards.",
        risk="moderate: several DESE datasets are behind apps or report portals rather than simple static files.",
    ),
    ExpansionSource(
        key="data_mo_catalog",
        label="State of Missouri data.mo.gov catalog",
        domain="open_data_catalog",
        url="https://data.mo.gov/data.json",
        phase_one_scope="Inventory statewide Socrata/data.json metadata and identify stable CSV/JSON exports.",
        ingestion_mode="Metadata first; download specific datasets only after row counts and schemas are known.",
        risk="moderate: mixed Socrata views, maps, files, filters, and stale records.",
    ),
    ExpansionSource(
        key="dhss_public_health",
        label="DHSS Data, Surveillance Systems & Statistical Reports",
        domain="public_health",
        url="https://health.mo.gov/data/",
        phase_one_scope="Index public-health resource metadata for county profiles, MOPHIMS/MICA, BRFSS, births/deaths, hospitalizations/PAS, county-level study, FOCUS reports, and surveillance dashboard links; parse selected statewide BRFSS and vital-statistics aggregates.",
        ingestion_mode="Public source-page metadata and resource links first; exact numeric values require source-specific aggregate parsers with suppression handling.",
        risk="high: health datasets require careful privacy, suppression handling, and no person-level records.",
    ),
    ExpansionSource(
        key="mshp_crash_data",
        label="MSHP crash and traffic safety data files",
        domain="traffic_safety",
        url="https://www.mshp.dps.mo.gov/MSHPWeb/SAC/data_960grid.html",
        phase_one_scope="Inventory small official Excel crash-statistics files for severity, rates, circumstances, and factor involvement; parse selected 2023 Traffic Safety Compendium statewide/factor HTML tables.",
        ingestion_mode="Static Excel files plus selected WebFOCUS HTML table snapshots; aggregate tables only.",
        risk="low: small aggregate files, but .xls parsing requires xlrd and Compendium coverage is selected rather than complete.",
    ),
    ExpansionSource(
        key="meric_labor",
        label="MERIC labor and unemployment data",
        domain="labor_market",
        url="https://meric.mo.gov/data/economic/local-area-unemployment-statistics/laus",
        phase_one_scope="Parse the public LAUS CSV route for current Missouri and county unemployment rate, labor force, employment, and unemployed counts; catalog wage, industry, projection, and regional profile releases for later.",
        ingestion_mode="Structured CSV form download with timestamped local index; broader reports still need source-specific parsers.",
        risk="moderate: county/current-month coverage and release timestamps must be labeled.",
    ),
    ExpansionSource(
        key="dnr_environment",
        label="Missouri DNR data and e-services",
        domain="environment",
        url="https://dnr.mo.gov/data-e-services",
        phase_one_scope="Index official public resource metadata for environmental data/e-services, including water permits, public water tools, impaired waters, air emissions, waste/recycling, land/geology GIS, energy data, forms, and public notices; parse the selected proposed 2024-2026 Section 303(d) listed-waters PDF.",
        ingestion_mode="Small HTML resource-link index first; selected 303(d) PDF parser is capped around 35 MB; start other numeric parsers with small tabular exports before GIS-heavy layers.",
        risk="moderate: many sources are search tools or map services rather than simple static files; the impaired-waters parser is a proposed-list snapshot, not live water safety, health, permit, or legal advice.",
    ),
    ExpansionSource(
        key="msdis_geospatial",
        label="MSDIS geospatial open data",
        domain="geospatial",
        url="https://www.msdis.missouri.edu/",
        phase_one_scope="Index official MSDIS metadata for Open Data datasets, ArcGIS REST feature/map/image services, county boundaries, imagery, LiDAR/elevation, archive directories, and vector GIS links.",
        ingestion_mode="Metadata-only lookup; avoid imagery, LiDAR, shapefile, geodatabase, and feature-attribute downloads by default.",
        risk="high: imagery, LiDAR, and GIS feature exports can be very large; this parser stores source metadata and links only.",
    ),
    ExpansionSource(
        key="modot_transportation",
        label="MoDOT traffic and transportation data",
        domain="transportation",
        url="https://www.modot.org/modatazone/traffic",
        phase_one_scope="Parse latest-year directional AADT route-segment records from the official TrafficInfoSegAADT ArcGIS service; keep broader safety/road tools cataloged.",
        ingestion_mode="ArcGIS REST attribute query with geometry omitted; selected non-person traffic-volume attributes only.",
        risk="moderate: route/segment text matching is not address geocoding, and broader map/app-only values still need source-specific parsing.",
    ),
    ExpansionSource(
        key="state_auditor_reports",
        label="Missouri State Auditor reports",
        domain="audits",
        url="https://auditor.mo.gov/AuditReport/Reports",
        phase_one_scope="Catalog audit reports, local government financial reports, tax increment financing reports, forfeiture reports, and data breach notices.",
        ingestion_mode="Source registry first; add PDF/report extraction only after selecting report families and limits.",
        risk="moderate: report search is partially dynamic and report PDFs need careful extraction.",
    ),
    ExpansionSource(
        key="dor_public_reports",
        label="Missouri Department of Revenue public reports",
        domain="tax_revenue",
        url="https://dor.mo.gov/public-reports/",
        phase_one_scope="Catalog public taxable sales, food tax, tax-credit, dealer, motor vehicle, and Working Family Tax Credit reports.",
        ingestion_mode="Source registry first; prefer downloadable text/zip files with clear fiscal or calendar year labels.",
        risk="moderate: suppressed cells and text-file layouts must be preserved.",
    ),
    ExpansionSource(
        key="mec_public_records",
        label="Missouri Ethics Commission public records",
        domain="ethics_campaign_finance",
        url="https://mec.mo.gov/",
        phase_one_scope="Index public-resource metadata for campaign finance, lobbying, committee contribution/expenditure, commission-action, advisory-opinion, PFD, form, and annual-report surfaces.",
        ingestion_mode="Metadata lookup first; add entity-specific search adapters after data shape is confirmed.",
        risk="moderate: entity matching and political-finance interpretation require careful citations.",
    ),
    ExpansionSource(
        key="sos_elections",
        label="Missouri Secretary of State election results",
        domain="elections",
        url="https://www.sos.mo.gov/elections/s_default",
        phase_one_scope="Parse selected statewide official returns, selected 2024 county President/Governor result rows, and 2024 county/jurisdiction turnout aggregates.",
        ingestion_mode="Official PDF parsers plus source registry; avoid voter-level data and non-bulk pages.",
        risk="moderate: precinct data may require contact or purchase, and county PDF formats vary by election.",
    ),
    ExpansionSource(
        key="oa_budget_planning",
        label="Office of Administration Budget and Planning",
        domain="budget",
        url="https://budplan.oa.mo.gov/budget-information",
        phase_one_scope="Parse metadata for executive budget links, budget summaries, revenue release/detail file links, performance-measure resources, demographic resources, and redistricting resources; parse selected General Revenue Detail Excel workbooks for aggregate line-item lookup.",
        ingestion_mode="Metadata/link index plus selected FY 2026 monthly revenue-detail Excel parser; broader fiscal-year PDFs still need stable source-specific parsers.",
        risk="moderate: budget proposal/enacted stages must not be mixed, and only selected revenue-detail Excel contents are parsed.",
    ),
    ExpansionSource(
        key="dese_child_care",
        label="DESE child care compliance dashboards",
        domain="child_care",
        url="https://dese.mo.gov/childhood/child-care/child-care-data-dashboards",
        phase_one_scope="Catalog regulated child care facilities, slots, pending facilities, inspections, complaints, and licensing-time dashboards.",
        ingestion_mode="Source registry first; extract dashboard PDFs/tables with quarter labels.",
        risk="moderate: facility-level compliance context needs source-cited wording.",
    ),
    ExpansionSource(
        key="dhss_long_term_care",
        label="DHSS long-term care inspection data",
        domain="long_term_care",
        url="https://health.mo.gov/safety/nursinghomesinspected/index.php",
        phase_one_scope="Catalog long-term-care inspections, facility types, beds, complaints, and Show Me Long-Term Care search surfaces.",
        ingestion_mode="Source registry first; prefer aggregate and source-navigation answers before facility-level summaries.",
        risk="high: health facility quality data needs careful context and no medical advice.",
    ),
    ExpansionSource(
        key="psc_reports",
        label="Missouri Public Service Commission reports",
        domain="utilities",
        url="https://psc.mo.gov/General/PSC_Reports",
        phase_one_scope="Parse PSC report-volume metadata for covered periods, year-to-volume matching, and PDF links; add capped selected report-PDF text extraction for simple orientation and snippet search.",
        ingestion_mode="Source registry first; parse selected report PDFs with strict MB/page/character caps before expanding to other report families.",
        risk="moderate: report metadata is small, but PSC report PDFs are large and utility cases contain legal/regulatory decisions that must be distinguished from source-text orientation.",
    ),
    ExpansionSource(
        key="dhss_cannabis_reports",
        label="DHSS Division of Cannabis Regulation reports",
        domain="cannabis",
        url="https://health.mo.gov/safety/cannabis/",
        phase_one_scope="Catalog cannabis annual reports, sales dashboards, transfer history, licensed facilities, inspections, and regulatory updates.",
        ingestion_mode="Source registry first; avoid legal advice and cite snapshot periods.",
        risk="moderate: dashboard values are time-sensitive and may shift after corrections.",
    ),
    ExpansionSource(
        key="agriculture_market_news",
        label="Missouri Agricultural Market News reports",
        domain="agriculture",
        url="https://agmarketnews.mo.gov/reports/",
        phase_one_scope="Parse report-link metadata for livestock, cattle, swine, sheep/goat, hay/forage, feedstuff, grain, regional market, and USDA AMS report links.",
        ingestion_mode="Metadata/link index first; parse PDF prices, receipts, weights, and market commentary later only for selected reports.",
        risk="low: metadata is small and public, but many links are external USDA AMS pages with report-specific PDF formats.",
    ),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value)).strip()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def fetch(session: requests.Session, url: str) -> requests.Response:
    response = session.get(url, timeout=60)
    response.raise_for_status()
    return response


def extract_links(page_text: str, base_url: str, limit: int = 20) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    for href, label in re.findall(r"<a\s+[^>]*href=['\"]([^'\"]+)['\"][^>]*>(.*?)</a>", page_text, flags=re.I | re.S):
        text = clean_text(label)
        if not text:
            continue
        links.append({"label": text, "url": urljoin(base_url, href)})
        if len(links) >= limit:
            break
    return links


def contract_probe(session: requests.Session) -> dict[str, Any]:
    response = session.post(
        "https://archive.oa.mo.gov/purch/cgi/list.cgi",
        data={"sort": "contract", "submit3": "Submit"},
        timeout=60,
    )
    response.raise_for_status()
    contract_count = len(re.findall(r"display\.cgi\?contnum=", response.text, flags=re.I))
    return {
        "legacy_contract_list_url": "https://archive.oa.mo.gov/purch/cgi/list.cgi",
        "estimated_contract_rows": contract_count,
        "list_page_bytes": len(response.content),
        "download_default": "metadata only; document links only",
    }


def mshp_probe(page_text: str, base_url: str) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    for match in re.finditer(r"<a\s+[^>]*href=['\"]([^'\"]+\.xls)['\"][^>]*>(.*?)</a>", page_text, flags=re.I | re.S):
        href, label = match.groups()
        after = page_text[match.end() : match.end() + 160]
        size_match = re.search(r"Size:\s*([\d.]+)\s*(KB|MB)", after, flags=re.I)
        size_kb = None
        if size_match:
            amount = float(size_match.group(1))
            size_kb = amount * 1024 if size_match.group(2).upper() == "MB" else amount
        files.append(
            {
                "label": clean_text(label),
                "url": urljoin(base_url, href),
                "estimated_kb": round(size_kb, 2) if size_kb is not None else None,
            }
        )
    crash_files = [file for file in files if "Crash" in file["label"] or "Crashes" in file["label"]]
    known_size_kb = sum(file["estimated_kb"] or 0 for file in crash_files)
    return {
        "excel_file_count": len(files),
        "crash_excel_file_count": len(crash_files),
        "estimated_crash_excel_mb": round(known_size_kb / 1024, 4),
        "crash_files": crash_files,
    }


def mshp_static_fallback() -> dict[str, Any]:
    crash_files = [
        ("Number of Persons Killed/Injured, Fatal/Personal Injury and Property Damage Crashes by Year", "CrashesSeverity.xls", 41),
        ("Death and Injury Rate by Year", "CrashesRates.xls", 32),
        ("Circumstances Involved in Crash by Year", "CrashesCircumstances.xls", 78),
        ("Crashes by Speed Involvement", "CrashesSpeed.xls", 34),
        ("Crash by Alcohol Involvement", "CrashesAlcohol.xls", 31),
        ("Crash by Young Driver Involvement (Under 21 Years Old)", "CrashesYoung.xls", 34),
        ("Crash by Older Driver Involvement (55 Years Old and Up)", "CrashesOlder.xls", 38),
        ("Motorcycle Crashes", "CrashesMotorcycle.xls", 38),
        ("Crashes by Commercial Motor Vehicle Involvement", "CrashesCMV.xls", 34),
    ]
    return {
        "excel_file_count": len(crash_files),
        "crash_excel_file_count": len(crash_files),
        "estimated_crash_excel_mb": round(sum(file[2] for file in crash_files) / 1024, 4),
        "source": "static fallback from previously observed official MSHP SAC data page labels",
        "crash_files": [
            {
                "label": label,
                "url": f"https://www.mshp.dps.mo.gov/MSHPWeb/SAC/{filename}",
                "estimated_kb": estimated_kb,
            }
            for label, filename, estimated_kb in crash_files
        ],
    }


def sos_static_links() -> list[dict[str, str]]:
    return [
        {"label": "Election Results", "url": "https://www.sos.mo.gov/elections/s_default"},
        {"label": "2024 General Election official returns", "url": "https://www.sos.mo.gov/CMSImages/ElectionResultsStatistics/2024GeneralElection.pdf"},
        {"label": "2024 Primary Election official returns", "url": "https://www.sos.mo.gov/CMSImages/ElectionResultsStatistics/2024PrimaryElection.pdf"},
    ]


def data_mo_catalog_probe(page_text: str) -> dict[str, Any]:
    catalog = json.loads(page_text)
    datasets = catalog.get("dataset", [])
    theme_counts: dict[str, int] = {}
    distribution_count = 0
    for dataset in datasets:
        if dataset.get("distribution"):
            distribution_count += 1
        theme = dataset.get("theme") or "uncategorized"
        if isinstance(theme, list):
            for item in theme:
                theme_counts[str(item)] = theme_counts.get(str(item), 0) + 1
        else:
            theme_counts[str(theme)] = theme_counts.get(str(theme), 0) + 1
    top_themes = [
        {"theme": theme, "count": count}
        for theme, count in sorted(theme_counts.items(), key=lambda item: item[1], reverse=True)[:12]
    ]
    return {
        "dataset_count": len(datasets),
        "datasets_with_distribution": distribution_count,
        "top_themes": top_themes,
        "api_views_url": "https://data.mo.gov/api/views.json",
        "socrata_catalog_api": "https://api.us.socrata.com/api/catalog/v1?domains=data.mo.gov",
    }


def preflight() -> dict[str, Any]:
    start = time.perf_counter()
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (compatible; MissouriPublicDataChat/1.0; +https://github.com/Stroudmj00/missouri-tiny-llm-case-study)",
            "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
        }
    )
    source_results: list[dict[str, Any]] = []
    for source in SOURCES:
        result: dict[str, Any] = source.__dict__.copy()
        try:
            response = fetch(session, source.url)
            result["status_code"] = response.status_code
            result["page_bytes"] = len(response.content)
            result["sample_links"] = extract_links(response.text, source.url, limit=12)
            if source.key == "data_mo_catalog":
                result["data_mo_probe"] = data_mo_catalog_probe(response.text)
            if source.key == "missouri_contracts":
                result["contract_probe"] = contract_probe(session)
            if source.key == "mshp_crash_data":
                result["mshp_probe"] = mshp_probe(response.text, source.url)
        except Exception as exc:  # noqa: BLE001 - source availability belongs in the report.
            result["fetch_warning"] = str(exc)
            if source.key == "mshp_crash_data":
                result["mshp_probe"] = mshp_static_fallback()
            if source.key == "sos_elections":
                result["sample_links"] = sos_static_links()
                result["page_bytes"] = 0
                result["status_code"] = None
        source_results.append(result)

    payload = {
        "generated_at_utc": utc_now(),
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "source_count": len(source_results),
        "default_policy": [
            "Run source preflight before downloading new data.",
            "Prefer aggregate tables and metadata before raw row-level files.",
            "Do not commit raw public downloads, contract indexes, health row-level files, or generated databases.",
            "Contract documents are linked first; PDF text extraction must be capped by limit and max_mb.",
        ],
        "sources": source_results,
    }
    write_json(REPORTS_DIR / "data_expansion_preflight.json", payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    print(json.dumps(preflight(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
