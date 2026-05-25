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

## SOS Election Returns Index

```powershell
py scripts\build_sos_elections_index.py --force
py scripts\test_chatbot_behavior.py
```

Observed result: 3 selected official SOS election-return PDFs, 782 contests, 1,604 candidate/ballot result rows, and 120 passing chatbot behavior cases.

## Hospital Profile Exact Lookup

```powershell
py scripts\build_data_mo_hospital_index.py --force
py scripts\ask_model.py "Which hospital has the most licensed beds?"
```

Observed result: 166 public hospital profile rows, 21,202 licensed beds, 2,032 ICU licensed beds, and Barnes Jewish Hospital as the largest indexed facility by licensed beds. Chatbot output suppresses address, phone, fax, and administrator-name fields while linking to the official data.mo.gov source.

## DOR Historical Taxable-Sales Lookup

```powershell
py scripts\build_dor_reports_index.py --force
py scripts\ask_model.py "How did Boone County taxable sales change from 2024 to 2025?"
```

Observed result: 16 official DOR public report files, 39,486 aggregate records, and exact 2016-2025 county Sales/Use taxable-sales lookup. Boone County taxable sales increased from $4,009,162,062.65 in 2024 to $4,237,498,350.94 in 2025, with citations to both official DOR ZIP downloads.

## DOR Food Tax Lookup

```powershell
py scripts\build_dor_reports_index.py --force
py scripts\ask_model.py "How did Boone County food tax change from FY24 to FY25?"
```

Observed result: 20 official DOR public report files, 45,460 aggregate records, and exact FY22-FY25 Food Tax by Political Subdivision lookup. Boone County food tax reported increased from $9,359,686.58 in FY24 to $9,704,724.54 in FY25, with citations to both official DOR PDFs.

## DOR Working Family Tax Credit Lookup

```powershell
py scripts\build_dor_reports_index.py --force
py scripts\ask_model.py "How did total Working Family Tax Credit amount change from 2024 to 2025?"
py scripts\test_chatbot_behavior.py
py scripts\test_source_usefulness.py
py scripts\verify_project.py
```

Observed result after the quarterly tax-credit expansion: 29 official DOR public report files, 45,948 aggregate records, exact 2024-2025 Missouri Working Family Tax Credit lookup by income range, and FY25-FY26 quarterly tax-credit report lookup. Total Working Family Tax Credit amount increased from $28,491,858.00 in 2024 to $46,062,034.00 in 2025, with citations to both official DOR PDFs.

## DOR Quarterly Tax Credit Lookup

```powershell
py scripts\build_dor_reports_index.py --force
py scripts\ask_model.py "Which tax credit had the highest issued FY to date in FY26 Q3?"
py scripts\test_chatbot_behavior.py
py scripts\test_source_usefulness.py
py scripts\verify_project.py
```

Observed result: the exact DOR parser now covers FY25 Q1-Q4 and FY26 Q1-Q3 quarterly tax-credit PDFs. In FY26 Q3, Low Income Housing had the highest issued FY-to-date amount at $73,929,460.00, with a citation to the official FY26 third-quarter DOR tax-credit report PDF.

## Full Contract Detail Metadata

```powershell
py scripts\build_contract_index.py --force --delay-seconds 0.01
py scripts\build_contract_document_index.py --force --limit 50 --max-mb 25 --delay-seconds 0.02
py scripts\test_chatbot_behavior.py
py scripts\test_source_usefulness.py
py scripts\verify_project.py
```

Observed result: the contract metadata pass now indexes 991 of 991 public contract detail pages with zero errors. The capped document-text pass now downloads 50 public PDFs while staying under the 25 MB laptop-safety cap, and the expanded metadata index exposes 235 candidate PDF links for future targeted extraction.
