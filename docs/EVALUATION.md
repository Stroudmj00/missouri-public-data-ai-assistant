# Evaluation Plan

## Evaluation Set

Fixed prompts live in:

```text
data/eval/evaluation_prompts.jsonl
```

Each prompt includes question, short sanitized context, expected answer, source, and answer type.

## Completed Comparison

- Base model: `HuggingFaceTB/SmolLM2-135M-Instruct`
- Fine-tuned adapter: `checkpoints\smollm2_135m_lora_run_001`
- Prompt count: 20
- Base pass rate: 18 / 20 (90.00%)
- Fine-tuned pass rate: 18 / 20 (90.00%)

Full results:

- `reports/evaluation_comparison.md`
- `reports/evaluation_comparison.csv`
- `reports/base_eval_outputs.jsonl`
- `reports/finetuned_outputs.jsonl`

## Metrics

- Numeric token overlap for aggregate numeric answers
- Normalized substring match for short factual answers
- Refusal/unknown phrase check for excluded data requests
- Runtime
- Peak allocated VRAM

## Interpretation

This is a small portfolio case-study evaluation. It is useful for showing reproducibility, model behavior, and iteration discipline, but it is not a broad benchmark.

## Current Runtime Layer

The canonical local chatbot runtime uses the run 002 MAP-expanded artifacts and deterministic MAP lookup:

- Adapter reference: `checkpoints\smollm2_135m_lora_run_002`
- Training rows: 304
- Eval rows: 40
- MAP local index: 104 text files and 6,123,427 parsed rows
- Public source-page index: 18 source families connected
- data.mo.gov catalog metadata index: 277 dataset records with cited theme/search/distribution-link answers
- data.mo.gov education index: 2 selected public education datasets and 14,123 parsed school/year rows
- DESE School Data resource metadata index: 382 public resource links across 8 official source pages
- DESE School Directory index: 489 district rows and 2,433 school/building rows from the public School Directory by District PDF
- data.mo.gov health index: 1 selected aggregate public-health dataset and 52 disease/condition rows
- DHSS public-health resource metadata index: 285 public resource links across 9 official source pages
- DHSS WIC aggregate index: 86,044 public source household rows summarized into 115 county and 224 municipality aggregate rows
- data.mo.gov LTC index: 1,101 sanitized directory rows, 986 unique facility numbers, 114 counties, and 47 aggregate census rows
- data.mo.gov DNR water index: 1 selected public drinking-water dataset and 1,425 system rows
- data.mo.gov utility index: 1 selected city/county utility-provider dataset and 1,718 rows
- PSC report metadata index: 27 official report PDF links, covering 1997-2023
- data.mo.gov agriculture index: 1 selected public feed sample testing dataset and 8,388 rows
- Agricultural Market News metadata index: 77 report/resource links, including 71 PDF links, across 8 category groups
- DHSS cannabis index: 223 verified dispensary records, 6 annual report links, and 3 selected annual-report PDFs parsed for PY22-PY24 aggregate metrics
- DESE child-care dashboard index: 5 quarterly dashboard PDFs parsed for aggregate slots, facilities, inspections, complaints, and licensing-time metrics
- Missouri State Auditor metadata index: 3,447 report metadata rows for 1999-2026
- SOS election returns index: 3 official statewide election-return PDFs, 782 contests, and 1,604 candidate/ballot rows
- OA Budget metadata index: 114 official page/link records across 5 Budget and Planning pages
- MSHP crash aggregate index: 9 official Excel files and 540 metric-year records
- DOR aggregate report index: 7 official public report files and 38,451 parsed aggregate records
- MERIC LAUS labor index: 25 official CSV downloads and 353 parsed aggregate records
- Chatbot behavior suite: 154 adversarial, citation, row-preview, aggregate-ranking, crash-statistic, DOR aggregate, MERIC labor-market, Missouri State Auditor metadata, SOS election returns, PSC report metadata, OA Budget metadata, Agricultural Market News metadata, DESE School Data resource metadata, DHSS public-health resource metadata, data.mo.gov catalog, data.mo.gov education, DESE School Directory, data.mo.gov health, DHSS WIC aggregate, data.mo.gov LTC directory/census, data.mo.gov DNR water, data.mo.gov utility, data.mo.gov agriculture, DHSS cannabis, DESE child-care dashboards, and public-data routing cases

Run 001 remains the historical before/after comparison for the first LoRA experiment. Run 002 is the current runtime and data-coverage iteration.
