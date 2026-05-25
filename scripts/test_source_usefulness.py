"""Probe whether representative public-data sources answer useful cited questions."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from missouri_tiny_llm.ask_model import AskEngine  # noqa: E402


CASES = [
    {
        "family": "MAP expenditures",
        "question": "How much did TRANSPORTATION pay BOKF NA in 2025?",
        "contains": ["$453,479,131.62", "TRANSPORTATION", "BOKF NA"],
        "source_contains": ["mapyourtaxes.mo.gov/MAP/Download"],
    },
    {
        "family": "Contracts",
        "question": "Explain contract CC221256001 in simple terms.",
        "contains": ["CC221256001", "Elliott Auto Supply"],
        "source_contains": ["archive.oa.mo.gov/purch/contracts"],
    },
    {
        "family": "data.mo.gov catalog",
        "question": "Which data.mo.gov datasets mention hospital?",
        "contains": ["hospital", "exact hospital-profile lookup is implemented", "Which hospital has the most licensed beds?"],
        "source_contains": ["data.mo.gov"],
    },
    {
        "family": "Hospital profile",
        "question": "How many licensed hospital beds are in the hospital profile?",
        "contains": ["21,202", "licensed beds"],
        "source_contains": ["data.mo.gov/d/q8me-hzr8"],
    },
    {
        "family": "DESE School Directory",
        "question": "What county is Columbia 93 in?",
        "contains": ["BOONE", "Columbia 93"],
        "source_contains": ["dese.mo.gov"],
    },
    {
        "family": "DESE APR rankings",
        "question": "What is the APR score for Atlas Public Schools?",
        "contains": ["Atlas Public Schools", "APR"],
        "source_contains": ["dese.mo.gov"],
    },
    {
        "family": "DESE finance transfers",
        "question": "What is Columbia 93's DESE 7% transfer amount?",
        "contains": ["Columbia 93", "7%"],
        "source_contains": ["dese.mo.gov"],
    },
    {
        "family": "DESE special education",
        "question": "What DESE special education data is indexed?",
        "contains": ["special-education", "incidence"],
        "source_contains": ["dese.mo.gov"],
    },
    {
        "family": "DHSS communicable disease",
        "question": "How many anaplasmosis cases are listed YTD in the Missouri communicable disease report?",
        "contains": ["anaplasmosis", "YTD"],
        "source_contains": ["data.mo.gov"],
    },
    {
        "family": "DHSS BRFSS",
        "question": "What percent of Missouri adults had obesity in BRFSS?",
        "contains": ["obesity", "%"],
        "source_contains": ["health.mo.gov/data/brfss"],
    },
    {
        "family": "DHSS vital statistics",
        "question": "How many deaths were reported in Missouri in 2023?",
        "contains": ["deaths", "2023"],
        "source_contains": ["health.mo.gov/data/focus"],
    },
    {
        "family": "DHSS MOPHIMS",
        "question": "How many septicemia inpatient hospitalizations are listed for Boone County in MOPHIMS?",
        "contains": ["Boone County", "septicemia"],
        "source_contains": ["ProfileBuilder"],
    },
    {
        "family": "DHSS WIC",
        "question": "How many WIC household rows are listed for Boone County?",
        "contains": ["Boone County", "WIC"],
        "source_contains": ["data.mo.gov"],
    },
    {
        "family": "Food pantries",
        "question": "How many food pantries are listed in Boone County?",
        "contains": ["Boone County", "food"],
        "source_contains": ["data.mo.gov"],
    },
    {
        "family": "LTC directory/census",
        "question": "What is the statewide LTC census occupancy ratio?",
        "contains": ["statewide", "occupancy"],
        "source_contains": ["data.mo.gov"],
    },
    {
        "family": "LTC inspections",
        "question": "Where can I look up LTC inspections for Boone County?",
        "contains": ["Boone County", "inspection"],
        "source_contains": ["health.mo.gov"],
    },
    {
        "family": "DNR water",
        "question": "What is the PWSID for City of Columbia Utilities?",
        "contains": ["City of Columbia Utilities", "PWSID"],
        "source_contains": ["data.mo.gov"],
    },
    {
        "family": "DNR oil and gas",
        "question": "What is DNR oil and gas permit 013-00120?",
        "contains": ["013-00120"],
        "source_contains": ["data.mo.gov"],
    },
    {
        "family": "DNR hazardous waste",
        "question": "What is listed for EPA ID MOD054950670?",
        "contains": ["MOD054950670"],
        "source_contains": ["data.mo.gov"],
    },
    {
        "family": "DNR impaired waters",
        "question": "How many impaired water listings are in Boone County?",
        "contains": ["Boone County", "impaired"],
        "source_contains": ["dnr.mo.gov"],
    },
    {
        "family": "MSDIS geospatial",
        "question": "Give me MSDIS county boundary links",
        "contains": ["county", "boundary"],
        "source_contains": ["msdis"],
    },
    {
        "family": "MoDOT AADT",
        "question": "Show MoDOT AADT for MO 163 near Green Meadows Road.",
        "contains": ["MO 163", "AADT"],
        "source_contains": ["mapping.modot.mo.gov"],
    },
    {
        "family": "MSHP crashes",
        "question": "How many crashes were in Boone County in 2023?",
        "contains": ["Boone County", "2,341"],
        "source_contains": ["TrafficCompendium"],
    },
    {
        "family": "DOR reports",
        "question": "What were Boone County taxable sales in 2025?",
        "contains": ["Boone County", "taxable sales"],
        "source_contains": ["dor.mo.gov"],
    },
    {
        "family": "DOR reports",
        "question": "How did Boone County taxable sales change from 2024 to 2025?",
        "contains": ["Boone County", "2024", "2025", "increased"],
        "source_contains": ["DI60IL02_TXB_CNTY_F_2024.zip", "DI60IL02_TXB_CNTY_F_2025.zip"],
    },
    {
        "family": "DOR reports",
        "question": "How did Boone County food tax change from FY24 to FY25?",
        "contains": ["Boone County", "FY24", "FY25", "increased"],
        "source_contains": ["FY24-Combined-totals.pdf", "FY25-Combined-totals.pdf"],
    },
    {
        "family": "DOR Working Family Tax Credit",
        "question": "How did total Working Family Tax Credit amount change from 2024 to 2025?",
        "contains": ["Working Family Tax Credit", "2024", "2025", "increased"],
        "source_contains": ["2024-MO-WFTC-Report.pdf", "2025-MO-WFTC-Report.pdf"],
    },
    {
        "family": "DOR quarterly tax credits",
        "question": "Which tax credit had the highest issued FY to date in FY26 Q3?",
        "contains": ["Low Income Housing", "issued FY-to-date"],
        "source_contains": ["FY26-thirdquarter-tax-credit-report.pdf"],
    },
    {
        "family": "MERIC LAUS",
        "question": "What is Boone County unemployment rate in March 2026?",
        "contains": ["Boone County", "March 2026"],
        "source_contains": ["meric.mo.gov"],
    },
    {
        "family": "MEC resources",
        "question": "What MEC reports are connected?",
        "contains": ["MEC", "resource"],
        "source_contains": ["mec.mo.gov"],
    },
    {
        "family": "MEC annual reports",
        "question": "How many registered lobbyists were listed in the 2025 MEC annual report?",
        "contains": ["registered lobbyists", "2025"],
        "source_contains": ["mec.mo.gov"],
    },
    {
        "family": "SOS elections",
        "question": "Who won the 2024 Missouri governor election?",
        "contains": ["2024", "Governor"],
        "source_contains": ["sos.mo.gov"],
    },
    {
        "family": "State Auditor",
        "question": "Give me the link for Auditor report 2026-044",
        "contains": ["2026-044"],
        "source_contains": ["auditor.mo.gov"],
    },
    {
        "family": "PSC reports",
        "question": "Explain PSC report volume 33 in simple terms.",
        "contains": ["PSC", "Vol 33"],
        "source_contains": ["psc.mo.gov"],
    },
    {
        "family": "OA Budget",
        "question": "What OA Budget data is connected?",
        "contains": ["Budget", "Planning"],
        "source_contains": ["budplan.oa.mo.gov"],
    },
    {
        "family": "OA revenue detail",
        "question": "What were net general revenue collections in January 2026?",
        "contains": ["January 2026", "net general revenue"],
        "source_contains": ["budplan.oa.mo.gov"],
    },
    {
        "family": "Child care",
        "question": "How many child care slots are listed in 2025 Q4?",
        "contains": ["2025 Q4", "child care slots"],
        "source_contains": ["dese.mo.gov"],
    },
    {
        "family": "Utilities",
        "question": "What utilities serve Columbia in Boone County?",
        "contains": ["Columbia", "Boone County"],
        "source_contains": ["data.mo.gov"],
    },
    {
        "family": "Agriculture feed testing",
        "question": "What are the protein values for sample D202500550?",
        "contains": ["D202500550", "protein"],
        "source_contains": ["data.mo.gov"],
    },
    {
        "family": "Farmers markets",
        "question": "How many farmers markets are listed in Adair County?",
        "contains": ["Adair County", "listing row"],
        "source_contains": ["data.mo.gov/d/2zg8-cta8"],
    },
    {
        "family": "Agricultural Market News",
        "question": "What does the latest Missouri hay report say about demand and supplies?",
        "contains": ["hay", "demand", "supplies"],
        "source_contains": ["ams.usda.gov"],
    },
    {
        "family": "Cannabis",
        "question": "How many verified cannabis dispensaries are in Boone County?",
        "contains": ["Boone County", "dispensaries"],
        "source_contains": ["health.mo.gov/safety/cannabis"],
    },
]


def http_source_links(result: dict[str, Any]) -> list[str]:
    links: list[str] = []
    for citation in result.get("citations", []):
        for source_file in citation.get("source_files", []):
            for key in ("source_url", "file_name"):
                value = str(source_file.get(key) or "")
                if value.startswith(("http://", "https://")) and value not in links:
                    links.append(value)
    for row in result.get("source_rows", []):
        value = str(row.get("source_file") or "")
        if value.startswith(("http://", "https://")) and value not in links:
            links.append(value)
    value = str(result.get("source_url") or "")
    if value.startswith(("http://", "https://")) and value not in links:
        links.append(value)
    return links


def main() -> None:
    engine = AskEngine()
    failures: list[str] = []
    results: list[dict[str, Any]] = []

    for case in CASES:
        result = engine.ask(case["question"])
        answer = str(result.get("answer") or "")
        links = http_source_links(result)
        source_blob = "\n".join(links)
        case_failures: list[str] = []

        if result.get("model") in {"retrieval_guardrail", "unsupported_scope_guardrail", "public_data_boundary"}:
            case_failures.append(f"unexpected guardrail model {result.get('model')}")
        if not links:
            case_failures.append("missing official HTTP source link")
        for expected in case.get("contains", []):
            if expected.lower() not in answer.lower():
                case_failures.append(f"answer missing {expected!r}")
        for expected in case.get("source_contains", []):
            if expected.lower() not in source_blob.lower():
                case_failures.append(f"source links missing {expected!r}")

        record = {
            "family": case["family"],
            "question": case["question"],
            "answer": answer,
            "model": result.get("model"),
            "retrieved_source": result.get("retrieved_source") or result.get("source"),
            "source_links": links,
            "ok": not case_failures,
            "failures": case_failures,
        }
        results.append(record)
        for failure in case_failures:
            failures.append(f"{case['family']}: {failure}")

    report_path = PROJECT_ROOT / "reports" / "source_usefulness_probe.json"
    report_path.write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")

    if failures:
        print("Source usefulness probe failed:")
        for failure in failures:
            print(f"- {failure}")
        print(f"- report: {report_path.relative_to(PROJECT_ROOT)}")
        raise SystemExit(1)

    print("Source usefulness probe passed.")
    print(f"- cases: {len(CASES)}")
    print(f"- report: {report_path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
