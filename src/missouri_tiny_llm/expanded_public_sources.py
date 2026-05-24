"""Build and query a local index of Missouri public-data source pages.

The goal is not to mirror every external dataset. This index proves source
access, records useful official links, and gives the chatbot cited answers for
which public data families are connected.
"""

from __future__ import annotations

import argparse
import html
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
RAW_DIR = PROJECT_ROOT / "data" / "raw_public" / "expanded_sources"
REPORTS_DIR = PROJECT_ROOT / "reports"
PUBLIC_SOURCE_INDEX_PATH = RAW_DIR / "missouri_public_source_index.json"


@dataclass(frozen=True)
class SourceSpec:
    key: str
    label: str
    domain: str
    url: str
    useful_for: str
    question_terms: tuple[str, ...]
    focus_terms: tuple[str, ...]
    known_resources: tuple[tuple[str, str], ...] = ()


SOURCES: tuple[SourceSpec, ...] = (
    SourceSpec(
        key="data_mo_catalog",
        label="State of Missouri data.mo.gov catalog",
        domain="open data catalog",
        url="https://data.mo.gov/data.json",
        useful_for="finding Missouri public datasets and selecting stable CSV/JSON exports for future ingestion",
        question_terms=("data.mo.gov", "open data", "catalog", "dataset", "datasets", "socrata"),
        focus_terms=("Government Administration", "Health", "Natural Resources", "Labor", "Regulatory", "Public Safety"),
    ),
    SourceSpec(
        key="dese",
        label="DESE School Data",
        domain="education",
        url="https://dese.mo.gov/school-data",
        useful_for="school and district accountability, assessment, staff, finance, directory, and dashboard questions",
        question_terms=("dese", "school", "district", "education", "assessment", "accountability"),
        focus_terms=("accountability", "assessment", "staff", "finance", "directory", "district", "dashboard"),
        known_resources=(
            ("School Directory Data Downloads", "https://dese.mo.gov/school-directory/data-downloads"),
        ),
    ),
    SourceSpec(
        key="dhss",
        label="DHSS Data, Surveillance Systems & Statistical Reports",
        domain="public health",
        url="https://health.mo.gov/data/",
        useful_for="aggregate public-health questions about county profiles, births, deaths, hospitalizations, BRFSS, and surveillance reports",
        question_terms=("dhss", "health", "birth", "death", "brfss", "hospitalization", "county profile"),
        focus_terms=("county", "birth", "death", "hospital", "BRFSS", "MICA", "profile", "PAS"),
    ),
    SourceSpec(
        key="mshp_sac",
        label="MSHP Statistical Analysis Center data files",
        domain="public safety",
        url="https://www.mshp.dps.mo.gov/MSHPWeb/SAC/data_960grid.html",
        useful_for="aggregate crash and traffic safety questions such as fatalities, injuries, speed, alcohol, age, motorcycle, and commercial vehicle factors",
        question_terms=("mshp", "crash", "traffic safety", "fatality", "fatalities", "injury", "injuries"),
        focus_terms=("Crash", "Crashes", "Traffic", "Alcohol", "Speed", "Motorcycle", "CMV", "Young", "Older"),
        known_resources=(
            ("MSHP Crash Data definitions", "https://www.mshp.dps.mo.gov/MSHPWeb/SAC/crash_data_960grid.html"),
        ),
    ),
    SourceSpec(
        key="meric",
        label="MERIC labor and unemployment data",
        domain="labor market",
        url="https://meric.mo.gov/data/unemployment",
        useful_for="exact MERIC LAUS lookup for current Missouri and county unemployment rate, labor force, employment, and unemployed counts; source discovery for wages, occupations, projections, industries, and regional profiles",
        question_terms=("meric", "labor", "unemployment", "wage", "occupation", "jobs", "workforce"),
        focus_terms=("unemployment", "labor force", "wage", "occupation", "projection", "regional", "industry"),
    ),
    SourceSpec(
        key="dnr",
        label="Missouri DNR data and e-services",
        domain="environment",
        url="https://dnr.mo.gov/data-e-services",
        useful_for="environmental source discovery: water permits, public water systems, impaired waters, drinking water, and environmental GIS tools",
        question_terms=("dnr", "environment", "water", "permit", "impaired", "drinking water", "air quality"),
        focus_terms=("water", "permit", "impaired", "drinking", "GIS", "environmental", "wastewater"),
        known_resources=(
            ("Water Data and e-Services", "https://dnr.mo.gov/water/data-e-services"),
            ("Water Permits", "https://dnr.mo.gov/water/business-industry-other-entities/permits-certification-engineering-fees/water-permits"),
            ("Impaired Waters", "https://dnr.mo.gov/water/what-were-doing/water-planning/water-quality-standards/impaired-waters"),
        ),
    ),
    SourceSpec(
        key="msdis",
        label="MSDIS geospatial open data",
        domain="geospatial",
        url="https://www.msdis.missouri.edu/",
        useful_for="geospatial source discovery: GIS services, Missouri boundaries, imagery services, LiDAR services, and vector layers",
        question_terms=("msdis", "gis", "geospatial", "map layer", "boundary", "lidar", "imagery"),
        focus_terms=("Open Data", "Web Services", "ArcGIS", "Imagery", "LiDAR", "Mapping", "Services"),
    ),
    SourceSpec(
        key="modot",
        label="MoDOT traffic and transportation data",
        domain="transportation",
        url="https://www.modot.org/modatazone/traffic",
        useful_for="transportation source discovery: traffic counts, traffic volume, road/route context, and MoDOT data tools",
        question_terms=("modot", "traffic count", "traffic volume", "aadt", "road", "route", "transportation"),
        focus_terms=("traffic", "count", "volume", "AADT", "road", "route", "data", "safety"),
        known_resources=(
            ("Traffic Volume Maps", "https://www.modot.org/traffic-volume-maps"),
            ("MoDOT Traffic Data", "https://www.modot.org/modatazone/traffic"),
            ("MoDOT Safety", "https://www.modot.org/safety"),
        ),
    ),
    SourceSpec(
        key="state_auditor",
        label="Missouri State Auditor reports",
        domain="audits and accountability",
        url="https://auditor.mo.gov/AuditReport/Menu",
        useful_for="audit report discovery: state agencies, local governments, schools, courts, tax credits, data analytics, and local financial reports",
        question_terms=("auditor", "audit report", "audit reports", "state auditor", "local government financial"),
        focus_terms=("Audit", "Report", "Tax", "Financial", "Data", "Property", "Forfeiture", "Local Government"),
        known_resources=(
            ("Audit Reports", "https://auditor.mo.gov/AuditReport/Menu"),
            ("Local Government Financial Reports", "https://auditor.mo.gov/AuditReport/Menu"),
            ("Tax Increment Financing Reports", "https://auditor.mo.gov/AuditReport/Menu"),
        ),
    ),
    SourceSpec(
        key="dor_reports",
        label="Missouri Department of Revenue public reports",
        domain="tax and revenue",
        url="https://dor.mo.gov/public-reports/",
        useful_for="public revenue and tax reports, with exact aggregate lookup for the selected taxable-sales, business-location, vehicle, driver, dealer, and SIC files",
        question_terms=("dor", "department of revenue", "revenue report", "taxable sales", "food tax", "working family tax credit"),
        focus_terms=("Taxable", "Sales", "Tax Credit", "Food Tax", "Motor Vehicle", "Dealer", "Working Family", "Cigarette"),
        known_resources=(
            ("Public Taxable Sales Reports", "https://dor.mo.gov/public-reports/"),
            ("Food Tax by Political Subdivision", "https://dor.mo.gov/public-reports/"),
            ("Missouri Working Family Tax Credit Reports", "https://dor.mo.gov/public-reports/"),
        ),
    ),
    SourceSpec(
        key="mec",
        label="Missouri Ethics Commission public records",
        domain="ethics and campaign finance",
        url="https://mec.mo.gov/",
        useful_for="campaign finance, lobbying, committee contribution/expenditure, commission action, and ethics-law source discovery",
        question_terms=("mec", "ethics commission", "campaign finance", "committee contribution", "lobbying", "lobbyist"),
        focus_terms=("Campaign", "Committee", "Contribution", "Expenditure", "Lobby", "Commission", "Annual Report", "Candidate"),
        known_resources=(
            ("Committee Contributions & Expenditures", "https://mec.mo.gov/"),
            ("Lobbyist Reports", "https://mec.mo.gov/"),
            ("Commission Cases/Actions", "https://mec.mo.gov/"),
        ),
    ),
    SourceSpec(
        key="sos_elections",
        label="Missouri Secretary of State election data",
        domain="elections",
        url="https://www.sos.mo.gov/elections/s_default",
        useful_for="official election source discovery: election results, candidates, ballot measures, voter turnout, and election calendars",
        question_terms=("sos", "secretary of state", "election data", "election results", "candidate", "ballot measure"),
        focus_terms=("Election", "Results", "Candidate", "Ballot", "Voter", "Turnout", "Initiative", "Petition"),
        known_resources=(
            ("Election Results", "https://www.sos.mo.gov/elections/s_default"),
            ("Candidates and Ballot Measures", "https://www.sos.mo.gov/elections/s_default"),
            ("Voter Turnout and Election Calendars", "https://www.sos.mo.gov/elections/s_default"),
        ),
    ),
    SourceSpec(
        key="oa_budget",
        label="Office of Administration Budget and Planning",
        domain="budget and planning",
        url="https://oa.mo.gov/budget-and-planning",
        useful_for="budget source discovery: executive budget, revenue information, performance measures, demographics, redistricting, and fiscal policy context",
        question_terms=("oa budget", "budget and planning", "executive budget", "revenue information", "performance measure", "demographics"),
        focus_terms=("Budget", "Revenue", "Performance", "Demographics", "Redistricting", "Fiscal", "Appropriation"),
        known_resources=(
            ("Budget Information", "https://oa.mo.gov/budget-and-planning"),
            ("Revenue Information", "https://oa.mo.gov/budget-and-planning"),
            ("Performance Measures", "https://oa.mo.gov/budget-and-planning"),
        ),
    ),
    SourceSpec(
        key="child_care",
        label="DESE child care compliance dashboards",
        domain="child care",
        url="https://dese.mo.gov/childhood/child-care/child-care-data-dashboards",
        useful_for="child-care source discovery: regulated facilities, slots, pending facilities, inspections, complaints, and licensing timelines",
        question_terms=("child care", "childcare", "licensed child care", "child care inspections", "child care slots"),
        focus_terms=("Dashboard", "Quarter", "Inspection", "Complaint", "Facility", "Slots", "Licensed"),
        known_resources=(
            ("Child Care Compliance and Regulation Data Dashboard", "https://dese.mo.gov/childhood/child-care/child-care-data-dashboards"),
            ("Inspection and Complaint Investigations", "https://dese.mo.gov/childhood/child-care/child-care-data-dashboards"),
        ),
    ),
    SourceSpec(
        key="long_term_care",
        label="DHSS long-term care inspection data",
        domain="long-term care",
        url="https://health.mo.gov/safety/nursinghomesinspected/index.php",
        useful_for="long-term-care source discovery: nursing home and assisted-living inspections, complaints, facility types, beds, and survey context",
        question_terms=("long-term care", "long term care", "nursing home", "assisted living", "facility inspection", "ltc inspection"),
        focus_terms=("Nursing", "Long-Term", "Inspection", "Complaint", "Facility", "Beds", "Assisted", "Show Me"),
        known_resources=(
            ("Show Me Long-Term Care", "https://healthapps.dhss.mo.gov/showmelongtermcare/"),
            ("Nursing Homes Inspections", "https://health.mo.gov/safety/nursinghomesinspected/index.php"),
        ),
    ),
    SourceSpec(
        key="psc",
        label="Missouri Public Service Commission reports",
        domain="utilities",
        url="https://psc.mo.gov/General/PSC_Reports",
        useful_for="utility-regulation source discovery: PSC report volumes, utility filings, annual reports, and rate-case context",
        question_terms=("psc", "public service commission", "utility", "utilities", "rate case", "utility report"),
        focus_terms=("PSC", "Report", "Utility", "Consumer", "Annual", "Electric", "Gas", "Water", "Sewer"),
        known_resources=(
            ("PSC Reports", "https://psc.mo.gov/General/PSC_Reports"),
            ("Utility Consumer Information", "https://psc.mo.gov/"),
        ),
    ),
    SourceSpec(
        key="cannabis",
        label="DHSS Division of Cannabis Regulation reports",
        domain="cannabis regulation",
        url="https://health.mo.gov/safety/cannabis/",
        useful_for="cannabis-regulation source discovery: annual reports, sales dashboards, transfer history, licensed facilities, inspections, and product/regulatory updates",
        question_terms=("cannabis", "marijuana", "division of cannabis regulation", "dcr", "cannabis sales", "licensed dispensary"),
        focus_terms=("Data", "Reports", "Annual", "Sales", "License", "Facility", "Dashboard", "Transfer", "Microbusiness"),
        known_resources=(
            ("Data and Reports", "https://health.mo.gov/safety/cannabis/"),
            ("Medical and Adult-Use Cannabis Annual Reports", "https://health.mo.gov/safety/cannabis/"),
            ("Licensed Facilities", "https://health.mo.gov/safety/cannabis/"),
        ),
    ),
    SourceSpec(
        key="agriculture",
        label="Missouri Agricultural Market News reports",
        domain="agriculture",
        url="https://agmarketnews.mo.gov/reports/",
        useful_for="agricultural market source discovery: livestock, cattle, swine, sheep/goat, and regional market reports",
        question_terms=("agriculture", "agricultural", "livestock", "cattle", "swine", "sheep", "market report"),
        focus_terms=("Cattle", "Livestock", "Swine", "Sheep", "Goat", "Weekly", "Market", "Auction"),
        known_resources=(
            ("Missouri Cattle/Livestock Market Reports", "https://agmarketnews.mo.gov/reports/"),
            ("Swine Reports", "https://agmarketnews.mo.gov/reports/"),
            ("Sheep and Goat Reports", "https://agmarketnews.mo.gov/reports/"),
        ),
    ),
)

