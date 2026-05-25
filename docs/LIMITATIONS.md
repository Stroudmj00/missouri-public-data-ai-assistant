# Limitations

## Not An Official Tool

This is an independent educational case study. It is not endorsed by, operated by, or representative of the State of Missouri.

## Small Evaluation Set

The final comparison uses 20 fixed prompts. That is enough for a portfolio case study, but not enough for a robust model-quality claim.

## Generated QA Templates

The QA set is generated from aggregate summaries. This makes the experiment reproducible, but it also means the task is narrow and partly template-like.

## First Fine-Tune Did Not Improve The Headline Metric

The LoRA adapter matched the base model at 18 / 20. It improved one prompt, regressed on one prompt, and failed the same refusal prompt as the base model.

## Refusal Behavior Needs Work

Both models failed the employee-salary prompt in the final evaluation when that prompt was framed as a refusal test. The next iteration should score public-but-not-indexed questions separately from private-identifier questions and numeric lookup.

## Public Data Does Not Mean Low Risk

Some public data sources include names or row-level payment records. This project keeps raw downloads local-only and emits aggregate QA artifacts, while the local UI can answer indexed named-vendor MAP expenditure totals and public MAP employee-pay lookups through deterministic lookup. Future expansion should repeat the source review and clearly label which public files are indexed.

## Tiny Models Should Not Memorize Public Records

Specific MAP facts should come from lookup/query code over public source files. The tiny model is useful for short answers over retrieved context, not as a trusted store of row-level public records.

## Source Coverage Varies

The MSHP aggregate crash-statistics index uses the official Excel files currently exposed by the Statistical Analysis Center page plus selected 2023 Traffic Safety Compendium HTML tables. The legacy Excel-file coverage varies by file and currently tops out at 2014, while the selected Compendium layer adds 2023 statewide severity and factor tables for speed, alcohol/drug, young-driver, older-driver, commercial-vehicle, motorcycle, school-bus, pedestrian/pedalcycle, work-zone, and deer/animal involvement, plus selected county severity/speed/alcohol-drug tables. It does not parse every Compendium table, municipal breakdowns, crash reports, or preliminary/live 2024+ crash data.

The DOR aggregate report index is intentionally selective. It currently parses 2016-2025 county Sales/Use taxable sales, FY22-FY25 Food Tax by Political Subdivision PDFs, 2024-2025 Working Family Tax Credit income-range PDFs, FY25-FY26 quarterly tax-credit report PDFs, a 2016 business-location report, vehicle counts as of 2017-12-31, licensed-driver totals as of 2024-11-14, dealer counts by county/type, and SIC location-count snapshots. Other DOR public reports, deeper tax-credit claim/customer records, and noncounty taxable-sales reports need their own parsers before the chatbot should give exact values for them. When DOR marks a food-tax cell suppressed because six or fewer businesses exist, the chatbot reports that suppression instead of estimating a value.

The MERIC LAUS labor index is also selective. It currently parses the public LAUS CSV route for the current selected release year, with seasonally adjusted statewide Missouri rows and not-seasonally-adjusted county rows. In the current local snapshot, statewide Missouri rows include January-April 2026 while county rows include January-March 2026. Wage, industry, occupation, projection, and regional-profile reports still need separate parsers.

The data.mo.gov catalog index is metadata-only. It can find dataset titles, themes, landing pages, and distribution links from the public DCAT catalog, but it does not parse every listed dataset into row-level or numeric answers.

The selected data.mo.gov education index is not a full DESE school-data parser. It currently covers two open-data tables: high-school senior counts and completed FAFSA application counts by school/year. The selected DESE School Directory parser adds district/school directory facts from the public School Directory by District PDF, including county, county-district code, MSIP, certified-staff count, enrollment, school/building count, school code, and grade span. The selected DESE assessment parser streams the 2025 public assessment aggregate CSV and keeps statewide plus selected district/school All Students performance-level rows; it does not save the raw 197 MB file, store student records, or cover every district/school row. The selected DESE APR ranking parser covers only the public 2025 lowest-5% APR ranking PDFs for LEA and school-building ranks and single-year APR percent scores. The selected DESE finance parser covers only three public 2025-2026 transfer PDFs: 7% transfer, 5% transfer, and transportation transfer. The selected DESE special-education incidence parser covers only statewide aggregate school-age child counts and incidence rates by disability category. The DESE School Data resource metadata parser can return cited public links for accountability/APR/MSIP, Core Data/MOSIS file layouts and code sets, school finance, assessment, and special-education resources. Full DESE MCDS dashboard numeric values, accountability calculations beyond the selected assessment/APR rows, detailed staff rows, budgets, audits, district profiles, and broader finance tables still need source-specific parsers before exact numeric answers should be given from those families.

