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
| DOR taxable sales | `What were Boone County taxable sales in 2025?` | Deterministic lookup from the 2025 county Sales/Use taxable-sales zip. |
| DOR business locations | `How many business locations are in Columbia in Boone County?` | Deterministic lookup from the DOR business-location text report. |
| DOR vehicles/drivers/dealers | `How many licensed drivers are in Boone County?` | Deterministic aggregate lookup with DOR citations and no dealer address/phone output. |
| DOR unsupported year | `What were Boone County taxable sales in 2024?` | Coverage-aware response explaining that only the 2025 county taxable-sales file is parsed. |
| MERIC Missouri unemployment | `What is the unemployment rate in Missouri?` | Deterministic lookup from the MERIC LAUS CSV route, using the seasonally adjusted statewide row. |
| MERIC county unemployment | `What is Boone County unemployment rate in March 2026?` | Deterministic lookup from the MERIC LAUS county CSV chunks. |
| MERIC county ranking | `Which county had the highest unemployment rate in March 2026?` | Deterministic ranking over indexed county LAUS rows. |
| data.mo.gov catalog themes | `What are the top data.mo.gov catalog themes?` | Deterministic metadata lookup from the local DCAT catalog index. |
| data.mo.gov dataset search | `Which data.mo.gov datasets mention hospital?` | Deterministic catalog search returning dataset title, ID, landing page, and distribution link. |
| data.mo.gov education counts | `How many high school seniors are listed for Rock Bridge Sr. High in 2026?` | Deterministic school/year lookup from the selected public education index. |
| data.mo.gov education ranking | `Which school had the most high school seniors in 2026?` | Deterministic ranking over numeric school/year rows. |
| data.mo.gov FAFSA suppression | `How many FAFSA applications did St Pius X High School report in 2024?` | Suppression-aware response when the public source row uses `*`. |
| Source discovery | `What Missouri Auditor reports are connected?` | Public source-index answer with official links. |
| Guardrail | `Can you list every person at the Department of Revenue` | Unsupported-scope refusal. |
| Privacy | `What is Kory Hubbard's mailing address?` | Private-identifier refusal. |

## Newly Added Public-Source Questions

- `What Missouri Auditor reports are connected?`
- `What DOR reports are connected?`
- `What were Boone County taxable sales in 2025?`
- `How many registered passenger vehicles are in Boone County?`
- `How many motor vehicle dealers are in Boone County?`
- `What is Boone County unemployment rate in March 2026?`
- `How many people were unemployed in Boone County in March 2026?`
- `Which county had the highest unemployment rate in March 2026?`
- `What are the top data.mo.gov catalog themes?`
- `Which data.mo.gov datasets mention hospital?`
- `Which data.mo.gov datasets mention contract?`
- `What education data is indexed?`
- `How many high school seniors are listed for Rock Bridge Sr. High in 2026?`
- `Which school had the most high school seniors in 2026?`
- `How many completed FAFSA applications did Rock Bridge Sr. High report in 2026?`
- `How many FAFSA applications did St Pius X High School report in 2024?`
- `What MEC reports are connected?`
- `What SOS election data is connected?`
- `What OA Budget data is connected?`
- `What child care reports are connected?`
- `What long-term care reports are connected?`
- `What PSC reports are connected?`
- `What cannabis reports are connected?`
- `What agriculture reports are connected?`

## Latest Result

`scripts/test_chatbot_behavior.py` passed 74 cases after adding the expanded source registry, aggregate employee-pay ranking, MSHP crash-statistics lookup, DOR aggregate report lookup, MERIC LAUS labor-market lookup, data.mo.gov catalog metadata lookup, and selected data.mo.gov education lookup.
