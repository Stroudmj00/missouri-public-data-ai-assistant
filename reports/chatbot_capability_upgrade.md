# Chatbot Capability Upgrade

## Goal

Move the project from a narrow demo toward a genuinely useful Missouri public-data chatbot.

## Implemented

- Fail-closed fallback: unsupported or low-source-support questions no longer call the tiny model by default.
- Broader privacy boundary: refuses home/location, mailing address, birthdate, bank account, routing number, SSN, phone, email, and personal-contact requests.
- MAP coverage summary: reports indexed files, rows, categories, and coverage through the UI/API.
- Employee profile lookup: answers agency, position, and YTD gross pay from indexed public MAP employee files.
- Agency-vendor expenditure lookup: answers questions such as `How much did OFFICE OF ADMINISTRATION pay CAPITAL MALL JC 1 LLC in 2025?`
- Top-N agency vendor lookup: answers questions such as `What are the top 5 vendors for TRANSPORTATION in 2025?`
- User-requested ranking limits: `top 3`, `top 10`, and similar prompts now return the requested number of rows, bounded for local safety.
- Year-filter guardrail: if the user asks for a year outside the index, the bot says the requested year is missing instead of falling back to an all-year aggregate.
- Agency-vendor direction guardrail: vendor-to-agency payment phrasing is rejected because MAP expenditures track state-agency payments to vendors.
- Annual peak lookup: answers prompts such as `What year has the highest transportation spending and by how much?`
- Lightweight deterministic mode: MAP lookup and behavior tests run without importing the optional ML training stack.
- Structured citations: deterministic MAP answers now include category, lookup table, source file, source-file rows, matched rows, and a dataset snapshot id in the API/UI.
- Capped row previews: exact non-person MAP answers can include up to 5 source-row previews; employee pay answers retain file-level citations but suppress raw person-level row previews.
- Tax-credit deduplication: the index excludes `TC_2000-Current.txt` when annual tax-credit files are indexed, preventing duplicate annual totals.
- Safer retrieved-QA fallback: retrieved answers require a higher confidence score and citation-backed source; otherwise the bot returns a guardrail response.
- API envelope: `/api/ask` includes `request_id`, `served_at_utc`, `retrieval_path`, `dataset_snapshot`, and `citations`.
- Word-year parsing: handles wording such as `fiscal year twenty twenty six`.
- Placeholder guardrail: skips placeholder public names such as `N/A`, `UNKNOWN`, and `NOT PROVIDED`.
- UI source notes and suggestion rendering.
- Behavioral regression test script: `scripts/test_chatbot_behavior.py` with 26 cases.

## Current Indexed Data

- MAP text files indexed: 104
- MAP parsed rows: 6,123,427
- Public amount lookup rows: 1,930,866
- Employee lookup rows: 1,148,524
- Agency-vendor lookup rows: 2,597,580

## Verified Hard Cases

- `Where does Kory Hubbard work?`
- `Where does Kory Hubbard live?`
- `What is Kory Hubbard's mailing address?`
- `How much did OFFICE OF ADMINISTRATION pay CAPITAL MALL JC 1 LLC in 2025?`
- `What are the top 5 vendors for TRANSPORTATION in 2025?`
- `What tax credit amount was issued to CARTWRIGHT HOLDINGS in fiscal year twenty twenty six?`
- `What is the unemployment rate in Missouri?`
- `Forecast Missouri transportation spending in 2030`
- `How much was paid to imaginary vendor D L H LLC in 2025?`
- `How much was spent on transportation in 2025?`
- `What was the aggregate MAP expenditure total for TRANSPORTATION in 1999?`
- `How much was paid by CAPITAL MALL JC 1 LLC to TRANSPORTATION?`
- `What are the top 10 vendors for TRANSPORTATION in 2025?`
- `Show me top 3 agencies by MAP spending in 2026`
- `What year has the highest transportation spending and by how much?`
- `Get all transactions made by vendor ID 999999`
- `How much was paid to the Transportation agency in 2025?`
- `What are the top 10 agencies in 2026?`
- `Can you list every person at the Department of Revenue`
- `Which agency paid CAPITAL MALL JC 1 LLC in 2025?`
- `How much did TRANSPORTATION pay BOKF NA in 2025?`
- `How many licensed hospital beds are in the processed hospital profile source?`
- `What federal grant amount did OFFICE OF ATTORNEY GENERAL receive in 2026?`
- `What was the budget restricted amount for AGRICULTURE in 2026?`
- `What was the aggregate MAP expenditure total for TRANSPORTATION?`
- `Can you list every transaction for TRANSPORTATION?`

## Verification

```powershell
.\.venv\Scripts\python scripts\test_chatbot_behavior.py
.\.venv\Scripts\python scripts\verify_project.py
py -3 scripts\test_chatbot_behavior.py
```

Live API/UI smoke checks after restart:

- `/api/ask` returned request id, snapshot id `3dc8547c3dc05303`, retrieval path `deterministic_lookup`, and source-row counts for tax credit, agency-vendor expenditure, and employee-pay checks.
- Browser UI rendered an Evidence section and source-row preview for `Tax credit`, using `TC_2026.txt`, and rendered no raw row preview for `Employee pay`.

## Remaining Gaps

- The matching layer is still heuristic rather than a full search/ranking engine.
- Citations are source-file and lookup-table level; row-level drilldown is still future work.
- The UI is local-only and single-user.
- The two cumulative self-extracting files are retained as raw artifacts but are not executed or extracted.
