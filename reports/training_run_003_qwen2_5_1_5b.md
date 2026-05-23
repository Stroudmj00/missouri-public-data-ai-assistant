# Training Run 003: Qwen2.5 1.5B

Generated at: `2026-05-23T04:39:23+00:00`

## Scope

This was a conservative LoRA fine-tuning run for the Missouri Tiny LLM case study. It trained only adapter weights on generated aggregate/source QA pairs.

## Configuration

- Base model: `Qwen/Qwen2.5-1.5B-Instruct`
- Config: `configs\finetune_qwen2_5_1_5b_lora_run_003.yaml`
- Adapter output: `checkpoints\qwen2_5_1_5b_lora_run_003`
- Training rows: 304
- Tokenized training examples: 304
- Max optimizer steps: 120
- Trainable parameters: 1,089,536 / 1,544,803,840 (0.0705%)

## Resource Usage

- Runtime: 322.274 seconds
- Peak allocated VRAM: 3811.43 MB
- Adapter size: 15.072 MB
- Loss chart: `reports\training_run_003_qwen2_5_1_5b_loss.png`
- Metrics CSV: `reports\training_run_003_qwen2_5_1_5b_metrics.csv`

## Safety Boundary

- Input data was `data/qa/train_map_run_002.jsonl`
- Exact employee, vendor, customer, and other row-level public-record answers are handled by deterministic lookup
- Raw row-level records were not used as model memorization targets
- Raw public downloads remain ignored from Git

## Interpretation

This run is intentionally small. It is meant to prove the full training/evaluation loop and create a measured comparison point, not to produce a production assistant.