The DESE School Directory PDF contains public contact/person fields, but this project intentionally does not store or return superintendent, principal, board member, phone, fax, email, or address fields from that source. The chatbot returns only public district/school directory facts needed for the case study.

The selected data.mo.gov health index is not a full DHSS public-health parser. It currently covers one aggregate table, Missouri Communicable Disease Report (2026), with current-week YTD counts, previous-week YTD counts, 5-year medians, rates per 100k, and rankings. The DHSS public-health resource metadata parser can return cited public links for county profiles, MOPHIMS/MICA, BRFSS, births/deaths, hospitalizations/PAS, county-level study, FOCUS reports, and surveillance dashboards. The selected DHSS BRFSS parser covers only the official front-page workbook of statewide aggregate prevalence values for 2018-2021, the selected DHSS vital-statistics parser covers only statewide Table 1 aggregate values from the 2023 Vital Statistics FOCUS PDF, and the selected DHSS MOPHIMS parser covers five default STATEWIDE / All demographic ProfileBuilder pages plus selected COUNTY leading-causes-of-death and inpatient-hospitalization rows for Boone, Cole, Greene, Jackson, St. Louis County, and St. Louis City. Exact all-county health profile values, broader MICA/PAS query values, county-level BRFSS values, respondent-level BRFSS data, county-level births/deaths, patient-level discharge records, race/demographic MOPHIMS slices, and other DHSS report values still need source-specific aggregate parsers and suppression checks. Health answers are source values only, not medical advice.

The selected data.mo.gov Profile of Hospitals index is a facility-profile lookup, not a care-quality or hospital-recommendation system. It can answer cited facility, region, and statewide licensed-bed/ICU-bed questions from 166 public rows. It does not return address, phone, fax, or administrator-name fields in chatbot answers or source-row previews, and it should not be used as medical advice, availability verification, or a quality ranking.

The selected DHSS WIC index is aggregate-only. The underlying public source contains household-level rows, but this project uses aggregate Socrata queries and stores only county and municipality summaries. It does not store or return household identifiers, applicant cities, ZIP codes, agency IDs, or raw household rows. WIC answers are descriptive public-data summaries, not eligibility, nutrition, medical, or benefits advice.

The selected data.mo.gov Food Pantry List index is a public directory snapshot. It can answer listed agency, county, city, public phone, public address, hours, and count questions, but it cannot verify current availability, eligibility rules, emergency service, nutrition advice, or which pantry is best for a specific person. Hours and contact details may be stale, so sourced answers include a call-ahead caveat.

The selected data.mo.gov Missouri Farmers' Markets index is a public directory snapshot. It can answer county counts, city lookups, listing/business lookups, public website/address fields, and top-county rankings, but it cannot verify live hours, product availability, whether a listing is currently operating, or which market is best. Contact-name and email fields from the source are suppressed.

The selected data.mo.gov LTC index is not a full long-term-care inspection or quality parser. It currently covers sanitized LTC Directory fields and aggregate LTC Census Report rows: facility name, city, county, region, capacity, level of care, license dates, certification, licensed homes, licensed beds, census, and occupancy. It does not store or return administrator names, phone numbers, mailing addresses, street addresses, inspection findings, complaints, survey findings, or medical/quality recommendations.

The selected DHSS LTC inspection metadata index is a resource/search-filter layer, not an inspection-result parser. It currently covers official Nursing Homes Inspected and Show Me Long Term Care pages, resource links, county/city search filters, scope/severity links, facility-type context, laws/regulations links, records-request links, and Nursing Home Compare guidance. It does not parse facility findings, complaint narratives, survey findings, addresses, quality ratings, or medical recommendations.

The selected DNR coverage is not a full DNR environmental or water-quality parser. It currently covers the Consumer Confidence Report public drinking-water system listing with PWSID, system name, and county; the data.mo.gov Oil and Gas Permits table with permit IDs, county, company/operator, lease/well, status, and permit-PDF links; the data.mo.gov Hazardous Waste Treatment, Storage and Disposal Facilities table with facility names, EPA IDs, county/status counts, and DNR regions; and 549 listing rows from the proposed 2024-2026 Section 303(d) listed-waters PDF for county, pollutant, waterbody, and high-priority TMDL questions. The separate DNR data/e-services resource metadata index can point to public links for water permits, MoCWIS, drinking-water tools, impaired waters, water-quality resources, GIS/map viewers, air-emissions tools, E-Start, WIMS, GeoSTRAT, energy data, forms, and public notices. It does not parse broader numeric water-quality values, broader permit families, emissions, broader waste-site/remediation values, geospatial layers, live advisories, drinking-water safety, recreation safety, oil/gas production, enforcement/compliance conclusions, medical guidance, or legal conclusions.

