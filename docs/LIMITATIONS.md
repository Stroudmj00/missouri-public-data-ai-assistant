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

The MSHP aggregate crash-statistics index uses the official Excel files currently exposed by the Statistical Analysis Center page. The parsed crash files are small and useful, but their year coverage varies by file and currently tops out at 2014 in the indexed official files.

The DOR aggregate report index is intentionally selective. It currently parses 2025 county Sales/Use taxable sales, a 2016 business-location report, vehicle counts as of 2017-12-31, licensed-driver totals as of 2024-11-14, dealer counts by county/type, and SIC location-count snapshots. Other DOR public reports, PDFs, suppressed cells, and historical taxable-sales years need their own parsers before the chatbot should give exact values for them.

The MERIC LAUS labor index is also selective. It currently parses the public LAUS CSV route for the current selected release year, with seasonally adjusted statewide Missouri rows and not-seasonally-adjusted county rows. In the current local snapshot, statewide Missouri rows include January-April 2026 while county rows include January-March 2026. Wage, industry, occupation, projection, and regional-profile reports still need separate parsers.

The data.mo.gov catalog index is metadata-only. It can find dataset titles, themes, landing pages, and distribution links from the public DCAT catalog, but it does not parse every listed dataset into row-level or numeric answers.

The selected data.mo.gov education index is not a full DESE school-data parser. It currently covers two open-data tables: high-school senior counts and completed FAFSA application counts by school/year. The selected DESE School Directory parser adds district/school directory facts from the public School Directory by District PDF, including county, county-district code, MSIP, enrollment, school/building count, school code, and grade span. DESE accountability, assessment, staff, and finance report surfaces still need source-specific parsers before exact answers should be given from those families.

The DESE School Directory PDF contains public contact/person fields, but this project intentionally does not store or return superintendent, principal, board member, phone, fax, email, or address fields from that source. The chatbot returns only public district/school directory facts needed for the case study.

The selected data.mo.gov health index is not a full DHSS public-health parser. It currently covers one aggregate table, Missouri Communicable Disease Report (2026), with current-week YTD counts, previous-week YTD counts, 5-year medians, rates per 100k, and rankings. County health profiles, MICA, births/deaths, hospitalizations, BRFSS, and facility-level health sources still need source-specific parsers and suppression checks. Health answers are source values only, not medical advice.

The selected DHSS WIC index is aggregate-only. The underlying public source contains household-level rows, but this project uses aggregate Socrata queries and stores only county and municipality summaries. It does not store or return household identifiers, applicant cities, ZIP codes, agency IDs, or raw household rows. WIC answers are descriptive public-data summaries, not eligibility, nutrition, medical, or benefits advice.

The selected data.mo.gov LTC index is not a full long-term-care inspection or quality parser. It currently covers sanitized LTC Directory fields and aggregate LTC Census Report rows: facility name, city, county, region, capacity, level of care, license dates, certification, licensed homes, licensed beds, census, and occupancy. It does not store or return administrator names, phone numbers, mailing addresses, street addresses, inspection findings, complaints, survey findings, or medical/quality recommendations.

The selected data.mo.gov DNR water index is not a full DNR environmental or water-quality parser. It currently covers the Consumer Confidence Report public drinking-water system listing with PWSID, system name, and county. Water permits, impaired waters, water-quality standards, environmental GIS layers, and detailed Consumer Confidence Report documents still need separate parsers before exact answers should be given from those families.

The selected data.mo.gov utility index is not a full Public Service Commission parser. It currently covers the Find A Missouri Utility city/county table with listed electric, gas, water, and telephone providers. PSC filings, rate cases, annual reports, staff positions, orders, tariffs, and legal/regulatory decisions still need separate parsers and careful labeling.

The selected data.mo.gov agriculture index is not a full Missouri agriculture parser. It currently covers the Missouri Department of Agriculture feed sample testing results table with sample IDs, feed classes, brands, dates, and selected nutrient guarantee/result fields. Agricultural market reports, seed testing, inspections, complaints, enforcement actions, and USDA-linked market reports still need separate parsers before exact answers should be given from those families.

The selected DHSS cannabis index is not a full cannabis-regulation parser. It currently covers sanitized non-contact fields from the verified dispensary locator and selected aggregate metrics extracted from PY22-PY24 annual-report PDFs. It does not store or return phone numbers, street addresses, websites, or coordinates from the public locator. Live Tableau dashboards, transfer history, inspections, item approvals, product/regulatory updates, and legal compliance interpretation still need separate parsers and careful labeling.

The Missouri State Auditor index is metadata-only. It currently covers report numbers, titles, release dates, official report-page links, PDF links, and simple title-topic inference. It does not download report PDFs, summarize findings, compare entities, make legal/accountability conclusions, or explain audit findings beyond pointing to official source documents. A future document parser should cap PDF downloads and preserve report dates, audited entities, and report context.

The SOS election-return index is selected and statewide-only. It currently covers three official statewide election-return PDFs: 2024 General, 2024 Primary, and 2022 General. It can answer supported winner, candidate vote, percentage, total-vote, and primary party-winner questions from those PDFs, but it does not parse county result tables, precinct files, voter files, registered-voter pages, turnout pages, ballot-measure pages, or candidate-filing pages.

## Local Hardware Scope

The project is tuned for an RTX 3060 Ti 8 GB GPU. Larger models, longer context, or bigger batches may not fit safely.

## No Production Guarantee

The model should not be used for procurement, employment, legal, financial, or policy decisions. It is a learning artifact.
