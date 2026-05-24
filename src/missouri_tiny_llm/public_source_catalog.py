"""Curated registry of Missouri public-data sources for the chatbot roadmap."""

from __future__ import annotations

from typing import Any


PUBLIC_SOURCE_CATALOG: list[dict[str, Any]] = [
    {
        "key": "map",
        "label": "Missouri Accountability Portal",
        "domain": "public finance",
        "url": "https://mapyourtaxes.mo.gov/MAP/Portal/Default.aspx",
        "status": "indexed",
        "access": "Public downloads and daily-updated MAP web tables.",
        "use_case": "Expenditures, employee pay, tax credits, federal grants, budget restrictions, bonds, and related transparency questions.",
        "risk": "Row-level public records need careful UI limits and privacy boundaries.",
    },
    {
        "key": "data_mo_catalog",
        "label": "State of Missouri data.mo.gov catalog",
        "domain": "open data catalog",
        "url": "https://data.mo.gov/data.json",
        "status": "cataloged",
        "access": "Socrata/data.json metadata and dataset CSV/JSON exports when public.",
        "use_case": "Discover and prioritize state datasets, including health, labor, natural resources, regulatory, and government administration data.",
        "risk": "Dataset schemas vary; some views are maps, files, filters, or stale records.",
    },
    {
        "key": "contracts",
        "label": "MissouriBUYS and OA contract search",
        "domain": "procurement",
        "url": "https://missouribuys.mo.gov/contractboard",
        "status": "indexed",
        "access": "Public contract board plus legacy OA statewide contract detail pages and document links.",
        "use_case": "Contract number, vendor, category, dates, document links, and MAP vendor-payment context.",
        "risk": "Legacy HTML/CGI structure can change; new MissouriBUYS transition may shift data surfaces.",
    },
    {
        "key": "contract_documents",
        "label": "OA contract award documents",
        "domain": "procurement documents",
        "url": "https://archive.oa.mo.gov/purch/contracts/",
        "status": "local optional extraction",
        "access": "Public PDF contract documents; downloaded and parsed locally only when a capped document index is built.",
        "use_case": "Plain-English contract explanations: what the state is buying, who the vendor is, term, renewal, contract type, and where to read the source document.",
        "risk": "PDF extraction can be imperfect; downloads must be capped to avoid storage spikes.",
    },
    {
        "key": "dese",
        "label": "DESE School Data",
        "domain": "education",
        "url": "https://dese.mo.gov/school-data",
        "status": "planned",
        "access": "Official school-data pages, dashboards, school directory exports, and public MCDS/DESE app surfaces.",
        "use_case": "District/school accountability, assessment, staff, finance, directory, and student-characteristic summaries.",
        "risk": "Some DESE surfaces are apps or secure portals; ingest only public downloadable outputs.",
    },
    {
        "key": "dhss",
        "label": "DHSS Data, Surveillance Systems & Statistical Reports",
        "domain": "public health",
        "url": "https://health.mo.gov/data/",
        "status": "planned",
        "access": "Public dashboards, profiles, reports, and aggregate health datasets.",
        "use_case": "County profiles, births, deaths, hospitalizations/PAS, BRFSS, opioid dashboards, and aggregate public-health trend explanations.",
        "risk": "Health data requires suppression, aggregation, and no person-level records.",
    },
    {
        "key": "mshp_sac",
        "label": "MSHP Statistical Analysis Center data files",
        "domain": "public safety",
        "url": "https://www.mshp.dps.mo.gov/MSHPWeb/SAC/data_960grid.html",
        "status": "planned",
        "access": "Small public Excel files for crime, crash, traffic arrest, and related aggregate tables.",
        "use_case": "Crash severity, fatalities, injuries, rates, alcohol/speed/young-driver/older-driver/commercial/motorcycle factors.",
        "risk": "Excel parsing dependency; avoid person-level incident reports.",
    },
    {
        "key": "meric",
        "label": "MERIC labor and unemployment data",
        "domain": "labor market",
        "url": "https://meric.mo.gov/data/unemployment",
        "status": "planned",
        "access": "Public reports, dashboard links, and local unemployment data.",
        "use_case": "County unemployment, labor force, wage, industry, projection, and regional profile questions.",
        "risk": "Many releases are PDFs or dashboards; exact current values need update timestamps.",
    },
    {
        "key": "dnr",
        "label": "Missouri DNR data and e-services",
        "domain": "environment",
        "url": "https://dnr.mo.gov/data-e-services",
        "status": "planned",
        "access": "Public environmental datasets, ArcGIS services, water permits, drinking water reports, impaired waters, and water-quality tools.",
        "use_case": "Water permits, public water systems, impaired waters, water quality, air/environmental reports, and GIS-style lookups.",
        "risk": "Many surfaces are search tools or map services; normalize by dataset before answering exact questions.",
    },
    {
        "key": "msdis",
        "label": "MSDIS geospatial open data",
        "domain": "geospatial",
        "url": "https://www.msdis.missouri.edu/",
        "status": "planned",
        "access": "Missouri GIS downloads, ArcGIS services, imagery, elevation, LiDAR, and vector layers.",
        "use_case": "County boundaries, administrative geography, public facilities, environmental overlays, and map-backed context.",
        "risk": "Imagery/LiDAR can be very large; start with vector metadata and small layers.",
    },
    {
        "key": "sos_elections",
        "label": "Missouri Secretary of State election results",
        "domain": "elections",
        "url": "https://www.sos.mo.gov/elections/s_default",
        "status": "watchlist",
        "access": "Official election-results pages; some precinct data may require purchase/contact.",
        "use_case": "Official statewide/county election results where downloadable public files are available.",
        "risk": "Not all result formats are bulk-download friendly; avoid voter-level data.",
    },
]


def catalog_by_status() -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for source in PUBLIC_SOURCE_CATALOG:
        grouped.setdefault(source["status"], []).append(source)
    return grouped
