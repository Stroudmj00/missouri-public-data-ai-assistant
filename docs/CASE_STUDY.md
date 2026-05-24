# Case Study

## Question

Can a consumer desktop support a credible tiny-LLM workflow for simple public-data questions?

## Final Answer For This Version

Yes, for a constrained case study. The project now builds a safe public-data ingestion pipeline, generates sanitized aggregate QA pairs, runs a no-training baseline, fine-tunes a small LoRA adapter, compares the base and fine-tuned models on fixed evaluation prompts, and serves exact public-record answers through a deterministic local lookup index.

## Public-Data Twist

The project uses public Missouri sources:

- Missouri Accountability Portal public downloads, including expenditures, employee pay, tax credits, federal grants, budget restrictions, bonds, stimulus, and check cancellations
- data.mo.gov Profile of Hospitals
- data.mo.gov LTC Census Report
- Missouri Department of Revenue public aggregate reports for taxable sales, business locations, vehicles, licensed drivers, dealers, and SIC location counts
- MERIC Local Area Unemployment Statistics public CSV downloads for current Missouri and county labor-market metrics
- State of Missouri `data.mo.gov` DCAT catalog metadata for dataset search, themes, landing pages, and distribution links
- Selected `data.mo.gov` education datasets for high-school senior counts and completed FAFSA application counts by school/year
- Selected DESE School Directory public PDF for district county, MSIP, enrollment, school/building count, school code, and grade-span lookup
- Selected `data.mo.gov` public-health aggregate data for communicable-disease YTD counts, rates per 100k, 5-year median comparisons, and rankings
- Selected DHSS WIC aggregate data for SFY 2025 county and municipality household-row counts and redeemed net-benefit totals
- Selected `data.mo.gov` LTC Directory and LTC Census Report data for sanitized facility capacity facts and aggregate occupancy
- Selected `data.mo.gov` DNR water data for public drinking-water system counts, PWSID lookup, and county rankings
- Selected `data.mo.gov` utility data for city/county electric, gas, water, and telephone provider lookup
- Missouri Public Service Commission report metadata for report-volume, covered-period, year-to-volume, and PDF-link lookup
- Selected `data.mo.gov` agriculture feed sample testing data for sample IDs, feed class counts/rankings, and nutrient guarantee/result lookup
- Selected DHSS cannabis regulation data for verified dispensary counts/lookups and PY22-PY24 annual-report sales, tax, transfer, microbusiness, agent-card, and operating-facility metrics
- Selected DESE child-care dashboard PDFs for quarterly aggregate slots, pending facilities, inspections, complaint investigations, facility type counts, and licensing-time percentages
- Missouri State Auditor report search metadata for report numbers, titles, release dates, official report pages, and PDF links
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
- Chatbot behavior suite: adversarial, citation, row-preview, aggregate-ranking, crash-statistic, DOR aggregate, MERIC labor-market, Missouri State Auditor metadata, SOS election-return, PSC report metadata, data.mo.gov catalog, data.mo.gov education, DESE School Directory, data.mo.gov health, DHSS WIC aggregate, data.mo.gov LTC directory/census, data.mo.gov DNR water, data.mo.gov utility, data.mo.gov agriculture, DHSS cannabis, DESE child-care dashboards, and public-data routing cases passed
- Public source-page index: 18 Missouri source families connected for cited source-discovery answers
- MSHP crash aggregate index: 9 official SAC Excel files and 540 metric-year records parsed locally
- DOR aggregate report index: 7 official public report files and 38,451 aggregate records parsed locally
- MERIC LAUS labor index: 25 official CSV downloads and 353 aggregate records parsed locally
- data.mo.gov catalog metadata index: 277 dataset records, 272 with distributions, 255 CSV links, and 255 JSON links
- data.mo.gov education index: 2 selected public education datasets and 14,123 parsed school/year rows
- DESE School Directory index: 489 district rows and 2,433 school/building rows parsed from a 3.4 MB public PDF
- data.mo.gov health index: 1 selected aggregate public-health dataset and 52 disease/condition rows
- DHSS WIC aggregate index: 86,044 public source household rows summarized into 115 county and 224 municipality aggregate rows
- data.mo.gov LTC index: 1,101 sanitized directory rows, 986 unique facility numbers, 114 counties, and 47 aggregate census rows
- data.mo.gov DNR water index: 1 selected public drinking-water dataset and 1,425 system rows
- data.mo.gov utility index: 1 selected city/county utility-provider dataset and 1,718 rows
- PSC report metadata index: 27 official report PDF links, covering 1997-2023
- data.mo.gov agriculture index: 1 selected public feed sample testing dataset and 8,388 rows
- DHSS cannabis index: 223 verified dispensary records across 57 counties and 3 selected annual-report PDFs parsed for PY22-PY24 aggregate metrics
- DESE child-care dashboard index: 5 quarterly dashboard PDFs parsed for aggregate slots, facilities, inspections, complaints, and licensing-time metrics
- Missouri State Auditor metadata index: 3,447 report metadata rows for 1999-2026
- SOS election returns index: 3 official statewide election-return PDFs, 782 contests, and 1,604 candidate/ballot rows

This is a credible case-study outcome because it preserves the negative result. The first fine-tune proved the local training loop and produced measurable behavior, but it did not improve the headline metric. The UI now makes the more practical architecture explicit: use the tiny model for simple QA over curated context, and use deterministic lookup for exact public records. The chatbot layer now treats exact MAP, MSHP, DOR, MERIC LAUS, Missouri State Auditor metadata, SOS election-return rows, PSC report metadata, data.mo.gov catalog, selected education, selected DESE School Directory, selected aggregate public-health, selected DHSS WIC aggregate, selected LTC directory/census, selected DNR water, selected utility-provider, selected agriculture feed-sample, selected cannabis regulation, and selected child-care dashboard questions as source-backed lookups with guardrails for unsupported years, list-all prompts, private identifiers, vendor IDs, reversed payment direction, and reports that have not been parsed yet. Each API response now carries a request id, retrieval path, dataset snapshot id, source-file citations, and capped non-person row previews so a user can see what local public-data snapshot supported the answer.

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
