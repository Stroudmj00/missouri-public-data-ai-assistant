# Portfolio Summary

## Short Description

Built a reproducible tiny-LLM case study using public Missouri finance, health, DHSS public-health, BRFSS, vital-statistics, MOPHIMS statewide and selected county profile aggregates, and long-term-care resource metadata, education, transportation, ethics/campaign-finance resource, elections, utility, PSC report metadata and capped report-PDF text, OA Budget, OA General Revenue Detail, agriculture and selected Agricultural Market News report PDFs, cannabis-regulation, child-care, and school-data resource datasets, with a CUDA-enabled local training environment, aggregate QA generation, baseline evaluation, LoRA fine-tuning, deterministic lookup for indexed public records, and documented data boundaries.

## What It Shows

- Local ML environment setup on consumer hardware
- Public-data ingestion with download/runtime/storage estimates
- Source-scoped public-data handling for public-sector records
- Tiny-model baseline testing
- LoRA fine-tuning on a small QA set
- Deterministic lookup for exact indexed public records such as MAP totals, contracts, election returns, MoDOT AADT route segments, MEC public-resource links and annual-report aggregate rows, utility providers, DESE School Data resource links, DESE APR ranking rows, selected DESE finance transfer rows, selected DESE special-education incidence rows, DHSS public-health resource links, DHSS BRFSS statewide prevalence rows, DHSS statewide vital-statistics rows, DHSS MOPHIMS statewide plus selected county leading-causes-of-death and inpatient-hospitalization profile rows, DHSS LTC inspection resource/search-filter metadata, PSC report metadata and selected report-PDF snippets, OA Budget metadata, OA General Revenue Detail workbook values, Agricultural Market News report links and selected PDF values, sourced civic facts, and selected cannabis-regulation facts
- Before/after evaluation with both improvement and regression documented
- Honest limitation reporting

## Key Result

The first LoRA adapter matched the base model on the 20-prompt evaluation set: 18 / 20 for both. It improved one numeric MAP answer, regressed on one hospital-bed answer, and failed the employee-salary prompt from the original refusal framing.

The value of the project is not that the first adapter won. The value is the complete reproducible workflow: source safety, local constraints, training, evaluation, and honest reporting.

## Resume Bullet Options

- Built a local tiny-LLM case study using public Missouri datasets, CUDA PyTorch, Hugging Face Transformers, and LoRA fine-tuning, with reproducible data ingestion, evaluation, and resource reporting.
- Designed a public-data QA pipeline that converts Missouri Accountability Portal and `data.mo.gov` sources into aggregate training/evaluation examples, while routing exact MAP public-record questions through source-backed lookup instead of model memorization.
- Benchmarked a small instruction model before and after LoRA fine-tuning on 20 fixed prompts, documenting equal headline performance, one improvement, one regression, and remaining refusal-behavior gaps.

## Interview Story

Situation:

I wanted a public applied-AI portfolio project that used Missouri public data without exposing internal work material and without pretending a tiny model could reliably memorize exact public records.

Task:

Build a tiny local model workflow that could answer simple public-data questions, use lookup for exact MAP records, and clearly document whether fine-tuning helped.

Action:

I created a safe ingestion pipeline, generated sanitized QA pairs, ran a no-training baseline, trained a small LoRA adapter on an RTX 3060 Ti, and compared the base and fine-tuned model on the same fixed prompts.

Result:

The full workflow ran locally with peak training VRAM around 619 MB. The fine-tuned adapter matched the base model at 18 / 20, improved one numeric answer, regressed on one prompt, and exposed refusal behavior as the next improvement target.

## GitHub Repo Description

Tiny local LLM case study using public Missouri datasets, sanitized aggregate QA generation, LoRA fine-tuning, and before/after evaluation on consumer GPU hardware.
