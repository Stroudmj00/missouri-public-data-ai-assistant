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
        phase_one_scope="Catalog official DESE data sections for accountability, dashboard, staff, finance, assessment, and directory data.",
        ingestion_mode="Source registry first; add specific downloads after identifying stable public exports.",
        risk="moderate: several DESE datasets are behind apps or report portals rather than simple static files.",
    ),
    ExpansionSource(
        key="dhss_public_health",
        label="DHSS Data, Surveillance Systems & Statistical Reports",
        domain="public_health",
        url="https://health.mo.gov/data/",
        phase_one_scope="Catalog public-health domains: county profiles, births, deaths, hospitalizations/PAS, BRFSS, and dashboards.",
        ingestion_mode="Source registry first; prefer aggregate public files and avoid row-level health records.",
        risk="high: health datasets require careful privacy and suppression handling.",
    ),
    ExpansionSource(
        key="mshp_crash_data",
        label="MSHP crash and traffic safety data files",
        domain="traffic_safety",
        url="https://www.mshp.dps.mo.gov/MSHPWeb/SAC/data_960grid.html",
        phase_one_scope="Inventory small official Excel crash-statistics files for severity, rates, circumstances, and factor involvement.",
        ingestion_mode="Static Excel files; likely safe aggregate tables.",
        risk="low: small aggregate files, but .xls parsing requires xlrd.",
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


def preflight() -> dict[str, Any]:
    start = time.perf_counter()
    session = requests.Session()
    source_results: list[dict[str, Any]] = []
    for source in SOURCES:
        result: dict[str, Any] = source.__dict__.copy()
        try:
            response = fetch(session, source.url)
            result["status_code"] = response.status_code
            result["page_bytes"] = len(response.content)
            result["sample_links"] = extract_links(response.text, source.url, limit=12)
            if source.key == "missouri_contracts":
                result["contract_probe"] = contract_probe(session)
            if source.key == "mshp_crash_data":
                result["mshp_probe"] = mshp_probe(response.text, source.url)
        except Exception as exc:  # noqa: BLE001 - source availability belongs in the report.
            result["error"] = str(exc)
            if source.key == "mshp_crash_data":
                result["mshp_probe"] = mshp_static_fallback()
        source_results.append(result)

    payload = {
        "generated_at_utc": utc_now(),
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "source_count": len(source_results),
        "default_policy": [
            "Run source preflight before downloading new data.",
            "Prefer aggregate tables and metadata before raw row-level files.",
            "Do not commit raw public downloads, contract indexes, health row-level files, or generated databases.",
            "Contract documents are linked first and downloaded only if a later phase needs document text extraction.",
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
