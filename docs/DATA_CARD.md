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
- MissouriBUYS Contract Board: https://missouribuys.mo.gov/contractboard
- Office of Administration Contract Search: https://archive.oa.mo.gov/purch/contracts/
- State of Missouri data.mo.gov catalog: https://data.mo.gov/data.json
- DESE School Data source registry: https://dese.mo.gov/school-data
- DHSS data source registry: https://health.mo.gov/data/
- MSHP SAC traffic-safety source registry: https://www.mshp.dps.mo.gov/MSHPWeb/SAC/data_960grid.html
- MERIC unemployment and labor data source registry: https://meric.mo.gov/data/unemployment
- MERIC Local Area Unemployment Statistics CSV route: https://meric.mo.gov/data/economic/local-area-unemployment-statistics/laus
- Missouri DNR data and e-services source registry: https://dnr.mo.gov/data-e-services
- MSDIS geospatial source registry: https://www.msdis.missouri.edu/
- MoDOT traffic and transportation source registry: https://www.modot.org/modatazone/traffic
- Missouri State Auditor report registry: https://auditor.mo.gov/AuditReport/Menu
- Missouri Department of Revenue public report registry: https://dor.mo.gov/public-reports/
- Missouri Ethics Commission public records registry: https://mec.mo.gov/
- Missouri Secretary of State elections registry: https://www.sos.mo.gov/elections/s_default
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
- MSHP crash index report: `reports/mshp_crash_index_report.json`
- Local MSHP crash-statistics index: `data/raw_public/mshp_crash/mshp_crash_index.json` (ignored by Git)
- DOR aggregate report index report: `reports/dor_reports_index_report.json`
- Local DOR aggregate report index: `data/raw_public/dor_reports/dor_reports_index.json` (ignored by Git)
- MERIC LAUS labor index report: `reports/meric_labor_index_report.json`
- Local MERIC LAUS labor index: `data/raw_public/meric_labor/meric_labor_index.json` (ignored by Git)
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
- data.mo.gov catalog preflight: 277 datasets found, 272 with distributions
- Public source-page index: 18 source families checked, 18 connected
- MSHP traffic-safety aggregate crash files preflight: about 0.32 MB across the key crash Excel files
- MSHP crash aggregate index: 9 official Excel files, 540 metric-year records
- DOR aggregate public reports: 7 official report files, about 5.8 MB downloaded, 38,451 parsed aggregate records
- DOR local parsed JSON index: about 20 MB, ignored by Git
- MERIC LAUS labor index: 25 official CSV downloads, about 0.31 MB local footprint, 353 aggregate rows, 116 areas, and 115 county areas
- Hospital profile rows processed: 166
- LTC census rows processed: 47

## Sanitization

Raw MAP downloads may contain vendor names and other row-level public records. The public QA files do not emit vendor names, employee salaries, person-level salary records, addresses, phone numbers, fax numbers, or hospital administrator names.

The local UI may answer exact public-record questions when the entity appears in the local MAP lookup index. Those answers come from deterministic lookup over local public source files, not from model memorization.

Contract lookup stores contract metadata and URLs. Contract document extraction is optional, capped, local-only, and ignored by Git. MAP payment context is computed separately from indexed MAP expenditure files when a contractor name can be matched.

DOR dealer source files are parsed into aggregate county/type counts. Individual dealer names, addresses, owner names, and phone numbers from that source are not returned by the chatbot.

## Current Scope

- Employee pay lookup is allowed for indexed public MAP employee files.
- Named-vendor expenditure lookup is allowed for indexed public MAP expenditure files.
- Contract number and contractor lookup is allowed for indexed public MissouriBUYS/OA contract metadata.
- Plain-English contract explanation is allowed when backed by contract metadata, source document links, optional local PDF text extraction, and citations.
- MSHP crash-statistic lookup is allowed for indexed aggregate SAC Excel files such as persons killed/injured, fatal crashes, death/injury rates, alcohol/speed involvement, motorcycle, commercial vehicle, young-driver, older-driver, and factor rankings.
- DOR aggregate lookup is allowed for indexed county taxable sales, business-location counts, vehicle counts, licensed-driver totals, dealer counts by county/type, and SIC location counts. Dealer outputs are aggregate only.
- MERIC LAUS lookup is allowed for indexed Missouri and county unemployment rate, labor force, employment, and unemployed-count questions. Missouri statewide rows use the seasonally adjusted series by default; county rows use the not-seasonally-adjusted public county series.
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