DEDICATED_PARSER_NOTES = {
    "dese": (
        "Dedicated parser status: selected exact lookup is implemented for the DESE School Directory by District PDF; "
        "accountability, staff, assessment, and finance reports still need separate parsers."
    ),
    "dhss": (
        "Dedicated parser status: selected exact aggregate lookup is implemented for the data.mo.gov Missouri Communicable Disease Report "
        "and DHSS WIC county/municipality aggregates; county profiles, MICA, births/deaths, hospitalizations, and BRFSS still need separate parsers."
    ),
    "long_term_care": (
        "Dedicated parser status: selected exact lookup is implemented for sanitized data.mo.gov LTC Directory rows "
        "and aggregate LTC Census Report rows; inspection reports, complaints, survey findings, and Show Me Long-Term Care details still need separate parsers."
    ),
    "dnr": (
        "Dedicated parser status: selected exact lookup is implemented for the data.mo.gov Consumer Confidence Report public drinking-water system rows; "
        "water permits, impaired waters, GIS layers, and broader environmental data still need separate parsers."
    ),
    "psc": (
        "Dedicated parser status: selected exact lookup is implemented for the data.mo.gov Find A Missouri Utility city/county provider table; "
        "PSC filings, rate cases, annual reports, and regulatory orders still need separate parsers."
    ),
    "mshp_sac": (
        "Dedicated parser status: exact aggregate crash-statistics lookup is implemented for the indexed SAC Excel files; "
        "crime and arrest files would need separate parsers."
    ),
    "dor_reports": (
        "Dedicated parser status: exact aggregate lookup is implemented for 2025 county taxable sales, business locations, "
        "vehicles, licensed drivers, dealer counts, and SIC location counts; other DOR report families still need parsers."
    ),
    "agriculture": (
        "Dedicated parser status: selected exact lookup is implemented for the data.mo.gov feed sample testing results table; "
        "market reports, seed samples, inspections, complaints, and enforcement sources still need separate parsers."
    ),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def clean_text(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value, flags=re.S)
    decoded = html.unescape(without_tags)
    return re.sub(r"\s+", " ", decoded).strip()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def extract_links(page_text: str, base_url: str, focus_terms: tuple[str, ...], limit: int = 18) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    seen: set[str] = set()
    focus_pattern = re.compile("|".join(re.escape(term) for term in focus_terms), flags=re.I) if focus_terms else None
    skip_pattern = re.compile(
        r"^(skip to|contact us|follow us|like us|email us|subscribe|mo\.gov|governor|find an agency|online services)$",
        flags=re.I,
    )
    for href, label in re.findall(r"<a\s+[^>]*href=['\"]([^'\"]+)['\"][^>]*>(.*?)</a>", page_text, flags=re.I | re.S):
        text = clean_text(label)
        if not text:
            continue
        if skip_pattern.search(text):
            continue
        absolute = urljoin(base_url, href)
        if absolute in seen:
            continue
        if focus_pattern and not (focus_pattern.search(text) or focus_pattern.search(absolute)):
            continue
        seen.add(absolute)
        links.append({"label": text[:160], "url": absolute})
        if len(links) >= limit:
            break
    return links


def data_mo_summary(page_text: str) -> dict[str, Any]:
    catalog = json.loads(page_text)
    datasets = catalog.get("dataset", [])
    theme_counts: dict[str, int] = {}
    distributions = 0
    titles: list[str] = []
    for dataset in datasets:
        if dataset.get("distribution"):
            distributions += 1
        title = clean_text(str(dataset.get("title", "")))
        if title and len(titles) < 10:
            titles.append(title)
        theme = dataset.get("theme") or "uncategorized"
        themes = theme if isinstance(theme, list) else [theme]
        for item in themes:
            theme_counts[str(item)] = theme_counts.get(str(item), 0) + 1
    top_themes = [
        {"label": label, "count": count}
        for label, count in sorted(theme_counts.items(), key=lambda item: item[1], reverse=True)[:8]
    ]
    return {
        "kind": "catalog",
        "dataset_count": len(datasets),
        "datasets_with_distribution": distributions,
        "top_themes": top_themes,
        "sample_titles": titles,
    }


def html_source_summary(spec: SourceSpec, page_text: str) -> dict[str, Any]:
    links = extract_links(page_text, spec.url, spec.focus_terms)
    file_links = [link for link in links if re.search(r"\.(csv|xlsx?|json|pdf)(?:$|\?)", link["url"], flags=re.I)]
    return {
        "kind": "source_page",
        "matched_link_count": len(links),
        "download_like_link_count": len(file_links),
        "sample_links": links,
        "known_resources": [{"label": label, "url": url} for label, url in spec.known_resources],
    }


def source_answer_summary(source: dict[str, Any]) -> str:
    summary = source.get("summary", {})
    if summary.get("kind") == "catalog":
        themes = ", ".join(f"{item['label']} ({item['count']})" for item in summary.get("top_themes", [])[:5])
        return (
            f"{source['label']} is connected as a catalog source with {summary.get('dataset_count', 0):,} datasets "
            f"and {summary.get('datasets_with_distribution', 0):,} datasets that list distributions. Top themes: {themes}."
        )
    link_labels = [link["label"] for link in summary.get("known_resources", [])[:3]]
    link_labels.extend(
        link["label"]
        for link in summary.get("sample_links", [])[:8]
        if not str(link.get("label", "")).lower().startswith("skip to")
    )
    link_labels = link_labels[:6]
    resource_text = "; ".join(link_labels) if link_labels else "source page is reachable, but no focused links were extracted"
    return f"{source['label']} is connected for {source['useful_for']}. Useful source links found: {resource_text}."


def build_public_source_index(force: bool = False, delay_seconds: float = 0.1) -> dict[str, Any]:
    if PUBLIC_SOURCE_INDEX_PATH.exists() and not force:
        return json.loads(PUBLIC_SOURCE_INDEX_PATH.read_text(encoding="utf-8"))

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (compatible; MissouriPublicDataChat/1.0; +https://github.com/Stroudmj00/missouri-tiny-llm-case-study)",
            "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
        }
    )
    start = time.perf_counter()
    sources: list[dict[str, Any]] = []
    for spec in SOURCES:
        row: dict[str, Any] = {
            "key": spec.key,
            "label": spec.label,
            "domain": spec.domain,
            "url": spec.url,
            "useful_for": spec.useful_for,
            "question_terms": list(spec.question_terms),
            "status": "not_checked",
        }
        try:
            response = session.get(spec.url, timeout=60)
            response.raise_for_status()
            row["status"] = "connected"
            row["status_code"] = response.status_code
            row["page_bytes"] = len(response.content)
            row["content_type"] = response.headers.get("content-type", "")
            if spec.key == "data_mo_catalog":
                row["summary"] = data_mo_summary(response.text)
            else:
                row["summary"] = html_source_summary(spec, response.text)
            row["answer_summary"] = source_answer_summary(row)
        except Exception as exc:  # noqa: BLE001 - keep other sources usable.
            row["status"] = "error"
            row["error"] = str(exc)
            row["summary"] = {"kind": "source_page", "sample_links": []}
            row["answer_summary"] = f"{spec.label} is registered, but the latest source fetch failed: {exc}"
        sources.append(row)
        if delay_seconds > 0:
            time.sleep(delay_seconds)

    connected = [source for source in sources if source.get("status") == "connected"]
    payload = {
        "generated_at_utc": utc_now(),
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "source_count": len(sources),
        "connected_source_count": len(connected),
        "local_index_path": str(PUBLIC_SOURCE_INDEX_PATH.relative_to(PROJECT_ROOT)),
        "notes": [
            "This is a source-page and catalog index, not a full mirror of every dataset.",
            "It lets the chatbot give cited, useful guidance for each connected public-data family.",
            "Exact row-level or numeric answers require a dedicated parser/index for the selected dataset.",
            "Dedicated exact lookup currently exists for MAP, data.mo.gov catalog metadata, selected data.mo.gov education rows, selected DESE School Directory rows, selected data.mo.gov public-health aggregate rows, selected DHSS WIC aggregate rows, selected data.mo.gov LTC directory/census rows, selected data.mo.gov DNR water rows, selected data.mo.gov utility-provider rows, selected data.mo.gov agriculture feed-sample rows, indexed MSHP crash aggregate files, selected DOR aggregate reports, and MERIC LAUS labor-market CSV rows.",
        ],
        "sources": sources,
    }
    write_json(PUBLIC_SOURCE_INDEX_PATH, payload)
    write_json(
        REPORTS_DIR / "public_source_index_report.json",
        {key: value for key, value in payload.items() if key != "sources"}
        | {
            "sources": [
                {
                    "key": source["key"],
                    "label": source["label"],
                    "status": source["status"],
                    "url": source["url"],
                    "answer_summary": source.get("answer_summary"),
                }
                for source in sources
            ]
        },
    )
    return payload


