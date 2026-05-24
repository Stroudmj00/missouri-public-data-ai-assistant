# Powerful Chatbot Upgrade

## Model Choice

Kimi K2 is not a local fine-tune target for this machine. Moonshot's public Kimi K2 repo describes the model as a 1T-parameter mixture-of-experts system with 32B activated parameters, which is far beyond an RTX 3060 Ti with 8 GB VRAM.

Gemma is a better family for this hardware, but the Hugging Face Gemma 3 repositories are gated. The current environment is not authenticated for `google/gemma-3-1b-it`, so direct download fails with a gated-repo 401 until a Hugging Face account accepts the Gemma terms and logs in locally.

The no-blocker local upgrade path is:

1. Use `Qwen/Qwen2.5-1.5B-Instruct` as the accessible stronger local model.
2. Keep exact Missouri public facts in SQLite deterministic lookup.
3. Fine-tune a small LoRA adapter on the generated Missouri public-data QA rows.
4. Use the stronger model only for grounded answer synthesis over cited lookup results.

## What Changed

- Added optional local answer synthesis to the chatbot runtime.
- The deterministic lookup answer remains the source of truth.
- Synthesis is opt-in with `--synthesis local`.
- Added a narrow sourced Missouri civic-facts fallback for basic officeholder questions, starting with the current governor.
- Added a stronger local LoRA config: `configs/finetune_qwen2_5_1_5b_lora_run_003.yaml`.
- Added a Gemma-ready config: `configs/finetune_gemma3_1b_lora_run_003.yaml`.

## Completed Run 003

- Model: `Qwen/Qwen2.5-1.5B-Instruct`
- Training rows: 304
- Eval rows: 40
- Max optimizer steps: 120
- Trainable parameters: 1,089,536
- Adapter size: 15.072 MB
- Runtime: 322.274 seconds
- Peak allocated VRAM: 3811.43 MB
- Adapter path: `checkpoints/qwen2_5_1_5b_lora_run_003`

## Train The Accessible Stronger Model

```powershell
.\.venv\Scripts\python scripts\finetune_lora.py --config configs\finetune_qwen2_5_1_5b_lora_run_003.yaml
```

## Start The More Conversational Runtime

```powershell
.\.venv\Scripts\python scripts\serve_ui.py `
  --port 7860 `
  --model-id Qwen/Qwen2.5-1.5B-Instruct `
  --adapter-path checkpoints/qwen2_5_1_5b_lora_run_003 `
  --synthesis local `
  --synthesis-max-new-tokens 160
```

## Gemma Path After Authentication

```powershell
huggingface-cli login
.\.venv\Scripts\python scripts\finetune_lora.py --config configs\finetune_gemma3_1b_lora_run_003.yaml
```

Then run:

```powershell
.\.venv\Scripts\python scripts\serve_ui.py `
  --port 7860 `
  --model-id google/gemma-3-1b-it `
  --adapter-path checkpoints/gemma3_1b_lora_run_003 `
  --synthesis local
```

## Why This Is More Powerful

The earlier app mostly returned exact templated answers. The upgraded app can use a stronger local instruction model to rewrite cited lookup results into more natural answers while preserving the public-data boundary. It also handles a small set of sourced Missouri civic facts that users reasonably expect from a Missouri chatbot. This keeps the most important property of the system intact: exact facts come from reproducible public-data queries or cited public facts, not unsupported model memory.
