# Portfolio Summary

## Short Description

Built the Missouri Public Data AI Assistant, a source-grounded public-data assistant using indexed Missouri finance, health, education, transportation, ethics, elections, utility, PSC, OA Budget, agriculture, cannabis-regulation, child-care, and school-data sources. The project combines controlled local evidence tools, Vertex AI Gemini deep-answer synthesis, deterministic lookup, route/ranking diagnostics, citations, guardrails, provider fallback, aggregate QA generation, baseline evaluation, historical LoRA fine-tuning, and documented data boundaries.

## What It Shows

- Source-grounded assistant architecture
- Public-data ingestion with download/runtime/storage estimates
- Source-scoped public-data handling for public-sector records
- Vertex AI Gemini provider integration with no-secret environment configuration
- Fake and unavailable providers for credential-free test coverage
- Historical local-model baseline testing and LoRA fine-tuning on a small QA set
- Deterministic lookup for exact indexed public records such as MAP totals, contracts, election returns, MoDOT AADT route segments, MEC public-resource links and annual-report aggregate rows, utility providers, DESE School Data resource links, selected DESE assessment aggregate rows, DESE APR ranking rows, selected DESE finance transfer rows, selected DESE special-education incidence rows, DHSS public-health resource links, DHSS BRFSS statewide prevalence rows, DHSS statewide and county vital-statistics rows, DHSS MOPHIMS statewide plus selected county leading-causes-of-death and inpatient-hospitalization profile rows, DHSS LTC inspection resource/search-filter metadata, PSC report metadata and selected report-PDF snippets, OA Budget metadata, OA General Revenue Detail workbook values, Agricultural Market News report links and selected PDF values, sourced civic facts, and selected cannabis-regulation facts
- Common routing metadata for reviewer audits: source family, evidence type, retrieval path, routing confidence, guardrail reason, and ranked candidate routes
- Deep Answer Mode metadata for reviewer audits: evidence-tool calls, evidence hits, evidence bundle ids, provider status, confidence, limitations, and local verification
- Before/after local-model evaluation with both improvement and regression documented
- Honest limitation reporting

## Key Result

The first LoRA adapter matched the base model on the 20-prompt evaluation set: 18 / 20 for both. It improved one numeric MAP answer, regressed on one hospital-bed answer, and failed the employee-salary prompt from the original refusal framing.

The value of the project is not that the first adapter won. The value is the complete reproducible workflow and architecture pivot: source safety, local evidence tools, provider-backed synthesis, evaluation, fallback behavior, and honest reporting.

## Resume Bullet Options

- Built the Missouri Public Data AI Assistant, a source-grounded assistant that retrieves indexed Missouri public-record evidence through controlled local tools and uses Vertex AI Gemini synthesis with citation and guardrail checks.
- Designed a public-data evidence pipeline that converts Missouri Accountability Portal, `data.mo.gov`, DESE, DHSS, DOR, MERIC, MoDOT, PSC, SOS, and related sources into cited lookup, ranking, comparison, and source-discovery tools instead of relying on model memorization.
- Added provider-agnostic Deep Answer Mode with Vertex AI Gemini as the default provider, fake/unavailable providers for tests, and fallback metadata when cloud credentials are missing.

## Interview Story

Situation:

I wanted a public applied-AI portfolio project that used Missouri public data without exposing internal work material and without pretending a local model could reliably memorize exact public records.

Task:

Build a useful public-data assistant that retrieves evidence locally, uses a stronger cloud model only over supplied evidence, and clearly documents the earlier fine-tuning result as historical context.

Action:

I created a safe ingestion pipeline, generated sanitized QA pairs, ran a no-training baseline, trained a small LoRA adapter on an RTX 3060 Ti, compared the base and fine-tuned model on fixed prompts, then shifted the runtime architecture to controlled evidence tools plus Vertex AI Gemini synthesis and local verification.

Result:

The full historical training workflow ran locally with peak training VRAM around 619 MB. The runtime assistant now passes 330 behavior cases and 44 source-usefulness probes while exposing provider fallback, evidence-tool calls, generalized evidence hits, citations, confidence, limitations, and guardrail metadata.

## GitHub Repo Description

Source-grounded Missouri Public Data AI Assistant with local evidence tools, Vertex AI Gemini synthesis, citations, guardrails, provider fallback, and historical local-LLM evaluation.
