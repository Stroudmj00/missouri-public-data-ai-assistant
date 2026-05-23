# Limitations

## Not An Official Tool

This is an independent educational case study. It is not endorsed by, operated by, or representative of the State of Missouri.

## Small Evaluation Set

The final comparison uses 20 fixed prompts. That is enough for a portfolio case study, but not enough for a robust model-quality claim.

## Generated QA Templates

The QA set is generated from aggregate summaries. This makes the experiment reproducible, but it also means the task is narrow and partly template-like.

## First Fine-Tune Did Not Improve The Headline Metric

The LoRA adapter matched the base model at 18 / 20. It improved one prompt, regressed on one prompt, and failed the same refusal prompt as the base model.

## Refusal Behavior Needs Work

Both models failed the employee-salary prompt in the final evaluation when that prompt was framed as a refusal test. The next iteration should score public-but-not-indexed questions separately from private-identifier questions and numeric lookup.

## Public Data Does Not Mean Low Risk

Some public data sources include names or row-level payment records. This project keeps raw downloads local-only and emits aggregate QA artifacts, while the local UI can answer indexed named-vendor FY2026 MAP expenditure totals through deterministic lookup. Future expansion should repeat the source review and clearly label which public files are indexed.

## Tiny Models Should Not Memorize Public Records

Specific MAP facts should come from lookup/query code over public source files. The tiny model is useful for short answers over retrieved context, not as a trusted store of row-level public records.

## Local Hardware Scope

The project is tuned for an RTX 3060 Ti 8 GB GPU. Larger models, longer context, or bigger batches may not fit safely.

## No Production Guarantee

The model should not be used for procurement, employment, legal, financial, or policy decisions. It is a learning artifact.
