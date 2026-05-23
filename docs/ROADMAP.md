# Roadmap

## End Goal

The finished project should be a public GitHub case study that shows, end to end, how a consumer desktop can build a small, honest, Missouri-public-data question-answering experiment.

The final artifact should look like this:

- A clean GitHub repo that a reviewer can clone and run.
- A documented Python/CUDA environment that fits on the local RTX 3060 Ti machine.
- A public-data pipeline that pulls selected `data.mo.gov` sources and can index the current Missouri Accountability Portal public download inventory.
- Aggregate QA pairs that do not train the tiny model on employee salary/person-level lookups or named-vendor memorization.
- Deterministic lookup for exact public MAP records that are present in local indexed source files.
- A no-training baseline report using a tiny instruct model.
- A small fine-tuned model or adapter trained on the sanitized QA set.
- Before/after evaluation showing whether fine-tuning improved simple answer coherence, numeric recall, and refusal behavior.
- Clear limitations explaining that this is an educational case study, not an official State of Missouri product or production public-finance assistant.

The project is successful when a reader can answer four questions from the repo alone:

1. What public data was used, and what was excluded?
2. What did the local machine download, store, and run?
3. Did fine-tuning improve answers over the baseline?
4. What are the limits, risks, and next steps?

## North Star Demo

The final demo should ask a small model questions like:

```text
Question: What was the aggregate MAP expenditure total for TRANSPORTATION in the processed file?
Answer: $3,123,182,666.35.
```

It should also separate public-but-not-indexed questions from private-identifier or out-of-scope questions:

```text
Question: What is the salary of a named State of Missouri employee?
Answer: If the employee appears in the local indexed MAP employee files, answer with a cited public MAP record and suppress raw employee row previews. Private identifiers remain out of scope.
```

The point is not to build a general chatbot. The point is to show careful data handling, constrained model behavior, measurable improvement, and reproducible local ML practice.

## Phase 0: Project Safety And Environment

Status: complete.

Goal:

Prove the local machine can run the project safely before downloading model weights or doing training.

Delivered:

- Python 3.11 virtual environment outside OneDrive
- CUDA-enabled PyTorch install
- GPU smoke test
- Environment documentation
- Constraint documentation
- Raw-data Git ignore rules

Evidence:

- `docs/ENVIRONMENT.md`
- `docs/CONSTRAINTS.md`
- `scripts/check_environment.py`
- `requirements.txt`

Gate:

- `pip check` passes
- CUDA is available
- smoke test uses negligible VRAM
- disk/RAM/VRAM headroom is documented

## Phase 1: Public Data Ingestion

Status: complete.

Goal:

Build a public-data pipeline that downloads bounded public sources, emits aggregate public artifacts, and keeps raw public records local for source-backed lookup.

Delivered:

- MAP `EXP_2026` ingestion
- full MAP public-download inventory and local SQLite index
- `data.mo.gov` hospital profile ingestion
- `data.mo.gov` LTC census ingestion
- preflight download estimates
- processed aggregate summary
- local-only raw public downloads

Evidence:

- `src/missouri_tiny_llm/ingest_public_data.py`
- `scripts/build_public_dataset.py`
- `reports/preflight_estimates.json`
- `reports/ingestion_report.md`
- `reports/dataset_manifest.json`
- `data/processed/public_data_summary.json`

Gate:

- employee files are public MAP inputs, but named-person records are served through deterministic lookup rather than model-memory training
- public outputs omit raw person/contact fields
- raw public downloads are ignored by Git
- ingestion runs in minutes, not hours

## Phase 2: Sanitized QA And Evaluation Set

Status: complete.

Goal:

Generate a small, clear QA set that can support baseline and fine-tuning comparisons.

Delivered:

- 100 training QA rows
- 20 evaluation QA rows
- 20 fixed evaluation prompts
- unsupported-source and boundary examples

Evidence:

- `data/qa/train.jsonl`
- `data/qa/eval.jsonl`
- `data/eval/evaluation_prompts.jsonl`
- `docs/DATA_CARD.md`
- `docs/EVALUATION.md`

Gate:

- QA rows are aggregate-focused
- evaluation prompts are fixed and versioned
- unsupported-source behavior is represented
- dataset size is small enough for safe first-pass fine-tuning

## Phase 3: No-Training Baseline

Status: complete.

Goal:

Establish the baseline before fine-tuning so the case study has a fair before/after comparison.

Delivered:

- capped baseline inference runner
- model download estimate
- 6-prompt baseline run
- simple scoring report
- model card describing current model state

Evidence:

- `src/missouri_tiny_llm/baseline_inference.py`
- `scripts/run_baseline.py`
- `reports/baseline_preflight.json`
- `reports/baseline_outputs.jsonl`
- `reports/baseline_summary.json`
- `reports/baseline_inference_report.md`
- `docs/MODEL_CARD.md`

Current result:

- model: `HuggingFaceTB/SmolLM2-135M-Instruct`
- prompts: 6
- pass rate: 5 / 6
- peak allocated VRAM: about 273 MB

Gate:

- no training is performed
- baseline is reproducible
- runtime and VRAM are documented
- at least one failure case is preserved for comparison

## Phase 4: First Fine-Tuning Run

Status: complete.

Goal:

Train a tiny adapter or small fine-tuned model on the sanitized QA set without stressing the PC.

Recommended first run:

