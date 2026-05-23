# Command Log

These are the main verified commands for the current project state.

## Environment Check

```powershell
.\.venv\Scripts\python scripts\check_environment.py
```

## Build Public Dataset

```powershell
.\.venv\Scripts\python scripts\build_public_dataset.py --target-count 120
```

## Download All MAP Public Files

```powershell
.\.venv\Scripts\python scripts\download_map_all.py --download
```

## Build MAP Public Lookup Index

```powershell
.\.venv\Scripts\python scripts\build_map_public_index.py --rebuild
```

## Build Expanded MAP Training Data

```powershell
.\.venv\Scripts\python scripts\build_map_training_data.py
```

## Baseline Inference

```powershell
.\.venv\Scripts\python scripts\run_baseline.py --max-prompts 6 --max-new-tokens 48
```

## Fine-Tune LoRA Adapter

```powershell
.\.venv\Scripts\python scripts\finetune_lora.py --config configs\finetune_smollm2_135m_lora.yaml
```

## Fine-Tune Expanded MAP Adapter

```powershell
.\.venv\Scripts\python scripts\finetune_lora.py --config configs\finetune_smollm2_135m_lora_run_002.yaml
```

## Before/After Evaluation

```powershell
.\.venv\Scripts\python scripts\evaluate_comparison.py --max-prompts 20 --max-new-tokens 48
```

## Project Verification

```powershell
.\.venv\Scripts\python scripts\verify_project.py
```

## Chatbot Behavior Tests

```powershell
.\.venv\Scripts\python scripts\test_chatbot_behavior.py
```

Result after adversarial routing, citation, and row-preview fixes:

- 26 behavior cases passed.
- Added coverage for agency-total routing, missing requested years, vendor-to-agency direction refusals, requested top-K limits, annual peak lookups, vendor ID/list-all guardrails, generic top-agency ranking, and agency-vendor BOKF NA lookup.
- Added citation checks for MAP source files and retrieved hospital-profile QA.
- Added capped source-row preview checks for exact non-person MAP records and no-preview checks for top/aggregate/list-all and employee-pay paths.
- Rebuilt the MAP lookup index after excluding `TC_2000-Current.txt` to avoid double-counting annual tax-credit totals.
- Also passed under the lightweight launcher:

```powershell
py -3 scripts\test_chatbot_behavior.py
```

## API Citation Envelope Smoke Test

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:7860/api/ask' -Method Post -ContentType 'application/json' -Body (@{ question = 'How much did TRANSPORTATION pay BOKF NA in 2025?' } | ConvertTo-Json -Compress)
```

Observed fields included `request_id`, `served_at_utc`, `retrieval_path`, `dataset_snapshot.snapshot_id`, and citation evidence for `EXP_2025.txt`.

## Row Preview Smoke Test

After rebuilding the index with `TC_2000-Current.txt` excluded from aggregation:

- `/api/coverage` reported snapshot `3dc8547c3dc05303`, 104 indexed text files, and 6,123,427 parsed MAP rows.
- Tax-credit query for `CARTWRIGHT HOLDINGS` returned $23,139.21 with 1 source-row preview from `TC_2026.txt`.
- Agency-vendor query for `OFFICE OF ADMINISTRATION` and `CAPITAL MALL JC 1 LLC` returned $249,336.95 with 4 source-row previews from `EXP_2025.txt`.
- Employee-pay query returned file-level citation for `EMP_2026.txt` and 0 raw row previews.

## Ask The Fine-Tuned Adapter

```powershell
.\.venv\Scripts\python scripts\ask_model.py "What was the aggregate MAP expenditure total for TRANSPORTATION?"
```

## Ask Indexed Public MAP Lookup

```powershell
.\.venv\Scripts\python scripts\ask_model.py "How much was paid to CAPITAL MALL JC 1 LLC?"
```

## Local Web UI

```powershell
.\.venv\Scripts\python scripts\serve_ui.py --port 7860
```
