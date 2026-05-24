# Data Card

## Dataset Name

Missouri Tiny LLM Public QA

## Intended Use

Educational case study for testing whether a tiny local language model can answer simple questions over Missouri public-data aggregates, with deterministic lookup for indexed row-level public MAP records.

## Sources

- Missouri Accountability Portal data download page: https://mapyourtaxes.mo.gov/MAP/Download/
- MAP public download categories: expenditures, employees, tax credits, federal grants, budget restrictions, bonds, stimulus, and check cancellations
- data.mo.gov Profile of Hospitals: https://data.mo.gov/resource/q8me-hzr8.json
- data.mo.gov LTC Census Report: https://data.mo.gov/resource/bf8b-a47t.json
- data.mo.gov LTC Directory: https://data.mo.gov/d/fenu-sipv
- MissouriBUYS Contract Board: https://missouribuys.mo.gov/contractboard
- Office of Administration Contract Search: https://archive.oa.mo.gov/purch/contracts/
- State of Missouri data.mo.gov catalog: https://data.mo.gov/data.json
- data.mo.gov Total Number of High School Seniors in Missouri: https://data.mo.gov/d/8yaf-xv66
- data.mo.gov Completed FAFSAs Reported to MDHE: https://data.mo.gov/d/t9f4-ncza
- DESE School Directory: https://dese.mo.gov/data-system-management/directory
- DESE School Directory Data Downloads: https://dese.mo.gov/school-directory/data-downloads
- data.mo.gov Missouri Communicable Disease Report (2026): https://data.mo.gov/d/fk75-fa28
- DHSS WIC Data: https://data.mo.gov/d/diyi-fr2a
- data.mo.gov Consumer Confidence Report: https://data.mo.gov/d/3mwf-kse4
- data.mo.gov Find A Missouri Utility: https://data.mo.gov/d/yeiz-h2m2
- data.mo.gov Missouri Department of Agriculture feed sample testing results: https://data.mo.gov/d/y9w9-qkg2
- DESE School Data source registry: https://dese.mo.gov/school-data
- DHSS data source registry: https://health.mo.gov/data/
- MSHP SAC traffic-safety source registry: https://www.mshp.dps.mo.gov/MSHPWeb/SAC/data_960grid.html
- MERIC unemployment and labor data source registry: https://meric.mo.gov/data/unemployment
- MERIC Local Area Unemployment Statistics CSV route: https://meric.mo.gov/data/economic/local-area-unemployment-statistics/laus
- Missouri DNR data and e-services source registry: https://dnr.mo.gov/data-e-services
- MSDIS geospatial source registry: https://www.msdis.missouri.edu/
- MoDOT traffic and transportation source registry: https://www.modot.org/modatazone/traffic
- Missouri State Auditor report registry: https://auditor.mo.gov/AuditReport/Menu
- Missouri State Auditor report search endpoint: https://auditor.mo.gov/AuditReport/SearchAudits
- Missouri Department of Revenue public report registry: https://dor.mo.gov/public-reports/
- Missouri Ethics Commission public records registry: https://mec.mo.gov/
- Missouri Secretary of State elections registry: https://www.sos.mo.gov/elections/s_default
- Missouri Secretary of State official election returns: https://www.sos.mo.gov/elections/s_default/results
- Office of Administration Budget and Planning registry: https://oa.mo.gov/budget-and-planning
- DESE child care compliance dashboard registry: https://dese.mo.gov/childhood/child-care/child-care-data-dashboards
- DHSS long-term care inspection registry: https://health.mo.gov/safety/nursinghomesinspected/index.php
- Missouri Public Service Commission report registry: https://psc.mo.gov/General/PSC_Reports
- DHSS Division of Cannabis Regulation registry: https://health.mo.gov/safety/cannabis/
- Missouri Agricultural Market News report registry: https://agmarketnews.mo.gov/reports/

## Generated Artifacts

