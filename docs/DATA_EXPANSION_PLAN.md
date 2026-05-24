# Missouri Data Expansion Plan

This phase expands the chatbot beyond the original MAP, hospital, LTC, and civic-fact coverage while keeping the same rule: exact answers must come from cited public sources or deterministic local indexes.

## Phase 1 Scope

| Domain | Source | Phase 1 behavior | Risk |
| --- | --- | --- | --- |
| Contracts | [MissouriBUYS Contract Board](https://missouribuys.mo.gov/contractboard) and [OA Contract Search](https://archive.oa.mo.gov/purch/contracts/) | Index contract number, contractor, description, category, period, detail page, and document URLs. Join contractor names to MAP vendor payments when a likely match exists. | Moderate: legacy HTML/CGI pages can change. |
| Contract documents | [OA Contract Search](https://archive.oa.mo.gov/purch/contracts/) | Capped local PDF download and text extraction for plain-English contract explanations. | Moderate: PDF extraction can be imperfect; downloads must be capped. |
| Open data catalog | [data.mo.gov data.json](https://data.mo.gov/data.json) | Index statewide Socrata/DCAT metadata for dataset counts, themes, title/description/keyword search, landing pages, and distribution links before picking more datasets. | Moderate: mixed datasets, maps, files, and stale records. |
| Selected education open data | [Total Number of High School Seniors](https://data.mo.gov/d/8yaf-xv66) and [Completed FAFSAs Reported to MDHE](https://data.mo.gov/d/t9f4-ncza) | Parse school/year counts for high-school seniors and completed FAFSA applications, including top-school rankings and suppression-aware FAFSA rows. | Low: small JSON exports; still not full DESE accountability/staff/finance coverage. |
| Selected DESE school directory | [DESE School Directory](https://dese.mo.gov/data-system-management/directory) and [School Directory Data Downloads](https://dese.mo.gov/school-directory/data-downloads) | Parse the public School Directory by District PDF for district county, MSIP, enrollment, school/building counts, school codes, and grade spans while suppressing contact/person fields. | Low: 3.4 MB public PDF and about 4.6 MB local PDF/index footprint; still not full DESE accountability/staff/finance coverage. |
| Selected DESE APR rankings | [2025 APR Ranking - LEAs](https://dese.mo.gov/media/pdf/2025-ranking-apr-leas) and [2025 APR Ranking - Schools](https://dese.mo.gov/media/pdf/2025-ranking-apr-schools-final) | Parse public lowest-5% APR ranking PDFs for LEA and school-building ranks, county-district codes, building numbers, and single-year APR percent scores. | Low: about 0.6 MB of source PDFs; it does not compute APR or replace full MCDS/accountability parsers. |
| Selected DESE finance transfers | [2025-2026 7% Transfer](https://dese.mo.gov/media/pdf/2025-2026-162326-or-7-final), [2025-2026 5% Transfer](https://dese.mo.gov/media/pdf/2025-2026-fiscal-year-2005-2006-designated-levy-or-5-final), and [2025-2026 Transportation Transfer](https://dese.mo.gov/media/pdf/2020-2021-transportation-transfer-preliminary) | Parse selected public school-finance transfer PDFs for district-level transfer amounts, including district lookup, top-district ranking, and source PDF links. | Low: under 1 MB of source PDFs and about 1,554 parsed district report rows; it does not replace full MCDS, budget, audit, staff, or assessment parsers. |
| Selected public-health open data | [Missouri Communicable Disease Report (2026)](https://data.mo.gov/d/fk75-fa28) | Parse aggregate disease/condition rows for current-week YTD counts, previous-week YTD counts, 5-year median comparisons, rates per 100k, and rankings. | Moderate: aggregate surveillance data only; not medical advice and not full DHSS MICA/profile coverage. |
| Selected DHSS BRFSS aggregates | [DHSS BRFSS](https://health.mo.gov/data/brfss/index.php) and [front-page workbook](https://health.mo.gov/data/brfss/libs/Maindowna.xlsx) | Parse statewide adult prevalence indicators, data years, prevalence percentages, and confidence interval bounds from the official workbook. | Moderate: statewide aggregate workbook only; not respondent-level BRFSS data, county-level BRFSS values, MOPHIMS/MICA, or medical advice. |
| Selected DHSS vital-statistics aggregates | [DHSS Vital Statistics FOCUS](https://health.mo.gov/data/focus/) and [2023 Vital Statistics PDF](https://health.mo.gov/data/focus/pdf/2023-focus.pdf) | Parse statewide Table 1 aggregate counts and rates for births, deaths, natural increase, infant deaths, marriages, divorces, and population. | Moderate: statewide aggregate report values only; not county-level values, certificates, person records, MOPHIMS/MICA, or medical advice. |
| Selected DHSS MOPHIMS statewide profiles | [DHSS MOPHIMS ProfileBuilder](https://healthapps.dhss.mo.gov/MoPhims/ProfileBuilder?pc=24) | Parse selected default STATEWIDE / All demographic ProfileBuilder count/rate tables for child health, chronic disease comparisons, leading causes of death, emergency room visits, and inpatient hospitalizations. | Moderate: aggregate profile values only; not county, city, region, race/demographic slices, patient-level PAS, discharge records, or medical advice. |
| Selected DHSS WIC aggregates | [DHSS WIC Data](https://data.mo.gov/d/diyi-fr2a) | Query aggregate county and municipality rows for SFY 2025 household-row counts, redeemed net-benefit totals, average benefits, and rankings. | Moderate: source is household-level public data, so keep only aggregate query outputs and do not store raw household rows. |
| Selected long-term-care directory and census | [LTC Directory](https://data.mo.gov/d/fenu-sipv) and [LTC Census Report](https://data.mo.gov/d/bf8b-a47t) | Parse sanitized facility directory rows for county/city/facility capacity and aggregate census rows for licensed homes, licensed beds, census, and occupancy. | Moderate: directory source contains contact/person fields, so query and store only selected non-person facility fields plus aggregate census rows. |
| Education | [DESE School Data](https://dese.mo.gov/school-data) | Index public resource metadata for accountability/APR/MSIP, Core Data/MOSIS file layouts and code sets, school finance, assessment, special education, and dashboard source links beyond the selected directory parser. | Moderate: many exports live behind app/report surfaces; exact numeric MCDS/dashboard values still need dedicated parsers. |
| Public health | [DHSS Data](https://health.mo.gov/data/) | Index public-health resource metadata for county profiles, MOPHIMS/MICA, births/deaths, hospitalizations/PAS, BRFSS, county-level study, FOCUS reports, and related surveillance dashboards. Selected BRFSS statewide prevalence values, selected statewide vital-statistics Table 1 values, and selected MOPHIMS statewide profile values are parsed from official DHSS files; other health values should prefer aggregate outputs only. | High: health data needs privacy/suppression checks. |
| Traffic safety | [MSHP SAC Data](https://www.mshp.dps.mo.gov/MSHPWeb/SAC/data_960grid.html) | Build a local aggregate index for severity, rates, circumstances, alcohol/speed, motorcycle, commercial vehicle, young-driver, and older-driver crash files. | Low: files are small aggregate tables, but `.xls` parsing needs `xlrd`. |
| Labor market | [MERIC LAUS unemployment data](https://meric.mo.gov/data/economic/local-area-unemployment-statistics/laus) | Parse the public LAUS CSV route for current Missouri and county unemployment rate, labor force, employment, and unemployed counts; keep broader wage, industry, projection, and regional profile releases cataloged for future parsers. | Moderate: county/current-month coverage and release timestamps must be labeled. |
| Selected DNR water open data | [Consumer Confidence Report](https://data.mo.gov/d/3mwf-kse4) | Parse public drinking-water system rows for county counts, PWSID lookup, system-name lookup, and county rankings. | Low: small JSON export; still not full DNR water quality, permit, impaired-water, or GIS coverage. |
| Environment | [Missouri DNR Data and e-Services](https://dnr.mo.gov/data-e-services) | Index public resource metadata for water permits, MoCWIS, drinking-water tools, impaired waters, water quality, GIS/map viewers, air-emissions tools, E-Start, WIMS, GeoSTRAT, energy data, forms, and public notices. | Moderate: many surfaces are search tools or maps; exact numeric environmental values still need dedicated parsers. |
| Geospatial | [MSDIS](https://www.msdis.missouri.edu/), [MSDIS Open Data](https://data-msdis.opendata.arcgis.com/), and MSDIS ArcGIS REST service directories | Index public metadata for Open Data datasets, ArcGIS REST feature/map/image services, county boundaries, imagery, LiDAR/elevation, archive directories, and vector GIS links. | High: imagery, LiDAR, and GIS feature exports can be very large; this parser stores metadata and links only. |
| Transportation | [MoDOT traffic data](https://www.modot.org/modatazone/traffic), [traffic volume maps](https://www.modot.org/traffic-volume-maps), and [TrafficInfoSegAADT ArcGIS service](https://mapping.modot.mo.gov/arcgis/rest/services/BusinessInt/TrafficInfoSegAADT/MapServer) | Parse latest-year directional AADT route-segment records for exact route, direction, highest-volume, and segment-text lookup; keep broader safety/road tools cataloged. | Moderate: route/segment matching is not geocoding, and broader app/map values still need source-specific parsers. |
| Audits | [Missouri State Auditor reports](https://auditor.mo.gov/AuditReport/Reports) and [SearchAudits endpoint](https://auditor.mo.gov/AuditReport/SearchAudits) | Parse report metadata for report numbers, titles, release dates, official report pages, PDF links, recent reports, year counts, and title keyword search. | Moderate: metadata is structured, but PDF extraction and findings summaries must stay capped and separate. |
| Tax and revenue | [DOR public reports](https://dor.mo.gov/public-reports/) | Parse a first exact aggregate layer for 2025 county taxable sales, business-location counts, vehicle counts, licensed-driver totals, dealer counts by county/type, and SIC location counts. | Moderate: suppressed cells, PDFs, and historical taxable-sales years still need source-specific parsers. |
| Ethics and campaign finance | [Missouri Ethics Commission](https://mec.mo.gov/) | Parse public-resource metadata for campaign-finance searches, Committee Contributions & Expenditures, lobbying searches/reports, commission actions, advisory opinions, forms, PFD resources, and annual reports; leave entity-level filing rows for later dedicated adapters. | Moderate: entity matching must be precise and citation-heavy. |
| Elections | [Secretary of State elections](https://www.sos.mo.gov/elections/s_default) and selected official election-return PDFs | Parse selected statewide official return PDFs for winners, candidate votes, percentages, contest total votes, and primary party winners; keep broader candidate/ballot/turnout/calendar resources cataloged. | Moderate: avoid voter-level data; PDF formats vary, and county/precinct result files need separate parsers. |
| Budget | [OA Budget and Planning](https://budplan.oa.mo.gov/budget-information) | Parse metadata for executive budget links, budget summaries, revenue releases/detail files, performance-measure resources, demographic resources, and redistricting resources. | Moderate: proposed vs enacted budget stages must be labeled; linked PDF/Excel contents need separate parsers. |
| Child care | [DESE child care dashboards](https://dese.mo.gov/childhood/child-care/child-care-data-dashboards) | Parse quarterly dashboard PDFs for aggregate slots, pending facilities, inspections, complaint investigations, facility type counts, and licensing-time percentages; keep provider search and complaint narratives cataloged for future parsers. | Moderate: facility-level compliance context needs careful wording. |
| Long-term care | [DHSS nursing home inspections](https://health.mo.gov/safety/nursinghomesinspected/index.php) and [Show Me Long Term Care](https://healthapps.dhss.mo.gov/showmeltc/default.aspx) | Parse exact resource/search-filter metadata for official inspection search links, county/city filters, facility-type context, scope/severity links, laws/regulations links, and Nursing Home Compare guidance. Facility findings, complaints, survey narratives, and quality ratings remain future work. | High: health facility data needs context and no medical advice. |
| Utilities | [PSC reports](https://psc.mo.gov/General/PSC_Reports) and [Find A Missouri Utility](https://data.mo.gov/d/yeiz-h2m2) | Parse PSC report-volume metadata for covered periods, year-to-volume matching, and PDF links; parse the selected city/county utility-provider table for electric, gas, water, and telephone provider lookup. | Moderate: metadata/provider tables are small, but filings, staff positions, orders, tariffs, and rate-case outcomes must be distinguished. |
| Cannabis regulation | [DHSS Cannabis Regulation](https://health.mo.gov/safety/cannabis/) and [verified dispensary locator](https://health.mo.gov/safety/cannabis/licensed-facilities.php) | Parse the verified dispensary ArcGIS layer for sanitized facility counts/lookups and selected PY22-PY24 annual-report PDF metrics for sales, taxes, transfers, microbusiness licenses, agent cards, and operating facilities; keep live dashboards, transfer history, inspections, and product/regulatory updates cataloged. | Moderate: values are time-sensitive; locator contact/address fields are intentionally excluded. |
| Selected agriculture open data | [Missouri Department of Agriculture feed sample testing results](https://data.mo.gov/d/y9w9-qkg2) | Parse public feed sample testing rows for sample ID lookup, feed class counts/rankings, and selected nutrient guarantee/result values. | Low: structured Socrata export; still not full agricultural market, seed, inspection, complaint, or enforcement coverage. |
| Agriculture | [Agricultural Market News](https://agmarketnews.mo.gov/reports/) | Parse exact report-link metadata for cattle/livestock, swine, sheep/goat, hay/forage, feedstuff, grain, regional-market, and USDA AMS report links; leave linked PDF/dashboard prices for later parsers. | Low: public reports, but many links point to USDA AMS pages and linked PDF/dashboard contents need separate extraction. |

## Commands

Preflight all expansion sources:

```powershell
python scripts\preflight_data_expansion.py
```

Build the public source-page index used by the chatbot for cited source-discovery answers:

```powershell
python scripts\build_public_source_index.py --force
```

Build the data.mo.gov catalog metadata index used for exact dataset-search answers:

```powershell
python scripts\build_data_mo_catalog_index.py --force
```

Build the selected data.mo.gov education exact lookup index:

```powershell
python scripts\build_data_mo_education_index.py --force
```

Build the selected DESE School Directory exact lookup index:

```powershell
python scripts\build_dese_directory_index.py --force
```

Build the DESE School Data resource metadata lookup index:

```powershell
python scripts\build_dese_school_data_index.py --force
```

Build the selected DESE APR ranking exact lookup index:

```powershell
python scripts\build_dese_apr_index.py --force
```

Build the selected DESE school-finance transfer exact lookup index:

```powershell
python scripts\build_dese_finance_index.py --force
```

Build the selected data.mo.gov public-health exact lookup index:

```powershell
python scripts\build_data_mo_health_index.py --force
```

Build the selected DHSS BRFSS statewide aggregate exact lookup index:

```powershell
python scripts\build_dhss_brfss_index.py --force
```

Build the selected DHSS vital-statistics statewide aggregate exact lookup index:

```powershell
python scripts\build_dhss_vital_stats_index.py --force
```

Build the selected DHSS MOPHIMS statewide profile exact lookup index:

```powershell
python scripts\build_dhss_mophims_profiles_index.py --force
```

Build the DHSS public-health resource metadata lookup index:

```powershell
python scripts\build_dhss_health_sources_index.py --force
```

Build the selected DHSS WIC aggregate exact lookup index:

```powershell
python scripts\build_data_mo_wic_index.py --force
```

Build the selected data.mo.gov long-term-care exact lookup index:

```powershell
python scripts\build_data_mo_ltc_index.py --force
```

Build the DHSS long-term-care inspection resource metadata lookup index:

```powershell
python scripts\build_dhss_ltc_inspection_index.py --force
```

Build the selected data.mo.gov DNR water exact lookup index:

```powershell
python scripts\build_data_mo_water_index.py --force
```

Build the DNR data/e-services resource metadata lookup index:

```powershell
python scripts\build_dnr_resources_index.py --force
```

Build the MSDIS geospatial resource metadata lookup index:

```powershell
python scripts\build_msdis_geospatial_index.py --force
```

Build the MoDOT latest-year AADT exact lookup index:

```powershell
python scripts\build_modot_aadt_index.py --force
```

Build the MEC public-resource metadata lookup index:

```powershell
python scripts\build_mec_resources_index.py --force
```

Build the selected data.mo.gov utility exact lookup index:

```powershell
python scripts\build_data_mo_utility_index.py --force
```

Build the selected PSC report metadata exact lookup index:

```powershell
python scripts\build_psc_reports_index.py --force
```

Build the selected OA Budget and Planning metadata exact lookup index:

```powershell
python scripts\build_oa_budget_index.py --force
```

Build the selected data.mo.gov agriculture exact lookup index:

```powershell
python scripts\build_data_mo_agriculture_index.py --force
```

Build the selected Agricultural Market News report metadata lookup index:

```powershell
python scripts\build_ag_market_news_index.py --force
```

Build the selected DHSS cannabis exact lookup index:

```powershell
python scripts\build_cannabis_index.py --force
```

Build the selected DESE child-care dashboard exact lookup index:

```powershell
python scripts\build_child_care_index.py --force
```

Build the MSHP aggregate crash-statistics index:

```powershell
python scripts\build_mshp_crash_index.py --force
```

Build the DOR aggregate public-reports index:

```powershell
python scripts\build_dor_reports_index.py --force
```

Build the MERIC LAUS labor-market index:

```powershell
python scripts\build_meric_labor_index.py --force
```

Build the Missouri State Auditor report metadata index:

```powershell
python scripts\build_state_auditor_index.py --force
```

Build the selected SOS election-return exact lookup index:

```powershell
python scripts\build_sos_elections_index.py --force
```

Build a conservative local contract metadata index:

```powershell
python scripts\build_contract_index.py --detail-limit 200 --delay-seconds 0.04
```

Build the full contract-detail index after the conservative run is stable:

```powershell
python scripts\build_contract_index.py --force --delay-seconds 0.04
```

Build a capped local contract-document text index:

```powershell
python scripts\build_contract_document_index.py --limit 25 --max-mb 25
```

## Current Contract Lookup

The contract index is local-only under `data/raw_public/contracts/` and is ignored by Git. The published repo includes the code and reports, not the raw local index.

Supported question shapes:

```text
Find contract CC221256001 and show its document links.
Explain contract CC221256001 in simple terms.
Search contracts for automotive parts.
What contracts mention Elliott Auto Supply?
```

The chatbot returns contract metadata, detail-page links, document links, optional extracted PDF text snippets, and a MAP payment context when the contractor name can be matched confidently to the local MAP vendor index.

## Not In Phase 1

- Downloading every contract PDF or Word document.
- Training on raw contract documents.
- Health row-level records.
- Person-level crash reports.
- DESE data behind secure/login-only surfaces, full accountability calculations, or unparsed MCDS/dashboard numeric values beyond the selected APR ranking PDFs and selected school-finance transfer PDFs.
- DHSS county-level BRFSS, broader MOPHIMS/MICA query results, county/city/race/demographic profile slices, vital records/certificates, hospital-discharge records, and patient/respondent-level health data beyond the selected statewide aggregate BRFSS workbook, selected statewide vital-statistics Table 1 rows, and selected MOPHIMS STATEWIDE / All demographic profile rows.
