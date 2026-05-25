# Case Study

## Question

Can a consumer desktop support a credible tiny-LLM workflow for simple public-data questions?

## Final Answer For This Version

Yes, for a constrained case study. The project now builds a safe public-data ingestion pipeline, generates sanitized aggregate QA pairs, runs a no-training baseline, fine-tunes a small LoRA adapter, compares the base and fine-tuned models on fixed evaluation prompts, and serves exact public-record answers through a deterministic local lookup index.

## Public-Data Twist

The project uses public Missouri sources:

- Missouri Accountability Portal public downloads, including expenditures, employee pay, tax credits, federal grants, budget restrictions, bonds, stimulus, and check cancellations
- data.mo.gov Profile of Hospitals, parsed into a cited hospital-profile lookup for facility/region/state bed totals while suppressing address, phone, fax, and administrator-name fields in chatbot output
- data.mo.gov LTC Census Report
- Missouri Department of Revenue public aggregate reports for taxable sales, business locations, vehicles, licensed drivers, dealers, and SIC location counts
- MERIC Local Area Unemployment Statistics public CSV downloads for current Missouri and county labor-market metrics
- State of Missouri `data.mo.gov` DCAT catalog metadata for dataset search, themes, landing pages, and distribution links
- Selected `data.mo.gov` education datasets for high-school senior counts and completed FAFSA application counts by school/year
- Selected DESE School Directory public PDF for district county, MSIP, enrollment, certified-staff count, school/building count, school code, and grade-span lookup
- DESE School Data resource pages for accountability/APR/MSIP, Core Data/MOSIS file layouts and code sets, school finance, assessment, and special-education links
- Selected DESE 2025 APR ranking public PDFs for lowest-5% LEA and school-building ranks and single-year APR percent scores
- Selected DESE 2025-2026 school-finance transfer PDFs for district-level 7%, 5%, and transportation transfer amounts
- Selected DESE special-education incidence PDF for statewide school-age child counts and incidence rates by disability category
- Selected `data.mo.gov` public-health aggregate data for communicable-disease YTD counts, rates per 100k, 5-year median comparisons, and rankings
- DHSS public-health resource pages for county profiles, MOPHIMS/MICA, BRFSS, births/deaths, hospitalizations/PAS, county-level study, FOCUS reports, and surveillance dashboard links
- DHSS BRFSS statewide aggregate workbook data for adult prevalence percentages and confidence interval bounds
- DHSS Vital Statistics FOCUS statewide Table 1 aggregate values for births, deaths, natural increase, infant deaths, marriages, divorces, and population
- Selected DHSS MOPHIMS statewide ProfileBuilder aggregate tables for child health, chronic disease comparisons, leading causes of death, emergency room visits, and inpatient hospitalizations
- Selected DHSS WIC aggregate data for SFY 2025 county and municipality household-row counts and redeemed net-benefit totals
- Selected `data.mo.gov` Food Pantry List rows for county, city, agency, public phone, public address, listed hours, and top-county counts
- Selected `data.mo.gov` LTC Directory and LTC Census Report data for sanitized facility capacity facts and aggregate occupancy
- DHSS long-term-care inspection resource pages and Show Me Long Term Care search-filter metadata for official source links, county/city filters, scope/severity links, and facility-type context
- Selected `data.mo.gov` DNR water data for public drinking-water system counts, PWSID lookup, and county rankings
- Selected `data.mo.gov` DNR oil and gas permit data for permit IDs, county counts, status counts, company/operator rankings, and permit-PDF links
- Selected `data.mo.gov` DNR hazardous-waste facility data for EPA IDs, county/status counts, facility lookups, and DNR region summaries
- Missouri DNR data/e-services resource pages for water permits, MoCWIS, drinking-water tools, impaired waters, water quality, GIS/map viewers, air emissions, E-Start, WIMS, GeoSTRAT, energy data, forms, and public notices
- Selected Missouri DNR proposed 2024-2026 Section 303(d) impaired-waters PDF rows for county counts, pollutant summaries, waterbody matches, and high-priority TMDL rows
- MSDIS geospatial Open Data, ArcGIS REST service, imagery, LiDAR/elevation, archive, and vector GIS metadata
- MoDOT TrafficInfoSegAADT public route-segment data for latest-year AADT traffic-volume lookup
- Missouri Ethics Commission public-resource pages for campaign-finance searches, lobbying searches/reports, forms, advisory opinions, commission actions, PFD resources, and annual reports
- Selected `data.mo.gov` utility data for city/county electric, gas, water, and telephone provider lookup
- Missouri Public Service Commission report metadata for report-volume, covered-period, year-to-volume, and PDF-link lookup
- Selected `data.mo.gov` agriculture feed sample testing data for sample IDs, feed class counts/rankings, and nutrient guarantee/result lookup
- Missouri Agricultural Market News report metadata for cattle/livestock, swine, sheep/goat, hay/forage, feedstuff, grain, regional-market, and USDA AMS report links
- Selected DHSS cannabis regulation data for verified dispensary counts/lookups and PY22-PY24 annual-report sales, tax, transfer, microbusiness, agent-card, and operating-facility metrics
- Selected DESE child-care dashboard PDFs for quarterly aggregate slots, pending facilities, inspections, complaint investigations, facility type counts, and licensing-time percentages
- Missouri State Auditor report search metadata for report numbers, titles, release dates, official report pages, and PDF links
- Selected Missouri State Auditor report PDFs for capped text extraction and plain-English report orientation
- Selected Missouri Secretary of State official election-return PDFs for statewide winners, candidate votes, percentages, contest total votes, and primary party winners

