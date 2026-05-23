# Model Card

## Current Model State

The project now has a small LoRA adapter trained on generated aggregate/source Missouri public-data QA pairs.

## Base Model

`Qwen/Qwen2.5-1.5B-Instruct`

## Adapter

- Adapter path: `checkpoints\qwen2_5_1_5b_lora_run_003`
- Adapter size: 15.072 MB
- Training rows: 304
- Max optimizer steps: 120
- Trainable parameters: 1,089,536 (0.0705% of total)
- Peak allocated VRAM during training: 3811.43 MB

## Intended Use

Educational case study for constrained QA over retrieved public-data snippets. Exact row-level MAP public records are answered by deterministic lookup over the local public index.

## Out Of Scope

- Production public-finance assistant
- Legal, procurement, financial, or employment advice
- Model-memory lookup for exact employee salary, vendor payment, customer tax-credit, or other row-level records
- State of Missouri endorsement or official representation

## Data Boundary

Training used `data/qa/train_map_run_002.jsonl`. It did not train on raw MAP rows as memorization targets. The local UI uses `data/raw_public/map_public_lookup.sqlite` for exact public-record lookup.

## Evaluation

See `reports/evaluation_comparison.md` after running the before/after evaluation.
