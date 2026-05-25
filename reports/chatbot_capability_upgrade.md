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
- Contract vendor search cleanup: contractor-name searches now prefer exact contractor matches before broad keyword fallback, so vendor questions do not drift into unrelated contracts that share generic words.
- data.mo.gov education lookup: answers high-school senior counts, completed FAFSA application counts, suppression-aware FAFSA rows, and top-school rankings by school year.
- DESE School Directory lookup: answers district county, county-district code, MSIP, enrollment, certified-staff counts, school/building counts, school codes, grade spans, and largest-district/staff rankings from the public School Directory by District PDF.
- DESE APR ranking lookup: answers selected 2025 public lowest-5% APR ranking questions for LEA and school-building ranks and single-year APR percent scores.
- DESE finance transfer lookup: answers selected 2025-2026 district transfer amount and top-district questions from the public 7%, 5%, and Transportation Transfer PDFs.
- data.mo.gov public-health lookup: answers aggregate communicable-disease YTD counts, rates per 100k, 5-year median comparisons, and rankings from the selected public report.
- DHSS BRFSS aggregate lookup: answers statewide adult prevalence percentage, confidence interval, summary, and ranking questions from the official BRFSS front-page workbook.
- DHSS vital-statistics aggregate lookup: answers statewide Table 1 births, deaths, natural increase, infant deaths, marriages, divorces, population, latest-year, source, county birth/death/natural-increase, and county ranking questions from the official FOCUS and annual Missouri Vital Statistics PDFs.
- DHSS MOPHIMS profile aggregate lookup: answers selected ProfileBuilder count/rate questions for child health, chronic disease comparisons, leading causes of death, emergency room visits, inpatient hospitalizations, and selected county leading-causes-of-death/inpatient values.
- data.mo.gov hospital profile lookup: answers statewide, region, and facility licensed-bed/ICU-bed questions plus largest-facility rankings from the public Profile of Hospitals source while suppressing address, phone, fax, and administrator-name fields in output.
- DHSS WIC aggregate lookup: answers county and municipality WIC household-row counts, redeemed net-benefit totals, average benefits, and top-county rankings from aggregate Socrata queries.
- data.mo.gov Food Pantry List lookup: answers county, city, agency, public phone, public address, listed hours, and top-county count questions from the selected public service-location table.
- data.mo.gov LTC lookup: answers sanitized long-term-care county, city, facility, capacity, level-of-care, and aggregate census occupancy questions.
- DHSS LTC inspection metadata lookup: answers official long-term-care inspection resource, county/city search-filter, scope/severity, facility-type, laws/regulations, records-request, and Nursing Home Compare guidance questions without parsing facility findings.
- data.mo.gov DNR water lookup: answers public drinking-water system counts by county, PWSID lookup, system-name lookup, and county rankings from the Consumer Confidence Report.
- data.mo.gov DNR hazardous-waste facility lookup: answers EPA ID lookup, facility-name lookup, county/status counts, county rankings, DNR region summaries, and source-link questions from the selected public facility table.
- DNR data/e-services resource metadata lookup: answers cited resource-link questions for water permits, MoCWIS, drinking-water tools, impaired waters, water quality, GIS/map viewers, air-emissions tools, E-Start, WIMS, GeoSTRAT, energy data, forms, and public notices.
- DNR impaired-waters lookup: answers selected county counts, pollutant summaries, waterbody matches, and high-priority TMDL questions from the proposed 2024-2026 Section 303(d) listed-waters PDF.
- MSDIS geospatial resource metadata lookup: answers cited resource-link questions for MSDIS Open Data datasets, ArcGIS REST services, county boundaries, imagery, LiDAR/elevation, archive directories, and vector GIS resources.
- data.mo.gov utility lookup: answers city/county electric, gas, water, and telephone provider questions from the Find A Missouri Utility table.
- data.mo.gov agriculture lookup: answers feed sample ID, feed class count/ranking, and selected nutrient guarantee/result questions from the Missouri Department of Agriculture feed sample testing table.
- data.mo.gov Missouri Farmers' Markets lookup: answers county counts, city lookups, public listing/business details, website/address fields, and top-county rankings while suppressing contact-name and email fields.
- Agricultural Market News selected report-PDF lookup: answers capped Missouri hay price range, hay demand/supply, Joplin feeder-cattle receipt, selected Joplin steer-row, special-note, and snippet questions with official USDA AMS PDF links.
- Missouri State Auditor metadata lookup: answers report number, release year, latest-report, title keyword, official report page, and PDF-link questions from the public report-search endpoint.
- Missouri State Auditor document text lookup: answers capped plain-English orientation questions from selected official Auditor PDFs, including report 2026-044, with direct PDF links.
- Missouri PSC report document text lookup: answers capped plain-English orientation and snippet-search questions from a selected official PSC report PDF, with direct official PDF links.
- SOS election returns lookup: answers selected statewide winner, candidate vote, percentage, contest total-vote, primary party-winner, selected 2024 county President/Governor result, and 2024 voter-turnout questions from official Secretary of State PDFs.
- OA General Revenue Detail lookup: answers selected FY 2026 monthly amount, percent-change, and fiscal year-to-date questions from official OA Excel workbooks.
- Word-year parsing: handles wording such as `fiscal year twenty twenty six`.
- Placeholder guardrail: skips placeholder public names such as `N/A`, `UNKNOWN`, and `NOT PROVIDED`.
- UI source notes and suggestion rendering.
- Citizen-facing answer panel cleanup: ordinary chat hides Source/Evidence, sourced answers label the source as a source/download link, and the evidence table uses citizen-readable data type and date/year labels instead of implementation details.
- Safer arithmetic routing: short math prompts such as `what is 2+2` and `what is 12 divided by 3?` answer directly, while public-data phrases with hyphens or years no longer get mistaken for arithmetic.
- Common routing diagnostics: every answer now exposes `retrieval_path`, `source_family`, `evidence_type`, `routing_confidence`, optional `guardrail_reason`, and top ranked `route_candidates` for reviewer-facing audits.
- Behavioral regression test script: `scripts/test_chatbot_behavior.py` with 317 expanded exact-lookup, general-chat, civic-fact, hyperlink, hospital-profile, contract payment-context, contract document text/snippet, DESE assessment, DESE staff, food pantry, farmers-market, DNR oil-and-gas permit, DNR hazardous-waste facility, SOS county/turnout, MSHP county crash, citizen-definition, DHSS county vital-statistics, and routing cases.
- Source usefulness probe: `scripts/test_source_usefulness.py` with 44 representative source-family questions that verify expected answer terms plus at least one public HTTP source/download link per sourced answer.