- Training QA rows: 100
- Evaluation QA rows: 20
- Expanded MAP run 002 training QA rows: 304
- Expanded MAP run 002 evaluation QA rows: 40
- Processed summary: `data/processed/public_data_summary.json`
- Evaluation prompts: `data/eval/evaluation_prompts.jsonl`
- Local MAP lookup index: `data/raw_public/map_public_lookup.sqlite` (ignored by Git)
- Local contract metadata index: `data/raw_public/contracts/missouri_contracts_index.json` (ignored by Git)
- Local contract document text index: `data/raw_public/contracts/missouri_contract_documents_index.json` (ignored by Git)
- Expansion preflight report: `reports/data_expansion_preflight.json`
- Public source index report: `reports/public_source_index_report.json`
- Local public source index: `data/raw_public/expanded_sources/missouri_public_source_index.json` (ignored by Git)
- data.mo.gov catalog index report: `reports/data_mo_catalog_index_report.json`
- Local data.mo.gov catalog metadata index: `data/raw_public/data_mo_catalog/data_mo_catalog_index.json` (ignored by Git)
- data.mo.gov education index report: `reports/data_mo_education_index_report.json`
- Local selected education index: `data/raw_public/data_mo_education/data_mo_education_index.json` (ignored by Git)
- DESE School Directory index report: `reports/dese_directory_index_report.json`
- Local selected DESE School Directory index: `data/raw_public/dese_directory/dese_directory_index.json` (ignored by Git)
- data.mo.gov health index report: `reports/data_mo_health_index_report.json`
- Local selected public-health index: `data/raw_public/data_mo_health/data_mo_health_index.json` (ignored by Git)
- DHSS WIC aggregate index report: `reports/data_mo_wic_index_report.json`
- Local selected DHSS WIC aggregate index: `data/raw_public/data_mo_wic/data_mo_wic_index.json` (ignored by Git)
- data.mo.gov LTC index report: `reports/data_mo_ltc_index_report.json`
- Local selected LTC directory/census index: `data/raw_public/data_mo_ltc/data_mo_ltc_index.json` (ignored by Git)
- data.mo.gov DNR water index report: `reports/data_mo_water_index_report.json`
- Local selected DNR water index: `data/raw_public/data_mo_water/data_mo_water_index.json` (ignored by Git)
- data.mo.gov utility index report: `reports/data_mo_utility_index_report.json`
- Local selected utility index: `data/raw_public/data_mo_utility/data_mo_utility_index.json` (ignored by Git)
- data.mo.gov agriculture index report: `reports/data_mo_agriculture_index_report.json`
- Local selected agriculture index: `data/raw_public/data_mo_agriculture/data_mo_agriculture_index.json` (ignored by Git)
- DHSS cannabis index report: `reports/cannabis_index_report.json`
- Local selected cannabis index: `data/raw_public/cannabis/cannabis_index.json` plus selected annual-report PDFs (ignored by Git)
- MSHP crash index report: `reports/mshp_crash_index_report.json`
- Local MSHP crash-statistics index: `data/raw_public/mshp_crash/mshp_crash_index.json` (ignored by Git)
- DOR aggregate report index report: `reports/dor_reports_index_report.json`
- Local DOR aggregate report index: `data/raw_public/dor_reports/dor_reports_index.json` (ignored by Git)
- MERIC LAUS labor index report: `reports/meric_labor_index_report.json`
- Local MERIC LAUS labor index: `data/raw_public/meric_labor/meric_labor_index.json` (ignored by Git)
- Missouri State Auditor metadata index report: `reports/state_auditor_index_report.json`
- Local Missouri State Auditor metadata index: `data/raw_public/state_auditor/state_auditor_index.json` (ignored by Git)
- SOS election returns index report: `reports/sos_elections_index_report.json`
- Local SOS election returns index: `data/raw_public/sos_elections/sos_elections_index.json` (ignored by Git)
- Contract document index report: `reports/contract_document_index_report.json`

## Source Volumes

