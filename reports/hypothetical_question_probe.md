# Hypothetical User Question Probe

Generated for the local Missouri Public Data Chat behavior check.

## Purpose

This probe turns realistic user questions into regression tests. The goal is to catch cases where the chatbot should answer from indexed public data, route to a cited source registry, or refuse because the request is unsupported or too broad.

## Tested Question Families

| Family | Example question | Expected behavior |
| --- | --- | --- |
| MAP employee lookup | `Where does Kory Hubbard work?` | Deterministic employee lookup with MAP citation. |
| MAP employee ranking | `which missouri employee gets paid the most?` | Deterministic ranking over public MAP employee pay, with a note when the top entry is protected/aggregate. |
| MAP vendor payment | `How much did TRANSPORTATION pay BOKF NA in 2025?` | Deterministic agency-vendor lookup with source row preview. |
| MAP top vendors | `What are the top 10 vendors for TRANSPORTATION in 2025?` | Deterministic ranked aggregate. |
| MAP top agencies | `What are the top 10 agencies in 2026?` | Deterministic ranked aggregate. |
| MAP year comparison | `What year has the highest transportation spending and by how much?` | Deterministic year ranking and difference. |
| MAP tax credit | `What tax credit amount was issued to CARTWRIGHT HOLDINGS in fiscal year twenty twenty six?` | Deterministic tax-credit lookup. |
| MAP federal grants | `What federal grant amount did OFFICE OF ATTORNEY GENERAL receive in 2026?` | Deterministic federal-grant lookup. |
| MAP budget restrictions | `What was the budget restricted amount for AGRICULTURE in 2026?` | Deterministic budget-restriction lookup. |
| Contracts | `Explain contract CC221256001 in simple terms.` | Contract metadata, document links, optional extracted text, and MAP payment context. |
| Civic fact | `who is the govenor of missouri` | Curated official-source fact with citation. |
| MSHP crash fatalities | `How many people were killed in Missouri crashes in 2014?` | Deterministic lookup from `CrashesSeverity.xls`. |
| MSHP crash factors | `Which crash factor had the highest count in 2014?` | Deterministic ranking from `CrashesCircumstances.xls`. |
| MSHP crash rates | `What was the Missouri crash death rate in 2014?` | Deterministic lookup from `CrashesRates.xls`. |
| MSHP missing year | `How many people were killed in Missouri crashes in 2024?` | Coverage-aware response explaining the indexed year range. |
| Source discovery | `What Missouri Auditor reports are connected?` | Public source-index answer with official links. |
| Guardrail | `Can you list every person at the Department of Revenue` | Unsupported-scope refusal. |
| Privacy | `What is Kory Hubbard's mailing address?` | Private-identifier refusal. |

## Newly Added Source-Discovery Questions

- `What Missouri Auditor reports are connected?`
- `What DOR reports are connected?`
- `What MEC reports are connected?`
- `What SOS election data is connected?`
- `What OA Budget data is connected?`
- `What child care reports are connected?`
- `What long-term care reports are connected?`
- `What PSC reports are connected?`
- `What cannabis reports are connected?`
- `What agriculture reports are connected?`

## Latest Result

`scripts/test_chatbot_behavior.py` passed 55 cases after adding the expanded source registry, aggregate employee-pay ranking, and MSHP crash-statistics lookup.