## Current Indexed Data

- MAP text files indexed: 104
- MAP parsed rows: 6,123,427
- Public amount lookup rows: 1,930,866
- Employee lookup rows: 1,148,524
- Agency-vendor lookup rows: 2,597,580
- OA General Revenue Detail rows: 210 aggregate line items from 10 official FY 2026 monthly Excel workbooks
- MERIC LAUS labor rows: 353 aggregate records from 25 official CSV downloads
- DOR aggregate report rows: 45,948 aggregate records from 29 official public report files, including 2016-2025 county Sales/Use taxable-sales ZIPs, FY22-FY25 Food Tax by Political Subdivision PDFs, 2024-2025 Working Family Tax Credit PDFs, and FY25-FY26 quarterly tax-credit report PDFs
- data.mo.gov catalog metadata: 277 dataset records, 272 with distributions, 255 CSV links, and 255 JSON links
- data.mo.gov education rows: 14,123 school/year rows across two selected public education datasets
- DESE School Directory rows: 489 district rows and 2,433 school/building rows from a 3.4 MB public PDF snapshot, including district certified-staff counts
- DESE APR ranking rows: 28 LEA rows and 101 school-building rows from two official public PDF reports
- DESE finance transfer rows: 1,554 district report rows from three official public PDF reports
- data.mo.gov health rows: 52 aggregate disease/condition rows from one selected public-health dataset
- DHSS BRFSS aggregate rows: 35 statewide prevalence indicators from the official front-page workbook, covering 2018-2021
- DHSS vital-statistics aggregate rows: 21 statewide Table 1 rows from the 2023 Vital Statistics FOCUS PDF, covering 2013, 2022, and 2023, plus 116 county/state Table 16A rows from the 2023 annual Missouri Vital Statistics PDF
- DHSS MOPHIMS profile rows: 192 statewide aggregate rows across 5 selected official ProfileBuilder pages, plus 438 selected county leading-causes-of-death and inpatient-hospitalization rows
- data.mo.gov hospital profile rows: 166 public facility profile rows, 21,202 licensed beds, and 2,032 ICU licensed beds
- DHSS WIC aggregate rows: 86,044 public source household rows summarized into 115 county and 224 municipality aggregate rows
- data.mo.gov Food Pantry List rows: 238 public service-location rows across 115 counties and 182 cities
- data.mo.gov Missouri Farmers' Markets rows: 280 public directory listing rows across 90 counties and 195 cities
- data.mo.gov LTC rows: 1,101 sanitized directory rows, 986 unique facility numbers, 114 counties, and 47 aggregate census rows
- DHSS LTC inspection metadata rows: 434 metadata rows from 2 official pages, including 24 resource links, 115 county filters, and 295 city filters
- data.mo.gov DNR water rows: 1,425 public drinking-water system rows across 115 counties
- data.mo.gov DNR hazardous-waste facility rows: 86 public facility rows across 29 counties and 5 DNR regions
- DNR data/e-services resource metadata rows: 281 public resource links across 9 official source pages
- DNR impaired-waters rows: 549 selected listing rows from the official proposed 2024-2026 Section 303(d) PDF
- MSDIS geospatial resource metadata rows: 509 public resource links across 14 pages, feeds, and service endpoints
- data.mo.gov utility rows: 1,718 city/county utility-provider rows across 115 counties
- data.mo.gov agriculture rows: 8,388 feed sample testing rows across 48 feed classes
- Agricultural Market News selected document PDFs: 3 official USDA AMS PDFs, 12 Missouri hay price rows, and 18 selected Joplin steer rows
- Missouri State Auditor metadata rows: 3,447 report records from 1999-2026
- Missouri State Auditor document text rows: 7 selected official PDFs, 4.64 MB downloaded locally in the capped sample run
- Missouri PSC report document text rows: 1 selected official PDF, 43.56 MB downloaded locally in the capped sample run
- SOS election-return rows: 5 official SOS PDFs, 782 statewide contests, 1,604 statewide candidate/ballot rows, 1,404 selected 2024 county candidate rows, and 117 voter-turnout rows

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
- `Find contract CC221256001 and show its document links.`
- `Explain contract CC221256001 in simple terms.`
- `What contracts mention Elliott Auto Supply?`
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
- `What BRFSS data is indexed?`
- `What percent of Missouri adults had obesity in BRFSS?`
- `Which BRFSS indicator has the highest prevalence?`
- `What DHSS vital statistics data is indexed?`
- `What is the latest statewide total for live births in Missouri?`
- `How many deaths were reported in Missouri in 2023?`
- `What are the indexed Missouri statewide births and deaths totals for the latest year?`
- `How many births and deaths were in Boone County in 2023?`
- `Which county had the most resident deaths in 2023?`
- `What is the source for the DHSS births/deaths aggregate index?`
- `How many WIC household rows are listed for Boone County?`
- `Which county had the highest WIC benefit total?`
- `How many food pantries are listed in Boone County?`
- `What are the hours for Central Pantry?`
- `What LTC data is indexed?`
- `How many LTC directory rows are listed for Boone County?`
- `What is the statewide LTC census occupancy ratio?`
- `What DHSS LTC inspection resources are indexed?`
- `Where can I look up LTC inspections for Boone County?`
- `Does Show Me Long Term Care include a city filter for Columbia?`
- `What facility types does Show Me Long Term Care mention?`
- `Where are LTC scope and severity resources?`
- `What Auditor report data is indexed?`
- `How many Missouri Auditor reports were released in 2026?`
- `Give me the link for Auditor report 2026-044`
- `Explain Auditor report 2026-044 in simple terms.`
- `What SOS election data is indexed?`
- `Who won the 2024 Missouri governor election?`
- `How many votes did Donald Trump receive in the 2024 Missouri general election?`
- `Who won the Republican primary for Missouri governor in 2024?`
- `What DNR water data is indexed?`
- `How many public water systems are listed in Boone County?`
- `What is the PWSID for City of Columbia Utilities?`
- `Which county has the most public water systems in the Consumer Confidence Report?`
- `What DNR hazardous waste facility data is indexed?`
- `How many DNR hazardous waste facilities are in Boone County?`
- `What is listed for EPA ID MOD054950670?`
- `What DNR resources are indexed?`
- `Give me DNR water permit links`
- `Where is Missouri impaired waters data?`
- `What DNR impaired waters data is parsed?`
- `How many impaired water listings are in Boone County?`
- `Which high-priority TMDL impaired waters are listed?`
- `What DNR GIS resources are indexed?`
- `What MSDIS geospatial resources are indexed?`
- `Give me MSDIS county boundary links`
- `Give me MSDIS imagery services`
- `Give me MSDIS LiDAR links`
- `What utility data is indexed?`
- `What utilities serve Columbia in Boone County?`
- `How many utility rows are listed for Boone County?`
- `Which electric utility appears most often?`
- `What PSC report document text is indexed?`
- `Explain PSC report volume 33 in simple terms.`
- `Find electric mentions in PSC report volume 33.`
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
.\.venv\Scripts\python scripts\test_source_usefulness.py
.\.venv\Scripts\python scripts\verify_project.py
py -3 scripts\test_chatbot_behavior.py
```

Live API/UI smoke checks after restart:

- `/api/ask` returned request id, snapshot id `3dc8547c3dc05303`, retrieval path `deterministic_lookup`, and source-row counts for tax credit, agency-vendor expenditure, and employee-pay checks.
- Browser UI rendered an Evidence section and source-row preview for `Tax credit`, using `TC_2026.txt`, and rendered no raw row preview for `Employee pay`.

## Remaining Gaps

- The matching layer now emits ranked source-family diagnostics, but more handlers still need to move behind shared search/ranking instead of local predicate checks.
- Citations are source-file and lookup-table level; row-level drilldown is still future work.
- The UI is local-only and single-user.
- The two cumulative self-extracting files are retained as raw artifacts but are not executed or extracted.