class PublicSourceIndex:
    def __init__(self, path: Path = PUBLIC_SOURCE_INDEX_PATH) -> None:
        self.path = path
        self._payload: dict[str, Any] | None = None

    def available(self) -> bool:
        return self.path.exists() and self.path.stat().st_size > 0

    def payload(self) -> dict[str, Any]:
        if self._payload is None:
            self._payload = json.loads(self.path.read_text(encoding="utf-8")) if self.available() else {}
        return self._payload

    def sources(self) -> list[dict[str, Any]]:
        return list(self.payload().get("sources", []))

    def find_source(self, question: str) -> dict[str, Any] | None:
        lowered = question.lower()
        ranked: list[tuple[int, dict[str, Any]]] = []
        for source in self.sources():
            terms = [str(term).lower() for term in source.get("question_terms", [])]
            score = sum(1 for term in terms if term in lowered)
            if source["key"] == "data_mo_catalog" and "data.mo.gov" in lowered:
                score += 3
            if score:
                ranked.append((score, source))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return ranked[0][1] if ranked else None

    def citation_for_source(self, source: dict[str, Any]) -> list[dict[str, Any]]:
        source_files = [
            {
                "category": source.get("key", "public_source"),
                "category_label": source.get("label", "Public source"),
                "file_name": source.get("url", ""),
                "row_count": None,
                "bytes": source.get("page_bytes"),
                "sha256": None,
            }
        ]
        for link in source.get("summary", {}).get("sample_links", [])[:5]:
            source_files.append(
                {
                    "category": source.get("key", "public_source"),
                    "category_label": link.get("label", "Source link"),
                    "file_name": link.get("url", ""),
                    "row_count": None,
                    "bytes": None,
                    "sha256": None,
                }
            )
        return [
            {
                "dataset": "Missouri public source index",
                "category": source.get("label", "Public source"),
                "kind": "source-page index",
                "lookup_table": "missouri_public_source_index",
                "year": 2026,
                "year_range": None,
                "source_files": source_files,
                "source_file_count": len(source_files),
                "source_rows": None,
                "matched_rows": 1,
            }
        ]

    def answer(self, question: str) -> dict[str, Any] | None:
        source = self.find_source(question)
        if source is None:
            return None
        summary = source.get("summary", {})
        lines = [
            f"{source['label']} is connected.",
            f"Usefulness: {source['useful_for']}.",
        ]
        if summary.get("kind") == "catalog":
            lines.append(
                f"Indexed catalog evidence: {summary.get('dataset_count', 0):,} datasets, "
                f"{summary.get('datasets_with_distribution', 0):,} with distributions."
            )
            themes = ", ".join(f"{item['label']} ({item['count']})" for item in summary.get("top_themes", [])[:6])
            if themes:
                lines.append(f"Top catalog themes: {themes}.")
            titles = "; ".join(summary.get("sample_titles", [])[:5])
            if titles:
                lines.append(f"Sample dataset titles: {titles}.")
        else:
            links = summary.get("sample_links", [])
            known = summary.get("known_resources", [])
            if known:
                rendered_known = "; ".join(f"{link['label']} ({link['url']})" for link in known[:3])
                lines.append(f"Known related resources: {rendered_known}.")
            if links:
                filtered_links = [
                    link
                    for link in links
                    if not str(link.get("label", "")).lower().startswith("skip to")
                ]
                rendered = "; ".join(f"{link['label']} ({link['url']})" for link in filtered_links[:5])
                lines.append(f"Useful official links found: {rendered}.")
            lines.append(
                f"Source index evidence: status {source.get('status')}; page bytes {source.get('page_bytes', 'unknown')}; "
                f"focused links {summary.get('matched_link_count', 0)}."
            )
        parser_note = DEDICATED_PARSER_NOTES.get(source.get("key"))
        if parser_note:
            lines.append(parser_note)
        else:
            lines.append("Next implementation step: choose one specific table/file from this source and add a dedicated parser for exact numeric answers.")
        return {
            "question": question,
            "answer": "\n".join(lines),
            "retrieved_context_id": f"missouri_public_source_index:{source['key']}",
            "retrieved_source": "missouri_public_source_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Answered from the local public-source index built from official Missouri source pages.",
            "citations": self.citation_for_source(source),
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--delay-seconds", type=float, default=0.1)
    args = parser.parse_args()
    payload = build_public_source_index(force=args.force, delay_seconds=args.delay_seconds)
    print(json.dumps({key: value for key, value in payload.items() if key != "sources"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
