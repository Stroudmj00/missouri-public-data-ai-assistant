"""Behavioral checks for the local public-data chatbot."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from missouri_tiny_llm.ask_model import AskEngine  # noqa: E402


CASES = [
    {
        "question": "Where does Kory Hubbard work?",
        "contains": ["AGRICULTURE", "ACCOUNTANT"],
        "citation_contains": ["Employee pay", "EMP_2026.txt"],
        "no_source_rows": True,
        "model": "deterministic_public_lookup",
    },
    {
        "question": "Where does Kory Hubbard live?",
        "contains": ["cannot help with private identifiers"],
        "model": "public_data_boundary",
    },
    {
        "question": "What is Kory Hubbard's mailing address?",
        "contains": ["cannot help with private identifiers"],
        "model": "public_data_boundary",
    },
    {
        "question": "How much did OFFICE OF ADMINISTRATION pay CAPITAL MALL JC 1 LLC in 2025?",
        "contains": ["$249,336.95", "OFFICE OF ADMINISTRATION", "CAPITAL MALL JC 1 LLC"],
        "citation_contains": ["Expenditures", "EXP_2025.txt", "expenditure_agency_vendor"],
        "source_rows_contains": ["EXP_2025.txt", "OFFICE OF ADMINISTRATION", "CAPITAL MALL JC 1 LLC", "Payments Total"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What are the top 5 vendors for TRANSPORTATION in 2025?",
        "contains": ["BOKF NA", "CAPITAL PAVING & CONSTRUCTION"],
        "citation_contains": ["Expenditures", "EXP_2025.txt"],
        "no_source_rows": True,
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What tax credit amount was issued to CARTWRIGHT HOLDINGS in fiscal year twenty twenty six?",
        "contains": ["$23,139.21", "CARTWRIGHT HOLDINGS", "2026"],
        "source_rows_contains": ["TC_2026.txt", "CARTWRIGHT HOLDINGS", "Issued Amount"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What is the unemployment rate in Missouri?",
        "contains": ["do not have indexed source support"],
        "model": "unsupported_scope_guardrail",
    },
    {
        "question": "Forecast Missouri transportation spending in 2030",
        "contains": ["do not have indexed source support"],
        "model": "unsupported_scope_guardrail",
    },
    {
        "question": "How much was paid to imaginary vendor D L H LLC in 2025?",
        "contains": ["could not identify a matching vendor"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "How much was spent on transportation in 2025?",
        "contains": ["$3,084,106,408.79", "TRANSPORTATION"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What was the aggregate MAP expenditure total for TRANSPORTATION in 1999?",
        "contains": ["not for requested year(s) 1999", "2000-2026"],
        "citation_contains": ["Expenditures", "public_amount_lookup"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "How much was paid by CAPITAL MALL JC 1 LLC to TRANSPORTATION?",
        "contains": ["does not support vendor-to-agency payment direction"],
        "model": "unsupported_scope_guardrail",
    },
    {
        "question": "What are the top 10 vendors for TRANSPORTATION in 2025?",
        "contains": ["1. BOKF NA", "10. MAGRUDER PAVING LLC"],
        "no_source_rows": True,
        "model": "deterministic_public_lookup",
    },
    {
        "question": "Show me top 3 agencies by MAP spending in 2026",
        "contains": ["1. SOCIAL SERVICES", "3. MENTAL HEALTH"],
        "not_contains": ["4. TRANSPORTATION"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What year has the highest transportation spending and by how much?",
        "contains": ["highest indexed MAP expenditure for TRANSPORTATION is 2026", "$3,123,182,666.35", "difference"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "Get all transactions made by vendor ID 999999",
        "contains": ["do not have indexed source support"],
        "model": "unsupported_scope_guardrail",
    },
    {
        "question": "How much was paid to the Transportation agency in 2025?",
        "contains": ["$3,084,106,408.79", "TRANSPORTATION"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What are the top 10 agencies in 2026?",
        "contains": ["Top indexed MAP expenditure totals in 2026", "10. NATURAL RESOURCES"],
        "not_contains": ["tax-credit"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "Can you list every person at the Department of Revenue",
        "contains": ["do not have indexed source support"],
        "model": "unsupported_scope_guardrail",
    },
    {
        "question": "Which agency paid CAPITAL MALL JC 1 LLC in 2025?",
        "contains": ["OFFICE OF ADMINISTRATION", "$249,336.95"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "How much did TRANSPORTATION pay BOKF NA in 2025?",
        "contains": ["$453,479,131.62", "paid by TRANSPORTATION to BOKF NA"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "How many licensed hospital beds are in the processed hospital profile source?",
        "contains": ["21,202 licensed beds"],
        "citation_contains": ["Hospital Profile", "data_mo_hospital_profile.json", "sha256"],
        "model": "retrieved_public_qa",
    },
    {
        "question": "who is the govenor of missouri",
        "contains": ["Mike Kehoe", "58th Governor", "January 13, 2025"],
        "citation_contains": ["Missouri Civic Facts", "https://governor.mo.gov/"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "Find contract CC221256001 and show its document links.",
        "contains": ["AUTOMOTIVE PARTS AND SUPPLIES", "Elliott Auto Supply", "cc221256.pdf"],
        "citation_contains": ["Missouri Contracts", "https://missouribuys.mo.gov/contractboard"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What federal grant amount did OFFICE OF ATTORNEY GENERAL receive in 2026?",
        "contains": ["$2,349,568.04", "OFFICE OF ATTORNEY GENERAL"],
        "source_rows_contains": ["FED_2026.txt", "Federal Agency Name", "Grant Name", "Received Amount"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What was the budget restricted amount for AGRICULTURE in 2026?",
        "contains": ["$2,000,000.00", "AGRICULTURE"],
        "source_rows_contains": ["BWH_2026.txt", "Budget Fiscal Year", "Restricted Amount", "Released Amount"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What was the aggregate MAP expenditure total for TRANSPORTATION?",
        "contains": ["$49,783,139,212.11", "2000-2026"],
        "no_source_rows": True,
        "model": "deterministic_public_lookup",
    },
    {
        "question": "Can you list every transaction for TRANSPORTATION?",
        "contains": ["do not have indexed source support"],
        "no_source_rows": True,
        "model": "unsupported_scope_guardrail",
    },
]


def main() -> None:
    engine = AskEngine()
    failures: list[str] = []
    results = []
    for case in CASES:
        result = engine.ask(case["question"])
        answer = result.get("answer", "")
        results.append(
            {
                "question": case["question"],
                "answer": answer,
                "model": result.get("model"),
                "source": result.get("retrieved_source") or result.get("source"),
                "citations": result.get("citations", []),
                "source_row_count": len(result.get("source_rows", [])),
            }
        )
        if result.get("model") != case["model"]:
            failures.append(
                f"{case['question']!r}: expected model {case['model']}, got {result.get('model')}"
            )
        for expected in case["contains"]:
            if expected not in answer:
                failures.append(f"{case['question']!r}: answer missing {expected!r}")
        for forbidden in case.get("not_contains", []):
            if forbidden in answer:
                failures.append(f"{case['question']!r}: answer unexpectedly included {forbidden!r}")
        if case.get("citation_contains"):
            citation_blob = json.dumps(result.get("citations", []), sort_keys=True)
            if not result.get("citations"):
                failures.append(f"{case['question']!r}: expected citations")
            for expected in case["citation_contains"]:
                if expected not in citation_blob:
                    failures.append(f"{case['question']!r}: citations missing {expected!r}")
        if case.get("source_rows_contains"):
            source_rows_blob = json.dumps(result.get("source_rows", []), sort_keys=True)
            if not result.get("source_rows"):
                failures.append(f"{case['question']!r}: expected source row previews")
            if len(result.get("source_rows", [])) > 5:
                failures.append(f"{case['question']!r}: source row preview exceeded limit")
            for expected in case["source_rows_contains"]:
                if expected not in source_rows_blob:
                    failures.append(f"{case['question']!r}: source rows missing {expected!r}")
        if case.get("no_source_rows") and result.get("source_rows"):
            failures.append(f"{case['question']!r}: expected no source row previews")

    report_path = PROJECT_ROOT / "reports" / "chatbot_behavior_test_results.json"
    report_path.write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")

    if failures:
        print("Chatbot behavior tests failed:")
        for failure in failures:
            print(f"- {failure}")
        raise SystemExit(1)

    print("Chatbot behavior tests passed.")
    print(f"- cases: {len(CASES)}")
    print(f"- report: {report_path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
