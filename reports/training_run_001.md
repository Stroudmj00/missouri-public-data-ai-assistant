# Training Run 001

Generated at: `2026-05-23T03:27:01+00:00`

## Scope

This was a conservative LoRA fine-tuning run for the Missouri Tiny LLM case study. It trained only adapter weights on generated aggregate/source QA pairs.

## Configuration

- Base model: `HuggingFaceTB/SmolLM2-135M-Instruct`
- Config: `configs\finetune_smollm2_135m_lora.yaml`
- Adapter output: `checkpoints\smollm2_135m_lora_run_001`
- Training rows: 100
- Tokenized training examples: 100
- Max optimizer steps: 120
- Trainable parameters: 460,800 / 134,975,808 (0.3414%)

## Resource Usage

- Runtime: 54.774 seconds
- Peak allocated VRAM: 619.14 MB
- Adapter size: 5.139 MB
- Loss chart: `reports\training_run_001_loss.png`
- Metrics CSV: `reports\training_run_001_metrics.csv`

## Safety Boundary

- Input data was `data/qa/train.jsonl`
- Exact employee, vendor, customer, and other row-level public-record answers are handled by deterministic lookup
- Raw row-level records were not used as model memorization targets
- Raw public downloads remain ignored from Git

## Interpretation

This run is intentionally small. It is meant to prove the full training/evaluation loop and create a measured comparison point, not to produce a production assistant.
