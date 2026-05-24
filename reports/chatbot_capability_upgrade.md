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
- MERIC LAUS lookup: answers Missouri and county unemployment rate, labor force, employment, unemployed-count, and county-ranking questions from structured public CSV downloads.
- data.mo.gov catalog lookup: answers catalog counts, top themes, dataset searches, landing pages, and CSV/JSON/PDF distribution-link questions from the public DCAT metadata snapshot.
- data.mo.gov education lookup: answers high-school senior counts, completed FAFSA application counts, suppression-aware FAFSA rows, and top-school rankings by school year.
- DESE School Directory lookup: answers district county, county-district code, MSIP, enrollment, school/building counts, school codes, grade spans, and largest-district rankings from the public School Directory by District PDF.
- data.mo.gov public-health lookup: answers aggregate communicable-disease YTD counts, rates per 100k, 5-year median comparisons, and rankings from the selected public report.
- DHSS WIC aggregate lookup: answers county and municipality WIC household-row counts, redeemed net-benefit totals, average benefits, and top-county rankings from aggregate Socrata queries.
- data.mo.gov LTC lookup: answers sanitized long-term-care county, city, facility, capacity, level-of-care, and aggregate census occupancy questions.
- data.mo.gov DNR water lookup: answers public drinking-water system counts by county, PWSID lookup, system-name lookup, and county rankings from the Consumer Confidence Report.
- DNR data/e-services resource metadata lookup: answers cited resource-link questions for water permits, MoCWIS, drinking-water tools, impaired waters, water quality, GIS/map viewers, air-emissions tools, E-Start, WIMS, GeoSTRAT, energy data, forms, and public notices.
- data.mo.gov utility lookup: answers city/county electric, gas, water, and telephone provider questions from the Find A Missouri Utility table.
- data.mo.gov agriculture lookup: answers feed sample ID, feed class count/ranking, and selected nutrient guarantee/result questions from the Missouri Department of Agriculture feed sample testing table.
- Missouri State Auditor metadata lookup: answers report number, release year, latest-report, title keyword, official report page, and PDF-link questions from the public report-search endpoint.
- SOS election returns lookup: answers selected statewide winner, candidate vote, percentage, contest total-vote, and primary party-winner questions from official Secretary of State election-return PDFs.
- Word-year parsing: handles wording such as `fiscal year twenty twenty six`.
- Placeholder guardrail: skips placeholder public names such as `N/A`, `UNKNOWN`, and `NOT PROVIDED`.
- UI source notes and suggestion rendering.
- Behavioral regression test script: `scripts/test_chatbot_behavior.py` with 166 expanded exact-lookup and routing cases.

## Current Indexed Data

- MAP text files indexed: 104
- MAP parsed rows: 6,123,427
- Public amount lookup rows: 1,930,866
- Employee lookup rows: 1,148,524
- Agency-vendor lookup rows: 2,597,580
- MERIC LAUS labor rows: 353 aggregate records from 25 official CSV downloads
- data.mo.gov catalog metadata: 277 dataset records, 272 with distributions, 255 CSV links, and 255 JSON links
- data.mo.gov education rows: 14,123 school/year rows across two selected public education datasets
- DESE School Directory rows: 489 district rows and 2,433 school/building rows from a 3.4 MB public PDF snapshot
- data.mo.gov health rows: 52 aggregate disease/condition rows from one selected public-health dataset
- DHSS WIC aggregate rows: 86,044 public source household rows summarized into 115 county and 224 municipality aggregate rows
- data.mo.gov LTC rows: 1,101 sanitized directory rows, 986 unique facility numbers, 114 counties, and 47 aggregate census rows
- data.mo.gov DNR water rows: 1,425 public drinking-water system rows across 115 counties
- DNR data/e-services resource metadata rows: 281 public resource links across 9 official source pages
- data.mo.gov utility rows: 1,718 city/county utility-provider rows across 115 counties
- data.mo.gov agriculture rows: 8,388 feed sample testing rows across 48 feed classes
- Missouri State Auditor metadata rows: 3,447 report records from 1999-2026
- SOS election-return rows: 3 official PDFs, 782 contests, and 1,604 candidate/ballot result rows

## Verified Hard Cases

- `Where does Kory Hubbard work?`
- `Where does Kory Hubbard live?`
- `What is Kory Hubbard's mailing address?`
- `How much did OFFICE OF ADMINISTRATION pay CAPITAL MALL JC 1 LLC in 2025?`
- `What are the top 5 vendors for TRANSPORTATION in 2025?`
- `What tax credit amount was issued to CARTWRIGHT HOLDINGS in fiscal year twenty twenty six?`
- `What is the unemployment rate in Missouri?`
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
- `What DESE school directory data is indexed?`
- `What county is Columbia 93 in?`
- `What grade span is Rock Bridge Sr. High?`
- `What public health data is indexed?`
- `How many anaplasmosis cases are listed YTD in the Missouri communicable disease report?`
- `What is the rate per 100k for salmonellosis?`
- `Which disease has the highest current week YTD count?`
- `What DHSS WIC data is indexed?`
- `How many WIC household rows are listed for Boone County?`
- `Which county had the highest WIC benefit total?`
- `What LTC data is indexed?`
- `How many LTC directory rows are listed for Boone County?`
- `What is the statewide LTC census occupancy ratio?`
- `What Auditor report data is indexed?`
- `How many Missouri Auditor reports were released in 2026?`
- `Give me the link for Auditor report 2026-044`
- `What SOS election data is indexed?`
- `Who won the 2024 Missouri governor election?`
- `How many votes did Donald Trump receive in the 2024 Missouri general election?`
- `Who won the Republican primary for Missouri governor in 2024?`
- `What DNR water data is indexed?`
- `How many public water systems are listed in Boone County?`
- `What is the PWSID for City of Columbia Utilities?`
- `Which county has the most public water systems in the Consumer Confidence Report?`
- `What DNR resources are indexed?`
- `Give me DNR water permit links`
- `Where is Missouri impaired waters data?`
- `What DNR GIS resources are indexed?`
- `What utility data is indexed?`
- `What utilities serve Columbia in Boone County?`
- `How many utility rows are listed for Boone County?`
- `Which electric utility appears most often?`
- `What agriculture feed testing data is indexed?`
- `Which feed class appears most often in the agriculture feed testing data?`
- `What are the protein values for sample D202500550?`
- `How many Poultry Feed samples are indexed?`
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
