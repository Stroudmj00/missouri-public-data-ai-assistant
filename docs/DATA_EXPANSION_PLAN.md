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
| Selected public-health open data | [Missouri Communicable Disease Report (2026)](https://data.mo.gov/d/fk75-fa28) | Parse aggregate disease/condition rows for current-week YTD counts, previous-week YTD counts, 5-year median comparisons, rates per 100k, and rankings. | Moderate: aggregate surveillance data only; not medical advice and not full DHSS MICA/profile/BRFSS coverage. |
| Selected DHSS WIC aggregates | [DHSS WIC Data](https://data.mo.gov/d/diyi-fr2a) | Query aggregate county and municipality rows for SFY 2025 household-row counts, redeemed net-benefit totals, average benefits, and rankings. | Moderate: source is household-level public data, so keep only aggregate query outputs and do not store raw household rows. |
| Selected long-term-care directory and census | [LTC Directory](https://data.mo.gov/d/fenu-sipv) and [LTC Census Report](https://data.mo.gov/d/bf8b-a47t) | Parse sanitized facility directory rows for county/city/facility capacity and aggregate census rows for licensed homes, licensed beds, census, and occupancy. | Moderate: directory source contains contact/person fields, so query and store only selected non-person facility fields plus aggregate census rows. |
| Education | [DESE School Data](https://dese.mo.gov/school-data) | Catalog accountability, assessment, staff, school finance, dashboard, and broader school-data sources beyond the selected directory parser. | Moderate: many exports live behind app/report surfaces. |
| Public health | [DHSS Data](https://health.mo.gov/data/) | Catalog county profiles, births, deaths, hospitalizations/PAS, BRFSS, and related public-health sources. Prefer aggregate outputs only. | High: health data needs privacy/suppression checks. |
| Traffic safety | [MSHP SAC Data](https://www.mshp.dps.mo.gov/MSHPWeb/SAC/data_960grid.html) | Build a local aggregate index for severity, rates, circumstances, alcohol/speed, motorcycle, commercial vehicle, young-driver, and older-driver crash files. | Low: files are small aggregate tables, but `.xls` parsing needs `xlrd`. |
| Labor market | [MERIC LAUS unemployment data](https://meric.mo.gov/data/economic/local-area-unemployment-statistics/laus) | Parse the public LAUS CSV route for current Missouri and county unemployment rate, labor force, employment, and unemployed counts; keep broader wage, industry, projection, and regional profile releases cataloged for future parsers. | Moderate: county/current-month coverage and release timestamps must be labeled. |
| Selected DNR water open data | [Consumer Confidence Report](https://data.mo.gov/d/3mwf-kse4) | Parse public drinking-water system rows for county counts, PWSID lookup, system-name lookup, and county rankings. | Low: small JSON export; still not full DNR water quality, permit, impaired-water, or GIS coverage. |
| Environment | [Missouri DNR Data and e-Services](https://dnr.mo.gov/data-e-services) | Catalog water permits, public water systems, impaired waters, water quality, and environmental GIS surfaces. | Moderate: many surfaces are search tools or maps. |
| Geospatial | [MSDIS](https://www.msdis.missouri.edu/) | Catalog vector/GIS services first; avoid imagery and LiDAR downloads by default. | High: imagery and LiDAR can be very large. |
| Transportation | [MoDOT traffic data](https://www.modot.org/modatazone/traffic) | Catalog traffic counts, traffic volume maps, road/route context, and safety sources. | Moderate: many values live in apps/maps. |
| Audits | [Missouri State Auditor reports](https://auditor.mo.gov/AuditReport/Menu) and [SearchAudits endpoint](https://auditor.mo.gov/AuditReport/SearchAudits) | Parse report metadata for report numbers, titles, release dates, official report pages, PDF links, recent reports, year counts, and title keyword search. | Moderate: metadata is structured, but PDF extraction and findings summaries must stay capped and separate. |
| Tax and revenue | [DOR public reports](https://dor.mo.gov/public-reports/) | Parse a first exact aggregate layer for 2025 county taxable sales, business-location counts, vehicle counts, licensed-driver totals, dealer counts by county/type, and SIC location counts. | Moderate: suppressed cells, PDFs, and historical taxable-sales years still need source-specific parsers. |
| Ethics and campaign finance | [Missouri Ethics Commission](https://mec.mo.gov/) | Catalog campaign finance, lobbying, committee contribution/expenditure, commission-action, and annual-report surfaces. | Moderate: entity matching must be precise and citation-heavy. |
| Elections | [Secretary of State elections](https://www.sos.mo.gov/elections/s_default) | Catalog election results, candidate/ballot resources, turnout, and election calendars. | Moderate: avoid voter-level data; formats vary. |
| Budget | [OA Budget and Planning](https://oa.mo.gov/budget-and-planning) | Catalog budget, revenue, performance-measure, demographic, redistricting, and fiscal-policy pages. | Moderate: proposed vs enacted budget stages must be labeled. |
| Child care | [DESE child care dashboards](https://dese.mo.gov/childhood/child-care/child-care-data-dashboards) | Catalog facilities, slots, inspections, complaints, pending facilities, and licensing timelines. | Moderate: facility-level compliance context needs careful wording. |
| Long-term care | [DHSS nursing home inspections](https://health.mo.gov/safety/nursinghomesinspected/index.php) | Catalog long-term-care inspections, facility types, beds, complaints, and Show Me Long-Term Care links. | High: health facility data needs context and no medical advice. |
| Utilities | [PSC reports](https://psc.mo.gov/General/PSC_Reports) and [Find A Missouri Utility](https://data.mo.gov/d/yeiz-h2m2) | Catalog PSC report volumes, utility report references, annual reports, and rate-case context; parse the selected city/county utility-provider table for electric, gas, water, and telephone provider lookup. | Moderate: provider table is small, but filings, staff positions, and orders must be distinguished. |
| Cannabis regulation | [DHSS Cannabis Regulation](https://health.mo.gov/safety/cannabis/) | Catalog annual reports, sales dashboards, transfer history, licensed facilities, and regulatory updates. | Moderate: values are time-sensitive and may be corrected. |
| Selected agriculture open data | [Missouri Department of Agriculture feed sample testing results](https://data.mo.gov/d/y9w9-qkg2) | Parse public feed sample testing rows for sample ID lookup, feed class counts/rankings, and selected nutrient guarantee/result values. | Low: structured Socrata export; still not full agricultural market, seed, inspection, complaint, or enforcement coverage. |
| Agriculture | [Agricultural Market News](https://agmarketnews.mo.gov/reports/) | Catalog livestock, cattle, swine, sheep/goat, and regional market reports. | Low: public reports, but many links point to USDA AMS pages. |

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

Build the selected data.mo.gov public-health exact lookup index:

```powershell
python scripts\build_data_mo_health_index.py --force
```

Build the selected DHSS WIC aggregate exact lookup index:

```powershell
python scripts\build_data_mo_wic_index.py --force
```

Build the selected data.mo.gov long-term-care exact lookup index:

```powershell
python scripts\build_data_mo_ltc_index.py --force
```

Build the selected data.mo.gov DNR water exact lookup index:

```powershell
python scripts\build_data_mo_water_index.py --force
```

Build the selected data.mo.gov utility exact lookup index:

```powershell
python scripts\build_data_mo_utility_index.py --force
```

Build the selected data.mo.gov agriculture exact lookup index:

```powershell
python scripts\build_data_mo_agriculture_index.py --force
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
- DESE data behind secure/login-only surfaces.