The project treats truly public MAP records as in scope when the matching public file has been downloaded and indexed. For row-level records, the app uses deterministic lookup rather than asking the tiny model to memorize names and dollar amounts.

## Current Pipeline

1. Estimate source download sizes and runtime before fetching data.
2. Download selected `data.mo.gov` sources and the current MAP public download inventory.
3. Keep raw public files local and ignored by Git.
4. Aggregate public records by agency, category, region, and public service area.
5. Generate sanitized QA pairs and fixed evaluation prompts.
6. Run a short baseline inference pass with no training.
7. Fine-tune a small LoRA adapter on the sanitized QA set.
8. Compare base and fine-tuned outputs on the same fixed prompts.
9. Download all current MAP public files and build a local SQLite lookup index.
10. Generate expanded MAP aggregate/source QA and run a second capped LoRA adapter.
11. Serve a tiny local UI that combines model QA with indexed public MAP lookup.
12. Publish data card, model card, reports, and generated QA artifacts.

## Results

- Training method: LoRA adapter on `HuggingFaceTB/SmolLM2-135M-Instruct`
- Training rows: 100
- Evaluation prompts: 20
- Training runtime: about 51 seconds
- Peak allocated VRAM during training: about 619 MB
- Adapter size: about 5.1 MB
- Base model pass rate: 18 / 20
- Fine-tuned adapter pass rate: 18 / 20
- Outcome: the adapter matched the base model overall, improved one prompt, regressed on one prompt, and still failed one prompt from the original refusal framing.
- Expanded MAP index: 104 text files and 6,123,427 parsed rows
- Run 002: 304 training rows, 40 eval rows, about 55 seconds, 619.14 MB peak VRAM
- Chatbot behavior suite: 297 adversarial, citation, row-preview, aggregate-ranking, general-chat, citizen-definition, hospital-profile, contract-vendor matching/payment context, contract document text/snippet, crash-statistic/county-crash, DOR aggregate, MERIC labor-market, MSDIS geospatial metadata, MoDOT AADT, MEC public-resource metadata, MEC annual-report aggregates, Missouri State Auditor metadata, Missouri State Auditor document text, SOS election-return/county/turnout, PSC report metadata, PSC report document text, OA Budget metadata, OA General Revenue Detail, Agricultural Market News metadata and selected report-PDF values, DESE School Data resource metadata, DESE APR ranking, DESE finance transfer, DESE special-education incidence, DESE School Directory certified-staff lookup, DHSS public-health resource metadata, DHSS BRFSS aggregate, DHSS vital-statistics aggregate, DHSS MOPHIMS statewide and selected county profile aggregate, DHSS LTC inspection metadata, data.mo.gov Food Pantry List, DNR data/e-services resource metadata, DNR oil-and-gas permit rows, DNR hazardous-waste facility rows, DNR impaired-waters PDF rows, data.mo.gov catalog, data.mo.gov education, DESE School Directory, data.mo.gov health, DHSS WIC aggregate, data.mo.gov LTC directory/census, data.mo.gov DNR water, data.mo.gov utility, data.mo.gov agriculture, DHSS cannabis, DESE child-care dashboards, sourced civic facts, and public-data routing cases passed
- Source usefulness probe: 40 representative source-family questions passed with at least one official HTTP source or download link per sourced answer
- Public source-page index: 18 Missouri source families connected for cited source-discovery answers
- MSHP crash aggregate index: 9 official SAC Excel files plus 14 selected 2023 Traffic Safety Compendium HTML reports, 2,358 aggregate records parsed locally
- DOR aggregate report index: 22 official public report files and 45,472 aggregate records parsed locally
- MERIC LAUS labor index: 25 official CSV downloads and 353 aggregate records parsed locally
- data.mo.gov catalog metadata index: 277 dataset records, 272 with distributions, 255 CSV links, and 255 JSON links
- data.mo.gov education index: 2 selected public education datasets and 14,123 parsed school/year rows
- DESE School Directory index: 489 district rows and 2,433 school/building rows parsed from a 3.4 MB public PDF, including district certified-staff counts
- DESE School Data resource metadata index: 382 public resource links across 8 official source pages
- DESE APR ranking index: 28 LEA rows and 101 school-building rows parsed from two official public PDF reports
- DESE school-finance transfer index: 1,554 district report rows parsed from three official public transfer PDFs
- DESE special-education incidence index: 559 statewide aggregate rows parsed from one official public PDF report
- data.mo.gov health index: 1 selected aggregate public-health dataset and 52 disease/condition rows
- DHSS public-health resource metadata index: 285 public resource links across 9 official source pages
- DHSS BRFSS aggregate index: 35 statewide prevalence indicators from the official workbook, covering 2018-2021
- DHSS vital-statistics aggregate index: 21 statewide Table 1 rows from the 2023 Vital Statistics FOCUS PDF, covering 2013, 2022, and 2023
- DHSS MOPHIMS profile index: 192 statewide aggregate rows across 5 selected official ProfileBuilder pages, plus 438 selected county leading-causes-of-death and inpatient-hospitalization rows
- data.mo.gov hospital profile index: 166 public facility profile rows, 21,202 licensed beds, and 2,032 ICU licensed beds
- DHSS WIC aggregate index: 86,044 public source household rows summarized into 115 county and 224 municipality aggregate rows
- data.mo.gov Food Pantry List index: 238 public service-location rows across 115 counties and 182 cities
- data.mo.gov LTC index: 1,101 sanitized directory rows, 986 unique facility numbers, 114 counties, and 47 aggregate census rows
- DHSS LTC inspection metadata index: 434 metadata rows from 2 official pages, including 24 resource links, 115 county filters, and 295 city filters
- data.mo.gov DNR water index: 1 selected public drinking-water dataset and 1,425 system rows
- data.mo.gov DNR oil and gas permit index: 10,490 public permit rows across 99 counties and 1,576 company/operator names
- data.mo.gov DNR hazardous-waste facility index: 86 public facility rows across 29 counties and 5 DNR regions
- DNR data/e-services resource metadata index: 281 public resource links across 9 official source pages
- DNR impaired-waters index: 549 selected rows from the proposed 2024-2026 Section 303(d) listed-waters PDF; 34.39 MB downloaded locally in the capped run
- MSDIS geospatial resource metadata index: 509 public resource links across 14 pages, feeds, and service endpoints
- MoDOT AADT index: 14,205 latest-year directional segment records for 229 routes across 4 directional layers
- MEC public-resource metadata index: 157 public resource/search/form/report links across 11 official source pages
- MEC annual-report aggregate index: 1,490 campaign-finance, lobbying, and PFD rows across official Electronic Annual Report years 2017-2026
- data.mo.gov utility index: 1 selected city/county utility-provider dataset and 1,718 rows
- PSC report metadata index: 27 official report PDF links, covering 1997-2023
- PSC report document text index: 1 selected official report PDF and 43.56 MB downloaded locally in the capped sample run
- data.mo.gov agriculture index: 1 selected public feed sample testing dataset and 8,388 rows
- Agricultural Market News metadata index: 77 report/resource links, including 71 PDF links, across 8 category groups
- Agricultural Market News document index: 3 selected official USDA AMS PDFs, 12 Missouri hay price rows, and 18 selected Joplin steer rows; about 0.90 MB downloaded locally in the capped sample run
- DHSS cannabis index: 223 verified dispensary records across 57 counties and 3 selected annual-report PDFs parsed for PY22-PY24 aggregate metrics
- DESE child-care dashboard index: 5 quarterly dashboard PDFs parsed for aggregate slots, facilities, inspections, complaints, and licensing-time metrics
- Missouri State Auditor metadata index: 3,447 report metadata rows for 1999-2026
- Missouri State Auditor document text index: 7 selected official report PDFs and 4.64 MB downloaded locally in the capped sample run
- SOS election returns index: 5 official SOS PDFs, 782 statewide contests, 1,604 statewide candidate/ballot rows, 1,404 selected 2024 county candidate rows, and 117 voter-turnout rows
- OA Budget metadata index: 114 official page/link records across 5 Budget and Planning pages
- OA General Revenue Detail index: 10 official monthly Excel workbooks and 210 aggregate revenue/refund line items