- MAP expenditure rows processed: 94,731
- MAP total aggregate payments: $35,836,030,005.81
- MAP all-files download inventory: 107 listed items
- MAP local lookup index: 104 text files, 6,123,427 parsed rows
- MAP raw public download footprint: about 589 MB
- MAP SQLite lookup footprint: about 1.15 GB, ignored by Git
- Contract metadata preflight: 991 public contract rows found; first 200 detail pages indexed locally
- Contract document text extraction sample: 12 public PDF documents, 4.29 MB downloaded locally, ignored by Git
- data.mo.gov catalog metadata index: 277 datasets found, 272 with distributions, 255 CSV distribution links, 255 JSON distribution links, 395 KB source snapshot
- data.mo.gov education index: 2 public education datasets, 14,123 parsed rows, 1,154 unique normalized school names, about 2.8 MB of downloaded source JSON
- DESE School Directory index: 489 district rows, 2,433 school/building rows, 1,095 PDF pages, 3.4 MB public PDF snapshot, and about 4.6 MB local PDF/index footprint
- data.mo.gov health index: 1 aggregate public-health dataset, 52 disease/condition rows, about 17 KB downloaded source JSON
- DHSS WIC aggregate index: 86,044 public source household rows summarized into 115 county rows and 224 municipality rows, about 60 KB local aggregate-query footprint
- data.mo.gov LTC index: 1,101 sanitized directory rows, 986 unique facility numbers, 114 counties, 47 aggregate census rows, and about 0.6 MB selected-source footprint
- data.mo.gov DNR water index: 1 public drinking-water dataset, 1,425 system rows, 115 counties, about 100 KB downloaded source JSON
- data.mo.gov utility index: 1 public utility-provider dataset, 1,718 city/county rows, 115 counties, about 322 KB downloaded source JSON
- data.mo.gov agriculture index: 1 public feed sample testing dataset, 8,388 rows, 48 feed classes, about 18 MB local raw/index footprint
- DHSS cannabis index: 223 verified dispensary records, 57 counties, 113 cities, 6 annual report links, 3 selected annual-report PDFs parsed for PY22-PY24 metrics, about 24.7 MB local source/index footprint
- Public source-page index: 18 source families checked, 18 connected
- MSHP traffic-safety aggregate crash files preflight: about 0.32 MB across the key crash Excel files
- MSHP crash aggregate index: 9 official Excel files, 540 metric-year records
- DOR aggregate public reports: 7 official report files, about 5.8 MB downloaded, 38,451 parsed aggregate records
- DOR local parsed JSON index: about 20 MB, ignored by Git
- MERIC LAUS labor index: 25 official CSV downloads, about 0.31 MB local footprint, 353 aggregate rows, 116 areas, and 115 county areas
- Missouri State Auditor metadata index: 3,447 report metadata rows, years 1999-2026, about 2 MB selected-source footprint
- SOS election returns index: 3 official statewide election-return PDFs, about 3.6 MB downloaded, 782 contests, and 1,604 candidate/ballot result rows
- Hospital profile rows processed: 166
- LTC census rows processed: 47

## Sanitization

Raw MAP downloads may contain vendor names and other row-level public records. The public QA files do not emit vendor names, employee salaries, person-level salary records, addresses, phone numbers, fax numbers, or hospital administrator names.

The local UI may answer exact public-record questions when the entity appears in the local MAP lookup index. Those answers come from deterministic lookup over local public source files, not from model memorization.

Contract lookup stores contract metadata and URLs. Contract document extraction is optional, capped, local-only, and ignored by Git. MAP payment context is computed separately from indexed MAP expenditure files when a contractor name can be matched.

DOR dealer source files are parsed into aggregate county/type counts. Individual dealer names, addresses, owner names, and phone numbers from that source are not returned by the chatbot.

The selected LTC Directory query requests and stores only facility, capacity, county, city, license-date, certification, and level-of-care fields. It does not store or return administrator names, phone numbers, mailing addresses, or street addresses.

The Missouri State Auditor metadata index stores report numbers, titles, release dates, official report page links, PDF links, citizen-summary links when listed, and inferred title topics. It does not download PDFs, extract findings, or make legal/accountability conclusions beyond metadata lookup.

The SOS election returns index stores selected statewide official return rows from public PDFs. It does not store voter files, voter-level data, precinct files, or county result tables.

The selected cannabis index stores sanitized non-contact verified dispensary fields: dispensary name, license number, city, county, ZIP, update label, and source object id. It does not store or return phone numbers, street addresses, websites, or coordinates from the public locator. Annual-report PDF extraction stores selected aggregate metrics only.

## Current Scope