- model: `HuggingFaceTB/SmolLM2-135M-Instruct`
- training mode: LoRA or a very small full fine-tune if memory allows
- max sequence length: 256
- batch size: 1 or 2
- gradient accumulation: 4 to 8
- max steps: 100 to 300
- checkpoint count: 1 or 2
- target runtime: under 30 minutes

Deliverables:

- training script
- training config
- run log
- loss chart
- checkpoint/adapters saved locally
- training resource report
- updated model card

Artifacts to create:

- `configs/finetune_smollm2_135m_lora.yaml`
- `src/missouri_tiny_llm/finetune.py`
- `reports/training_run_001.md`
- `reports/training_run_001_metrics.csv`
- `reports/training_run_001_loss.png`
- `models/` or `checkpoints/` ignored from Git

Delivered:

- `configs/finetune_smollm2_135m_lora.yaml`
- `src/missouri_tiny_llm/finetune.py`
- `scripts/finetune_lora.py`
- `reports/training_preflight_001.json`
- `reports/training_run_001.md`
- `reports/training_run_001_summary.json`
- `reports/training_run_001_metrics.csv`
- `reports/training_run_001_loss.png`
- local ignored adapter at `checkpoints/smollm2_135m_lora_run_001`

Result:

- 120 optimizer steps
- 100 training QA rows
- about 51 seconds runtime
- about 619 MB peak allocated VRAM
- about 5.1 MB adapter directory
- 460,800 trainable parameters

Gate:

- run completes without system instability
- peak VRAM stays below a documented limit
- checkpoint can be loaded
- loss curve is saved
- failures are documented, not hidden

## Phase 5: Before/After Evaluation

Status: complete.

Goal:

Compare the base model against the fine-tuned model using the same fixed evaluation prompts.

Deliverables:

- post-training inference outputs
- before/after comparison table
- numeric accuracy comparison
- refusal/unknown comparison
- qualitative examples

Artifacts to create:

- `reports/finetuned_outputs.jsonl`
- `reports/evaluation_comparison.md`
- `reports/evaluation_comparison.csv`

Delivered:

- `src/missouri_tiny_llm/evaluate_comparison.py`
- `scripts/evaluate_comparison.py`
- `reports/base_eval_outputs.jsonl`
- `reports/finetuned_outputs.jsonl`
- `reports/evaluation_preflight.json`
- `reports/evaluation_comparison_summary.json`
- `reports/evaluation_comparison.md`
- `reports/evaluation_comparison.csv`

Result:

- base model: 18 / 20
- fine-tuned adapter: 18 / 20
- improved prompts: 1
- regressed prompts: 1
- both failed: 1
- interpretation: the adapter matched the base model overall and did not improve the headline metric

Gate:

- same prompts are used for baseline and fine-tuned model
- scoring method is documented
- at least one improvement and one remaining weakness are shown
- results are not overstated

## Phase 6: Public GitHub Polish

Status: complete.

Goal:

Make the repo readable as a public portfolio artifact.

Deliverables:

- final README narrative
- short architecture diagram or pipeline diagram
- clear setup instructions
- public-data source table
- reproduced command log
- limitations section
- future work section

Artifacts to finalize:

- `README.md`
- `docs/CASE_STUDY.md`
- `docs/DATA_CARD.md`
- `docs/MODEL_CARD.md`
- `docs/EVALUATION.md`
- `docs/LIMITATIONS.md`
- `reports/evaluation_comparison.md`

Delivered:

- README end-goal summary and pipeline diagram
- `docs/CASE_STUDY.md`
- `docs/DATA_CARD.md`
- `docs/MODEL_CARD.md`
- `docs/EVALUATION.md`
- `docs/LIMITATIONS.md`
- `reports/command_log.md`
- `reports/evaluation_comparison.md`

Gate:

- a reviewer can understand the project in under five minutes
- a technical reviewer can rerun the safe pipeline
- no raw public records are accidentally committed
- claims match the actual reports

## Phase 7: Portfolio Packaging

Status: complete.

Goal:

Turn the project into a career-facing case study.

Deliverables:

- concise portfolio summary
- resume bullet candidates
- interview story outline
- screenshots or small charts
- GitHub repo description

Suggested positioning:

> Built a reproducible tiny-LLM case study using public Missouri finance and healthcare datasets, with a CUDA-enabled local training environment, sanitized aggregate QA generation, baseline evaluation, and documented data-safety boundaries.

Artifacts to create:

- `docs/PORTFOLIO_SUMMARY.md`
- `reports/project_screenshot_plan.md`
- one or two small charts from training/evaluation

Delivered:

- `docs/PORTFOLIO_SUMMARY.md`
- `reports/project_screenshot_plan.md`
- `reports/training_run_001_loss.png`
- evaluation comparison examples in `reports/evaluation_comparison.md`

Gate:

- portfolio language is accurate
- technical claims are backed by files in the repo
- public-sector data handling is framed carefully

## Current Next Goal Command

Use this when ready to proceed:

```text
/goal Improve the Missouri Tiny LLM case study with a stronger evaluation iteration: score aggregate QA, exact public-record lookup, unsupported-source questions, private-identifier refusals, and citation quality separately; keep private identifiers and non-public work material out of scope; replace brittle heuristic matching with a stronger search/ranking layer; and compare run 003 against run 002 without overwriting the original reports.
```
