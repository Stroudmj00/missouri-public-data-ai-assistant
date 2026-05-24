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
- Chatbot behavior suite: 66 adversarial, citation, row-preview, aggregate-ranking, crash-statistic, DOR aggregate, MERIC labor-market, and public-data routing cases passed
- Public source-page index: 18 Missouri source families connected for cited source-discovery answers
- MSHP crash aggregate index: 9 official SAC Excel files and 540 metric-year records parsed locally
- DOR aggregate report index: 7 official public report files and 38,451 aggregate records parsed locally
- MERIC LAUS labor index: 25 official CSV downloads and 353 aggregate records parsed locally

This is a credible case-study outcome because it preserves the negative result. The first fine-tune proved the local training loop and produced measurable behavior, but it did not improve the headline metric. The UI now makes the more practical architecture explicit: use the tiny model for simple QA over curated context, and use deterministic lookup for exact public records. The chatbot layer now treats exact MAP, MSHP, DOR, and MERIC LAUS questions as source-backed lookups with guardrails for unsupported years, list-all prompts, private identifiers, vendor IDs, reversed payment direction, and reports that have not been parsed yet. Each API response now carries a request id, retrieval path, dataset snapshot id, source-file citations, and capped non-person row previews so a user can see what local public-data snapshot supported the answer.

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
