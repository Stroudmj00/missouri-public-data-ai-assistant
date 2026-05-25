# Missouri Data Expansion Plan

This phase expands the chatbot beyond the original MAP, hospital, LTC, and civic-fact coverage while keeping the same rule: exact answers must come from cited public sources or deterministic local indexes.

## Phase 1 Scope

| Domain | Source | Phase 1 behavior | Risk |
| --- | --- | --- | --- |
| Contracts | [MissouriBUYS Contract Board](https://missouribuys.mo.gov/contractboard) and [OA Contract Search](https://archive.oa.mo.gov/purch/contracts/) | Index contract number, contractor, description, category, period, detail page, and document URLs. Join contractor names to MAP vendor payments when a likely match exists. | Moderate: legacy HTML/CGI pages can change. |
| Contract documents | [OA Contract Search](https://archive.oa.mo.gov/purch/contracts/) | Capped local PDF download and text extraction for plain-English contract explanations, document-text coverage summaries, and targeted snippet searches for renewal, expiration, scope, purpose, and public-use language. | Moderate: PDF extraction can be imperfect; downloads must be capped and snippets are not substitutes for the official contract. |
| Open data catalog | [data.mo.gov data.json](https://data.mo.gov/data.json) | Index statewide Socrata/DCAT metadata for dataset counts, themes, title/description/keyword search, landing pages, and distribution links before picking more datasets. | Moderate: mixed datasets, maps, files, and stale records. |
| Selected education open data | [Total Number of High School Seniors](https://data.mo.gov/d/8yaf-xv66) and [Completed FAFSAs Reported to MDHE](https://data.mo.gov/d/t9f4-ncza) | Parse school/year counts for high-school seniors and completed FAFSA applications, including top-school rankings and suppression-aware FAFSA rows. | Low: small JSON exports; still not full DESE accountability/staff/finance coverage. |
| Selected DESE school directory | [DESE School Directory](https://dese.mo.gov/data-system-management/directory) and [School Directory Data Downloads](https://dese.mo.gov/school-directory/data-downloads) | Parse the public School Directory by District PDF for district county, MSIP, enrollment, certified-staff counts, school/building counts, school codes, and grade spans while suppressing contact/person fields. | Low: 3.4 MB public PDF and about 4.6 MB local PDF/index footprint; still not full DESE accountability/detailed-staff/finance coverage. |
| Selected DESE assessment aggregates | [Missouri Education Data Explorer downloads](https://moschooldata.org/downloads), [Learning Outcomes dashboard](https://moschooldata.org/dashboards/proficiency), [DESE School Data](https://dese.mo.gov/school-data), and [DESE Assessment](https://dese.mo.gov/quality-schools/assessment) | Stream the public 2025 Missouri Assessment Program aggregate CSV and keep statewide plus selected district/school All Students performance-level rows for Below Basic, Basic, Proficient, and Advanced. | Moderate: the public source CSV is about 197 MB, so the builder streams it and does not save the raw file; selected aggregate coverage is not full MCDS/dashboard coverage. |
| Selected DESE APR rankings | [2025 APR Ranking - LEAs](https://dese.mo.gov/media/pdf/2025-ranking-apr-leas) and [2025 APR Ranking - Schools](https://dese.mo.gov/media/pdf/2025-ranking-apr-schools-final) | Parse public lowest-5% APR ranking PDFs for LEA and school-building ranks, county-district codes, building numbers, and single-year APR percent scores. | Low: about 0.6 MB of source PDFs; it does not compute APR or replace full MCDS/accountability parsers. |
| Selected DESE finance transfers | [2025-2026 7% Transfer](https://dese.mo.gov/media/pdf/2025-2026-162326-or-7-final), [2025-2026 5% Transfer](https://dese.mo.gov/media/pdf/2025-2026-fiscal-year-2005-2006-designated-levy-or-5-final), and [2025-2026 Transportation Transfer](https://dese.mo.gov/media/pdf/2020-2021-transportation-transfer-preliminary) | Parse selected public school-finance transfer PDFs for district-level transfer amounts, including district lookup, top-district ranking, and source PDF links. | Low: under 1 MB of source PDFs and about 1,554 parsed district report rows; it does not replace full MCDS, budget, audit, staff, or assessment parsers. |
| Selected DESE special-education incidence | [Special Education Data Reports](https://dese.mo.gov/special-education/data-reports) and [School Age Incidence Rates by disability and year - statewide](https://apps.dese.mo.gov/MCDS/FileDownloadWebHandler.ashx?filename=7d504a44-c2ddIncidence+Rate+90-present.pdf) | Parse statewide school-age child counts, incidence rates, total child count, enrollment, top disability-category rankings, and adjacent-year trend checks. | Low: about 0.5 MB source PDF and less than 2 MB local footprint; statewide aggregate only, not district profiles or student-level records. |
| Selected public-health open data | [Missouri Communicable Disease Report (2026)](https://data.mo.gov/d/fk75-fa28) | Parse aggregate disease/condition rows for current-week YTD counts, previous-week YTD counts, 5-year median comparisons, rates per 100k, and rankings. | Moderate: aggregate surveillance data only; not medical advice and not full DHSS MICA/profile coverage. |
| Selected hospital profile open data | [Profile of Hospitals](https://data.mo.gov/d/q8me-hzr8) | Parse public facility profile rows for statewide, region, and facility licensed-bed/ICU-bed totals, license type, and largest-facility rankings. | Moderate: facility profile values only; not medical advice, quality ranking, availability verification, inspections, or contact lookup. Address, phone, fax, and administrator-name fields are suppressed in chatbot output. |
| Selected DHSS BRFSS aggregates | [DHSS BRFSS](https://health.mo.gov/data/brfss/index.php) and [front-page workbook](https://health.mo.gov/data/brfss/libs/Maindowna.xlsx) | Parse statewide adult prevalence indicators, data years, prevalence percentages, and confidence interval bounds from the official workbook. | Moderate: statewide aggregate workbook only; not respondent-level BRFSS data, county-level BRFSS values, MOPHIMS/MICA, or medical advice. |
| Selected DHSS vital-statistics aggregates | [DHSS Vital Statistics FOCUS](https://health.mo.gov/data/focus/), [2023 Vital Statistics FOCUS PDF](https://health.mo.gov/data/focus/pdf/2023-focus.pdf), and [2023 annual Missouri Vital Statistics PDF](https://health.mo.gov/data/vitalstatistics/mvs23/2023MissouriVitalStatistics.pdf) | Parse statewide Table 1 aggregate counts/rates and annual county Table 16A resident/recorded births, deaths, natural increase, and rates. | Moderate: aggregate report values only; not certificates, person records, city/demographic slices, MOPHIMS/MICA, or medical advice. |
| Selected DHSS MOPHIMS profiles | [DHSS MOPHIMS ProfileBuilder](https://healthapps.dhss.mo.gov/MoPhims/ProfileBuilder?pc=24) | Parse selected default STATEWIDE / All demographic ProfileBuilder count/rate tables plus selected COUNTY leading-causes-of-death and inpatient-hospitalization rows for Boone, Cole, Greene, Jackson, St. Louis County, and St. Louis City. | Moderate: aggregate profile values only; not all-county, city, region, race/demographic slices, patient-level PAS, discharge records, or medical advice. |
| Selected DHSS WIC aggregates | [DHSS WIC Data](https://data.mo.gov/d/diyi-fr2a) | Query aggregate county and municipality rows for SFY 2025 household-row counts, redeemed net-benefit totals, average benefits, and rankings. | Moderate: source is household-level public data, so keep only aggregate query outputs and do not store raw household rows. |
| Selected data.mo.gov food pantry service locations | [Food Pantry List](https://data.mo.gov/d/eb3y-vtsa) | Parse public agency, county, city, public phone, public address, hours, and count fields for citizen-facing service-location lookup. | Low to moderate: public directory data, but avoid eligibility, benefits, nutrition, emergency-service, or recommendation advice; hours may be stale. |
| Selected data.mo.gov farmers-market directory | [Missouri Farmers' Markets](https://data.mo.gov/d/2zg8-cta8) | Parse public listing name, county, city, public address, website, profile/description, and count fields for citizen-facing market-directory lookup. | Low to moderate: public directory data, but suppress contact-name and email fields; avoid endorsements, live-hours guarantees, product availability, or recommendations. |
| Selected long-term-care directory and census | [LTC Directory](https://data.mo.gov/d/fenu-sipv) and [LTC Census Report](https://data.mo.gov/d/bf8b-a47t) | Parse sanitized facility directory rows for county/city/facility capacity and aggregate census rows for licensed homes, licensed beds, census, and occupancy. | Moderate: directory source contains contact/person fields, so query and store only selected non-person facility fields plus aggregate census rows. |
| Education | [DESE School Data](https://dese.mo.gov/school-data) | Index public resource metadata for accountability/APR/MSIP, Core Data/MOSIS file layouts and code sets, school finance, assessment, special education, and dashboard source links beyond the selected directory parser. | Moderate: many exports live behind app/report surfaces; exact numeric MCDS/dashboard values still need dedicated parsers. |
| Public health | [DHSS Data](https://health.mo.gov/data/) | Index public-health resource metadata for county profiles, MOPHIMS/MICA, births/deaths, hospitalizations/PAS, BRFSS, county-level study, FOCUS reports, and related surveillance dashboards. Selected BRFSS statewide prevalence values, selected statewide vital-statistics Table 1 values, selected annual county vital-statistics Table 16A values, selected MOPHIMS statewide profile values, and selected county leading-causes-of-death/inpatient-hospitalization values are parsed from official DHSS files; other health values should prefer aggregate outputs only. | High: health data needs privacy/suppression checks. |
| Traffic safety | [MSHP SAC Data](https://www.mshp.dps.mo.gov/MSHPWeb/SAC/data_960grid.html) and [Traffic Safety Compendium](https://www.mshp.dps.mo.gov/MSHPWeb/SAC/Compendium/TrafficCompendium.html) | Build a local aggregate index for severity, rates, circumstances, alcohol/speed, motorcycle, commercial vehicle, young-driver, and older-driver crash files, plus selected 2023 Compendium statewide/factor HTML tables and selected county severity/speed/alcohol-drug tables. | Low: files are small aggregate tables, but `.xls` parsing needs `xlrd`; Compendium parsing is selected rather than a full mirror. |
| Labor market | [MERIC LAUS unemployment data](https://meric.mo.gov/data/economic/local-area-unemployment-statistics/laus) | Parse the public LAUS CSV route for current Missouri and county unemployment rate, labor force, employment, and unemployed counts; keep broader wage, industry, projection, and regional profile releases cataloged for future parsers. | Moderate: county/current-month coverage and release timestamps must be labeled. |
| Selected DNR water open data | [Consumer Confidence Report](https://data.mo.gov/d/3mwf-kse4) | Parse public drinking-water system rows for county counts, PWSID lookup, system-name lookup, and county rankings. | Low: small JSON export; still not full DNR water quality, permit, impaired-water, or GIS coverage. |
| Selected DNR oil and gas open data | [Oil and Gas Permits](https://data.mo.gov/d/y64b-aec2) | Parse public permit rows for permit-ID lookup, county counts, status counts, company/operator rankings, and permit-PDF links. | Low: structured Socrata export; not production, compliance, landowner, or legal-advice coverage. |
| Selected DNR hazardous-waste open data | [Hazardous Waste Treatment, Storage and Disposal Facilities](https://data.mo.gov/d/m7dn-rv29) | Parse public facility rows for EPA ID lookup, facility-name lookup, county/status counts, county rankings, DNR region summaries, and source links. | Low to moderate: structured Socrata export, but do not return phone/contact fields or infer compliance, enforcement, remediation, or environmental risk. |
| Environment | [Missouri DNR Data and e-Services](https://dnr.mo.gov/data-e-services) and [DNR Impaired Waters](https://dnr.mo.gov/water/hows-water/impaired) | Index public resource metadata for water permits, MoCWIS, drinking-water tools, impaired waters, water quality, GIS/map viewers, air-emissions tools, E-Start, WIMS, GeoSTRAT, energy data, forms, and public notices. Parse the selected proposed 2024-2026 Section 303(d) listed-waters PDF for county counts, pollutant summaries, waterbody matches, and high-priority TMDL rows. | Moderate: many surfaces are search tools or maps; the impaired-waters parser is a 34.39 MB capped PDF snapshot and does not answer live water safety, permits, health, or legal questions. Broader exact numeric environmental values still need dedicated parsers. |
| Geospatial | [MSDIS](https://www.msdis.missouri.edu/), [MSDIS Open Data](https://data-msdis.opendata.arcgis.com/), and MSDIS ArcGIS REST service directories | Index public metadata for Open Data datasets, ArcGIS REST feature/map/image services, county boundaries, imagery, LiDAR/elevation, archive directories, and vector GIS links. | High: imagery, LiDAR, and GIS feature exports can be very large; this parser stores metadata and links only. |
| Transportation | [MoDOT traffic data](https://www.modot.org/modatazone/traffic), [traffic volume maps](https://www.modot.org/traffic-volume-maps), and [TrafficInfoSegAADT ArcGIS service](https://mapping.modot.mo.gov/arcgis/rest/services/BusinessInt/TrafficInfoSegAADT/MapServer) | Parse latest-year directional AADT route-segment records for exact route, direction, highest-volume, and segment-text lookup; keep broader safety/road tools cataloged. | Moderate: route/segment matching is not geocoding, and broader app/map values still need source-specific parsers. |
| Audits | [Missouri State Auditor reports](https://auditor.mo.gov/AuditReport/Reports) and [SearchAudits endpoint](https://auditor.mo.gov/AuditReport/SearchAudits) | Parse report metadata for report numbers, titles, release dates, official report pages, PDF links, recent reports, year counts, and title keyword search; build a capped selected PDF text layer for plain-English report orientation. | Moderate: metadata is structured and PDF extraction is capped; broader findings comparison and legal/accountability conclusions remain out of scope. |
| Tax and revenue | [DOR public reports](https://dor.mo.gov/public-reports/) | Parse a first exact aggregate layer for 2016-2025 county taxable sales, FY22-FY25 food tax by political subdivision, 2024-2025 Working Family Tax Credit income ranges, business-location counts, vehicle counts, licensed-driver totals, dealer counts by county/type, and SIC location counts. | Moderate: suppressed cells, noncounty taxable-sales reports, and broader DOR report families still need source-specific parsers. |
| Ethics and campaign finance | [Missouri Ethics Commission](https://mec.mo.gov/) | Parse public-resource metadata for campaign-finance searches, Committee Contributions & Expenditures, lobbying searches/reports, commission actions, advisory opinions, forms, PFD resources, and annual reports; leave entity-level filing rows for later dedicated adapters. | Moderate: entity matching must be precise and citation-heavy. |
| Elections | [Secretary of State elections](https://www.sos.mo.gov/elections/s_default), selected official election-return PDFs, [2024 county results](https://www.sos.mo.gov/CMSImages/ElectionResultsStatistics/ActualResults-November52024.pdf), and [2024 voter turnout](https://www.sos.mo.gov/CMSImages/ElectionResultsStatistics/Nov2024OfficialVoterTurnout.pdf) | Parse selected statewide official return PDFs for winners, candidate votes, percentages, contest total votes, and primary party winners; parse selected 2024 county President/Governor result rows and 2024 county/jurisdiction turnout aggregates; keep broader candidate/ballot/calendar resources cataloged. | Moderate: avoid voter-level data; PDF formats vary, and precinct files, all-contest county coverage, ballot measures, and candidate filings need separate parsers. |
| Budget | [OA Budget and Planning](https://budplan.oa.mo.gov/budget-information) and [Revenue Information](https://budplan.oa.mo.gov/revenue-information) | Parse metadata for executive budget links, budget summaries, revenue release/detail file links, performance-measure resources, demographic resources, and redistricting resources; parse selected FY 2026 monthly General Revenue Detail Excel workbooks for aggregate revenue/refund line-item lookup. | Moderate: proposed vs enacted budget stages must be labeled; only selected revenue-detail Excel contents are parsed, while broader budget PDFs and older final-year details need separate parsers. |
| Child care | [DESE child care dashboards](https://dese.mo.gov/childhood/child-care/child-care-data-dashboards) | Parse quarterly dashboard PDFs for aggregate slots, pending facilities, inspections, complaint investigations, facility type counts, and licensing-time percentages; keep provider search and complaint narratives cataloged for future parsers. | Moderate: facility-level compliance context needs careful wording. |
| Long-term care | [DHSS nursing home inspections](https://health.mo.gov/safety/nursinghomesinspected/index.php) and [Show Me Long Term Care](https://healthapps.dhss.mo.gov/showmeltc/default.aspx) | Parse exact resource/search-filter metadata for official inspection search links, county/city filters, facility-type context, scope/severity links, laws/regulations links, and Nursing Home Compare guidance. Facility findings, complaints, survey narratives, and quality ratings remain future work. | High: health facility data needs context and no medical advice. |
| Utilities | [PSC reports](https://psc.mo.gov/General/PSC_Reports) and [Find A Missouri Utility](https://data.mo.gov/d/yeiz-h2m2) | Parse PSC report-volume metadata for covered periods, year-to-volume matching, and PDF links; parse a capped selected report-PDF text sample for simple orientation and snippet search; parse the selected city/county utility-provider table for electric, gas, water, and telephone provider lookup. | Moderate: metadata/provider tables are small, but PSC PDFs are large and filings, staff positions, orders, tariffs, legal conclusions, and rate-case outcomes must be distinguished. |
| Cannabis regulation | [DHSS Cannabis Regulation](https://health.mo.gov/safety/cannabis/) and [verified dispensary locator](https://health.mo.gov/safety/cannabis/licensed-facilities.php) | Parse the verified dispensary ArcGIS layer for sanitized facility counts/lookups and selected PY22-PY24 annual-report PDF metrics for sales, taxes, transfers, microbusiness licenses, agent cards, and operating facilities; keep live dashboards, transfer history, inspections, and product/regulatory updates cataloged. | Moderate: values are time-sensitive; locator contact/address fields are intentionally excluded. |
| Selected agriculture open data | [Missouri Department of Agriculture feed sample testing results](https://data.mo.gov/d/y9w9-qkg2) | Parse public feed sample testing rows for sample ID lookup, feed class counts/rankings, and selected nutrient guarantee/result values. | Low: structured Socrata export; still not full agricultural market, seed, inspection, complaint, or enforcement coverage. |
| Agriculture | [Agricultural Market News](https://agmarketnews.mo.gov/reports/) | Parse exact report-link metadata for cattle/livestock, swine, sheep/goat, hay/forage, feedstuff, grain, regional-market, and USDA AMS report links; parse a capped selected PDF document layer for Missouri hay price ranges, demand/supply context, and Joplin receipt/steer examples. | Low to medium: public reports, but linked PDF/dashboard coverage must stay capped and clearly labeled so market facts are not confused with forecasts or recommendations. |

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

Build the selected DESE assessment aggregate exact lookup index:

```powershell
python scripts\build_dese_assessment_index.py --force
```

Build the selected DESE APR ranking exact lookup index:

```powershell
python scripts\build_dese_apr_index.py --force
```

Build the selected DESE school-finance transfer exact lookup index:

```powershell
python scripts\build_dese_finance_index.py --force
```

Build the selected DESE special-education incidence exact lookup index:

```powershell
python scripts\build_dese_special_education_index.py --force
```

Build the selected data.mo.gov public-health exact lookup index:

```powershell
python scripts\build_data_mo_health_index.py --force
```

Build the selected DHSS BRFSS statewide aggregate exact lookup index:

```powershell
python scripts\build_dhss_brfss_index.py --force
```

Build the selected DHSS vital-statistics statewide and county aggregate exact lookup index:

```powershell
python scripts\build_dhss_vital_stats_index.py --force
```

Build the selected DHSS MOPHIMS profile exact lookup index:

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

Build the selected data.mo.gov Food Pantry List exact lookup index:

```powershell
python scripts\build_data_mo_food_pantry_index.py --force
```

Build the selected data.mo.gov Missouri Farmers' Markets exact lookup index:

```powershell
python scripts\build_data_mo_farmers_market_index.py --force
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

Build the selected data.mo.gov DNR oil-and-gas permit exact lookup index:

```powershell
python scripts\build_data_mo_dnr_oil_gas_index.py --force
```

Build the selected data.mo.gov DNR hazardous-waste facility exact lookup index:

```powershell
python scripts\build_data_mo_dnr_hazardous_waste_index.py --force
```

Build the DNR data/e-services resource metadata lookup index:

```powershell
python scripts\build_dnr_resources_index.py --force
```

Build the selected DNR impaired-waters PDF lookup index:

```powershell
python scripts\build_dnr_impaired_waters_index.py --force
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

Build the MEC Electronic Annual Report aggregate lookup index:

```powershell
python scripts\build_mec_annual_report_index.py --force
```

Build the selected data.mo.gov utility exact lookup index:

```powershell
python scripts\build_data_mo_utility_index.py --force
```

Build the selected PSC report metadata exact lookup index:

```powershell
python scripts\build_psc_reports_index.py --force
```

Build the capped selected PSC report document text index:

```powershell
python scripts\build_psc_report_document_index.py --limit 1 --max-mb 60 --force
```

Build the selected OA Budget and Planning metadata exact lookup index:

```powershell
python scripts\build_oa_budget_index.py --force
```

Build the selected OA General Revenue Detail exact lookup index:

```powershell
python scripts\build_oa_revenue_detail_index.py --force
```

Build the selected data.mo.gov agriculture exact lookup index:

```powershell
python scripts\build_data_mo_agriculture_index.py --force
```

Build the selected Agricultural Market News report metadata lookup index:

```powershell
python scripts\build_ag_market_news_index.py --force
```

Build the capped selected Agricultural Market News report-PDF document index:

```powershell
python scripts\build_ag_market_report_document_index.py --force
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

Build the selected Missouri State Auditor report PDF text index:

```powershell
python scripts\build_state_auditor_document_index.py --limit 10 --max-mb 25 --report-number 2026-044 --force
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
python scripts\build_contract_document_index.py --limit 50 --max-mb 25
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
- DESE data behind secure/login-only surfaces, full accountability calculations, or unparsed MCDS/dashboard numeric values beyond the selected assessment aggregate rows, selected APR ranking PDFs, selected school-finance transfer PDFs, and selected statewide special-education incidence PDF.
- DHSS county-level BRFSS, broader MOPHIMS/MICA query results, all-county/city/race/demographic profile slices, vital records/certificates, hospital-discharge records, and patient/respondent-level health data beyond the selected statewide aggregate BRFSS workbook, selected statewide vital-statistics Table 1 rows, selected county vital-statistics Table 16A rows, selected MOPHIMS STATEWIDE / All demographic profile rows, and selected county leading-causes-of-death/inpatient-hospitalization rows.
