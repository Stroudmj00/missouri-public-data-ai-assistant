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
- Chatbot behavior suite: 26 adversarial, citation, row-preview, and public-data routing cases

Run 001 remains the historical before/after comparison for the first LoRA experiment. Run 002 is the current runtime and data-coverage iteration.