This is a credible case-study outcome because it preserves the negative result. The first fine-tune proved the local training loop and produced measurable behavior, but it did not improve the headline metric. The UI now makes the more practical architecture explicit: use the tiny model for simple QA over curated context, use deterministic lookup for exact public records, and keep ordinary low-risk chat separate from sourced public-data answers. The chatbot layer now treats exact MAP, MSHP, DOR, MERIC LAUS, MSDIS geospatial metadata, MoDOT AADT, MEC public-resource metadata and annual-report aggregates, Missouri State Auditor metadata and selected report PDF text, SOS election-return rows, PSC report metadata and selected PSC report PDF text, OA Budget metadata, OA General Revenue Detail workbook rows, Agricultural Market News metadata and selected USDA AMS report PDF values, DESE School Data resource metadata, DESE APR ranking rows, selected DESE school-finance transfer rows, selected DESE special-education incidence rows, DHSS public-health resource metadata, DHSS BRFSS aggregate rows, DHSS vital-statistics aggregate rows, DHSS MOPHIMS statewide and selected county profile rows, DHSS LTC inspection metadata, selected data.mo.gov Food Pantry List rows, DNR data/e-services resource metadata, selected DNR hazardous-waste facility rows, selected DNR impaired-waters PDF rows, data.mo.gov catalog, selected education, selected DESE School Directory, selected aggregate public-health, selected DHSS WIC aggregate, selected LTC directory/census, selected DNR water, selected utility-provider, selected agriculture feed-sample, selected cannabis regulation, sourced civic facts, and selected child-care dashboard questions as source-backed lookups with guardrails for unsupported years, list-all prompts, private identifiers, vendor IDs, reversed payment direction, buying/selling advice, water-safety advice, and unparsed live report coverage. Each sourced API response now carries a request id, retrieval path, dataset snapshot id, source-file citations, and capped row previews so a user can see what local public-data snapshot supported the answer; ordinary answers such as arithmetic do not show source or evidence panels.

## What This Demonstrates

- Conservative local ML environment setup
- Public-data provenance
- Source-scoped public-data handling
- Simple QA generation
- Deterministic lookup for exact public records
- Baseline evaluation before training
- Honest limitation reporting

## Next Experiment

Score aggregate QA, exact public lookup, unsupported-source questions, private-identifier refusals, and citation quality as separate benchmark categories. Then replace the heuristic matcher with a stronger search/ranking layer while keeping exact facts out of model memory.