The selected MSDIS geospatial index is metadata-only. It currently covers MSDIS Open Data dataset metadata, ArcGIS REST feature/map/image service links, county-boundary resources, imagery services, LiDAR/elevation services, archive directories, and vector GIS links. It does not download feature rows, geometry, coordinates, shapefiles, geodatabases, imagery tiles, LiDAR point clouds, or service attributes, and it should not be treated as a geocoder or GIS analysis engine.

The selected MoDOT AADT index is not a full transportation, safety, road-closure, or geocoding parser. It currently covers latest-year directional AADT segment attributes from the official TrafficInfoSegAADT ArcGIS service. It can match routes, directions, highest-volume segments, and segment-description text, but it does not geocode addresses, parse real-time traffic/road closures, interpret crash risk, or mirror every MoDOT map/app value.

The selected Missouri Ethics Commission coverage has two layers. The public-resource metadata layer points to campaign-finance searches, Committee Contributions & Expenditures, lobbying searches/reports, commission actions, advisory opinions, forms, financial disclosure/PFD resources, and annual report links. The annual-report aggregate layer parses official Electronic Annual Report tables for 2017-2026 campaign-finance, lobbying, and PFD totals. It still does not download filing result rows, match named committees or lobbyists, parse donor rows, parse complaints, summarize enforcement findings, or draw political/legal conclusions.

The selected utility coverage is not a full Public Service Commission parser. It currently covers the Find A Missouri Utility city/county table with listed electric, gas, water, and telephone providers, PSC report-volume metadata/PDF links, and a capped selected PSC report-PDF text index for plain-English orientation and snippet search. PSC filings, rate cases, full annual-report PDF contents, staff positions, tariffs, legal conclusions, and full regulatory-order analysis still need separate parsers and careful labeling.

The selected agriculture coverage is not a full Missouri agriculture parser. It currently covers the Missouri Department of Agriculture feed sample testing results table with sample IDs, feed classes, brands, dates, and selected nutrient guarantee/result fields, plus Agricultural Market News report-link metadata for cattle/livestock, swine, sheep/goat, hay/forage, feedstuff, grain, regional markets, and USDA AMS report URLs. A capped selected document layer parses three official USDA AMS PDFs for Missouri hay price ranges, hay demand/supply context, selected Joplin feeder-cattle receipts, selected Joplin steer rows, special notes, and source snippets. It does not parse every live market-report PDF/dashboard, bid/offer feed, forecast, seed-testing source, inspection, complaint, or enforcement action.

The selected DHSS cannabis index is not a full cannabis-regulation parser. It currently covers sanitized non-contact fields from the verified dispensary locator and selected aggregate metrics extracted from PY22-PY24 annual-report PDFs. It does not store or return phone numbers, street addresses, websites, or coordinates from the public locator. Live Tableau dashboards, transfer history, inspections, item approvals, product/regulatory updates, and legal compliance interpretation still need separate parsers and careful labeling.

The selected DESE child-care dashboard index is not a provider lookup or child-care recommendation system. It currently covers quarterly aggregate dashboard PDF values for slots, pending facilities, inspections, complaint investigations, facility type counts, and licensing-time percentages. Provider-level search records, inspection findings, complaint narratives, addresses, phone numbers, quality conclusions, and licensing recommendations still need separate parsers and careful labeling.

The Missouri State Auditor metadata index covers report numbers, titles, release dates, official report-page links, PDF links, and simple title-topic inference. A separate selected document-text index downloads a capped local sample of official report PDFs and can provide plain-English orientation from extracted recommendation snippets, such as for report 2026-044. It is not a complete audit archive, does not compare entities, does not make legal/accountability conclusions, and does not replace the official report wording.

The SOS election-return index is selected. It currently covers three official statewide election-return PDFs: 2024 General, 2024 Primary, and 2022 General. It also parses the official 2024 General Election county-results PDF for selected President/Governor county candidate rows and the official 2024 General Election voter-turnout PDF for county/jurisdiction turnout aggregates. It can answer supported statewide winner, candidate vote, percentage, total-vote, primary party-winner, selected county winner/vote, and 2024 turnout questions, but it does not parse precinct files, voter files, broader county contests, registered-voter history pages, ballot-measure pages, or candidate-filing pages.

The OA Budget and Planning metadata index covers official page/link records for executive budgets, budget summaries, revenue releases/detail file links, performance-measure resources, demographic resources, and redistricting resources. A separate selected OA General Revenue Detail index parses 10 FY 2026 monthly Excel workbooks into 210 aggregate revenue/refund line items, including monthly amounts, percent changes, and fiscal year-to-date amounts. It does not parse older final-year PDF details, budget-book PDFs, redistricting documents, appropriations, taxpayer records, forecasts, or enacted/proposed budget policy meaning.

## Local Hardware Scope

The project is tuned for an RTX 3060 Ti 8 GB GPU. Larger models, longer context, or bigger batches may not fit safely.

## No Production Guarantee

The model should not be used for procurement, employment, legal, financial, or policy decisions. It is a learning artifact.