- Employee pay lookup is allowed for indexed public MAP employee files.
- Named-vendor expenditure lookup is allowed for indexed public MAP expenditure files.
- Contract number and contractor lookup is allowed for indexed public MissouriBUYS/OA contract metadata.
- Plain-English contract explanation is allowed when backed by contract metadata, source document links, optional local PDF text extraction, and citations.
- MSHP crash-statistic lookup is allowed for indexed aggregate SAC Excel files such as persons killed/injured, fatal crashes, death/injury rates, alcohol/speed involvement, motorcycle, commercial vehicle, young-driver, older-driver, and factor rankings.
- DOR aggregate lookup is allowed for indexed county taxable sales, business-location counts, vehicle counts, licensed-driver totals, dealer counts by county/type, and SIC location counts. Dealer outputs are aggregate only.
- MERIC LAUS lookup is allowed for indexed Missouri and county unemployment rate, labor force, employment, and unemployed-count questions. Missouri statewide rows use the seasonally adjusted series by default; county rows use the not-seasonally-adjusted public county series.
- data.mo.gov catalog lookup is allowed for dataset counts, theme counts, title/description/keyword searches, landing pages, and CSV/JSON/PDF distribution links. It is metadata search, not row-level parsing of every catalog dataset.
- Selected data.mo.gov education lookup is allowed for high-school senior counts, completed FAFSA application counts, and top-school rankings by school year. Suppressed FAFSA values such as `*` are returned as suppressed/not numeric rather than converted into counts.
- Selected DESE School Directory lookup is allowed for public district/school directory facts: district county, county-district code, MSIP status, certified staff count, prior-year enrollment, school/building count, school code, and grade span. The index does not return superintendent, principal, board member, phone, fax, email, address, or other contact/person fields from the directory PDF.
- Selected data.mo.gov public-health lookup is allowed for aggregate communicable-disease report values: current-week YTD counts, previous-week YTD counts, rates per 100k, 5-year median comparisons, and rankings. It is aggregate surveillance reporting, not medical advice.
- Selected DHSS WIC lookup is allowed only for county and municipality aggregate facts: source household-row counts, redeemed net-benefit totals, average benefits, 2022 municipality population where present, and top-county rankings. The index is built from aggregate Socrata queries and does not store or return household identifiers, applicant cities, ZIP codes, agency IDs, or raw household rows.
- Selected data.mo.gov LTC lookup is allowed for sanitized directory facts and aggregate census facts: county/city/facility capacity, level of care, license effective/expiration dates, certification when present, top-county capacity ranking, licensed homes, licensed beds, census, and occupancy. It is not a medical, quality, complaint, inspection, or facility-ranking system.
- Selected data.mo.gov DNR water lookup is allowed for public drinking-water system counts by county, PWSID lookup, system-name lookup, and county rankings. It is a selected Consumer Confidence Report listing, not full DNR water quality, permit, impaired-water, or GIS coverage.
- Selected data.mo.gov utility lookup is allowed for city/county electric, gas, water, and telephone provider lookup and provider rankings. It is a selected provider table, not full PSC filings, rate cases, annual reports, or legal/regulatory orders.
- Selected data.mo.gov agriculture lookup is allowed for public feed sample ID lookup, feed class counts/rankings, and selected nutrient guarantee/result values. It is a selected feed sample testing table, not full agriculture market reports, seed data, inspections, complaints, or enforcement coverage.
- Selected DHSS cannabis lookup is allowed for verified dispensary counts, county/city rankings, license/name lookup, and selected PY22-PY24 annual-report sales, tax, transfer, microbusiness, agent-card, and operating-facility metrics. It is not a legal-advice system and does not yet parse live Tableau dashboards, transfer history, inspections, item approvals, or product/regulatory updates.
- Missouri State Auditor lookup is allowed for public report metadata: report number, title, release date, official report page, PDF link, citizen-summary link when listed, recent reports, year counts, and title keyword searches. It is not an audit-finding summarizer unless a future capped document parser is added.
- Selected SOS election lookup is allowed for official statewide return facts from indexed PDFs: winners, candidate votes, percentages, contest total votes, and primary party winners. It is not a voter-file, precinct-level, county-results, turnout, ballot-measure, or candidate-filing parser yet.
- Source-discovery answers are supported for the connected public source registry: DESE, DHSS, MSHP, MERIC, DNR, MSDIS, MoDOT, Auditor, DOR, MEC, SOS elections, OA Budget, child care, long-term care, PSC, cannabis, agriculture, and data.mo.gov.
- Capped raw-row previews are allowed for non-person exact-record answers; employee raw-row previews are suppressed in the UI/API.

## Exclusions

- Internal State of Missouri notes or non-public work material
- Raw MAP downloads in the public Git repo
- Local SQLite lookup index in the public Git repo
- Local model caches and LoRA checkpoints in the public Git repo
- Any claim of State of Missouri endorsement

## Limitations

The QA set is small and aggregate-focused. The row-level MAP lookup is limited to the public source files present under `data/raw_public/`. It is suitable for a constrained learning case study, not a production public-finance assistant.
