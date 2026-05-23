# Baseline Inference Report

Generated at: `2026-05-23T02:05:51+00:00`

## Scope

This is a no-training baseline run against sanitized aggregate evaluation prompts. It uses short context snippets, caps prompt count and output length, and does not download or use employee salary/person-level data.

## Run Summary

- Model: `HuggingFaceTB/SmolLM2-135M-Instruct`
- Device: `cuda`
- Prompt count: 6
- Max new tokens: 48
- Model load time: 1.877 seconds
- Inference time: 7.478 seconds
- Peak allocated VRAM: 272.91 MB
- Simple pass count: 5 / 6
- Simple pass rate: 83.33%

## Sample Outputs

### map_overview_001

Question: How many rows are in the sanitized MAP expenditure build?

Expected: 94,731 rows.

Generated: The sanitized MAP expenditure build has 94,731 rows, 25 agencies, 18 categories, and total payments of $35,836,030,005.81

Score: `True` by numeric token overlap

### map_agency_004

Question: What was the aggregate MAP expenditure total for TRANSPORTATION in the processed file?

Expected: $3,123,182,666.35.

Generated: The aggregate MAP expenditure total for TRANSPORTATION in the processed file is $3,123,182,666.35.

Score: `True` by numeric token overlap

### map_agency_010

Question: What was the aggregate MAP expenditure total for NATURAL RESOURCES in the processed file?

Expected: $511,519,819.48.

Generated: The aggregate NATURAL RESOURCES in the processed file was $511,519,819.48.

Score: `True` by numeric token overlap

### map_category_004

Question: What was the aggregate MAP expenditure total for the DEBT SERVICE category?

Expected: $538,081,025.61.

Generated: The aggregate MAP expenditure total for the DEBT SERVICE category was $538,081,61.

Score: `False` by numeric token overlap

### map_category_010

Question: What was the aggregate MAP expenditure total for the FUEL & UTILITIES category?

Expected: $67,924,357.45.

Generated: The aggregate MAP expenditure total for the FUEL & UTILITIES category was $67,924,357.45.

Score: `True` by numeric token overlap

### map_agency_category_004

Question: What is the aggregate total for TRANSPORTATION in category PROPERTY & IMPROVEMENTS?

Expected: $1,840,245,911.75.

Generated: The aggregate total for TRANSPORTATION in category PROPERTY & IMPROVEMENTS is $1,840,245,911.75.

Score: `True` by numeric token overlap
