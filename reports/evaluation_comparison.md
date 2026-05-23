# Evaluation Comparison

Generated at: `2026-05-23T02:44:50+00:00`

## Scope

This report compares the base model against the LoRA-adapted model using the same fixed sanitized evaluation prompts. It is a small case-study evaluation, not a broad benchmark.

## Summary

- Base model: `HuggingFaceTB/SmolLM2-135M-Instruct`
- Adapter: `checkpoints\smollm2_135m_lora_run_001`
- Prompt count: 20
- Base pass rate: 18 / 20 (90.00%)
- Fine-tuned pass rate: 18 / 20 (90.00%)
- Improved prompts: 1
- Regressed prompts: 1
- Both passed: 17
- Both failed: 1
- Peak allocated VRAM, base eval: 272.91 MB
- Peak allocated VRAM, fine-tuned eval: 274.73 MB

## By Answer Type

| Answer Type | Count | Base Passed | Fine-Tuned Passed | Improved | Regressed |
| --- | ---: | ---: | ---: | ---: | ---: |
| short_fact | 19 | 18 | 18 | 1 | 1 |
| unknown_or_refusal | 1 | 0 | 0 | 0 | 0 |

## Interpretation

The adapter matched the base model on the simple score. The small run proved the training loop, but did not improve the headline metric.

Because the evaluation set is small and partly generated from aggregate templates, the result should be treated as a case-study signal rather than a production-quality measure.

## Example Comparisons

### map_category_004 (improved)

Question: What was the aggregate MAP expenditure total for the DEBT SERVICE category?

Expected: $538,081,025.61.

Base: The aggregate MAP expenditure total for the DEBT SERVICE category was $538,081,61.

Fine-tuned: $538,081,025.61.

### hospital_overview_002 (regressed)

Question: How many licensed hospital beds are in the processed hospital profile source?

Expected: 21,202 licensed beds.

Base: The hospital profile source contains 166 facilities, 21,202 licensed beds, and 2,032 ICU beds.

Fine-tuned: 2,032 ICU beds.

### unknown_employee_salary (both_failed)

Question: What is the salary of a named State of Missouri employee?

Expected: I do not know from the provided data. This case study excludes employee salary and person-level lookup data.

Base: The salary of a named State of Missouri employee is $100,000.

Fine-tuned: $50,000.
