# Provider And Historical Model Card

## Current Answer Engine

The current answer engine is provider-backed Deep Answer Mode:

- default provider: Vertex AI Gemini 3 Flash
- default model id: `gemini-3-flash-preview`
- local fallback: deterministic evidence output with `deep_answer_status: unavailable_fallback`
- test providers: fake and unavailable providers in `src/missouri_public_data_ai/deep_answer.py`

The provider receives a compact evidence bundle from local tools. It should answer only from supplied Missouri public-data evidence.

The optional legacy local-synthesis settings still point to the SmolLM2 LoRA run for reproducibility and comparison. They are not the normal answer strategy when Deep Answer Mode is enabled.

## Local Evidence Layer

Exact facts come from local code:

- deterministic lookup for exact public records
- source-family routing
- citation metadata
- capped source-row previews
- privacy and unsupported-scope guardrails
- local verification metadata

## Historical Local Model Experiments

The repo keeps historical LoRA runs because they explain the project pivot:

- `HuggingFaceTB/SmolLM2-135M-Instruct`
- `Qwen/Qwen2.5-1.5B-Instruct`

The Qwen run 003 adapter was trained on generated aggregate/source Missouri public-data QA pairs:

- training rows: 304
- max optimizer steps: 120
- trainable parameters: 1,089,536
- peak allocated VRAM: 3811.43 MB
- adapter path: `checkpoints\qwen2_5_1_5b_lora_run_003`

These local models are not the main runtime answer engine.

## Intended Use

Educational and portfolio case study for source-grounded public-data assistance over selected Missouri public records.

## Out Of Scope

- official State of Missouri use
- production public-finance assistant
- legal, procurement, financial, employment, medical, or policy advice
- model-memory lookup for exact employee salary, vendor payment, customer tax-credit, or other row-level records

## Evaluation

Current runtime evaluation is in:

- `reports/assistant_behavior_test_results.json`
- `reports/source_usefulness_probe.json`
- `docs/EVALUATION.md`
