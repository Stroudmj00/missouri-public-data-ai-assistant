# Project Plan

## Goal

Train and evaluate a tiny local language model that answers very basic questions coherently, with a Missouri public-data twist and a public GitHub case study.

## Feasibility

This is feasible on the local machine if the scope stays small.

Good fits for the RTX 3060 Ti 8 GB:

- nanoGPT-style character/token experiments
- 1M to 30M parameter from-scratch toy transformers
- TinyStories-scale experiments using subsets or short runs
- Full fine-tuning of very small models such as 100M to 300M parameter models, depending on batch size and sequence length
- LoRA/QLoRA-style fine-tuning of around 1B parameter chat models with careful memory settings

Poor fits:

- Training a general-purpose LLM from scratch
- Reproducing modern GPT-quality instruction following
- Long context training
- Full fine-tuning of multi-billion-parameter models without heavy quantization/offloading

## Technical Stack

- Python 3.11 or 3.12
- PyTorch with CUDA
- Hugging Face `transformers`, `datasets`, `accelerate`
- Optional: `trl` for supervised fine-tuning
- Optional: `peft` for LoRA
- `nanoGPT` as the educational baseline/reference
- `wandb`, TensorBoard, or CSV logs for experiment tracking
- `matplotlib` for loss/evaluation charts

## Model Tracks

### Track A: From Scratch

Purpose: show the mechanics.

Method:

- Start from nanoGPT concepts.
- Train a tiny GPT on a small simple corpus.
- Add a Missouri-public-data QA corpus only after the baseline works.
- Track train/validation loss, samples, speed, and memory.

Likely model size:

- 1M to 10M parameters for first successful run
- 10M to 30M parameters if the environment is stable

Expected outcome:

- Coherent short text in a narrow style
- Some memorized/simple QA behavior
- Not reliable factual reasoning

### Track B: Fine-Tuned Small Instruct Model

Purpose: produce better basic answers.

Candidate models:

- `HuggingFaceTB/SmolLM2-135M-Instruct`
- `HuggingFaceTB/SmolLM2-360M-Instruct`
- `TinyLlama/TinyLlama-1.1B-Chat-v1.0` with LoRA/quantization if memory allows

Method:

- Build a small curated instruction dataset from public Missouri data.
- Compare base model vs fine-tuned model.
- Keep generation settings fixed for evaluation.

Expected outcome:

- Better instruction-following and coherence than from-scratch tiny model
- Still limited knowledge and weak reasoning
- Strong case-study value because the comparison is honest

## Missouri Public Data Angle

Initial data candidates:

- `2023 State Expenditures` from data.mo.gov
- Missouri Accountability Portal public download files
- `Profile of Hospitals` from data.mo.gov
- `LTC CENSUS REPORT` from data.mo.gov
- Public `Bidding & Contracts` pages from Missouri OA
- Public `Contract Compass` page from Missouri OA

Example QA pair types:

- "What fields are included in the 2023 State Expenditures dataset?"
- "Which agency/category combination had the largest public expenditure in the processed sample?"
- "Which MAP data categories are available as public downloads?"
- "What delimiter does the MAP data download page say its files use?"
- "How many licensed beds are reported for this LTC region in the public census sample?"
- "What is the purpose of MissouriBUYS based on the public OA page?"
- "When should the assistant say it does not know?"

For the first public release, prefer aggregate questions for model training. Row-level named-entity questions are acceptable when they are answered by lookup over downloaded public files.

For MAP specifically, avoid model memorization of individual employee salary or vendor payment rows. Use deterministic lookup for exact indexed public records, and use the model for source literacy, public finance categories, aggregation, and unknown-handling examples.

## Evaluation

Use a fixed evaluation set with versioned prompts.

Metrics:

- Exact match for numeric/lookup questions
- Contains-answer score for short factual questions
- Manual coherence rating from 1 to 5
- Hallucination flag
- Unknown-handling flag
- Latency and VRAM usage

Baselines:

- Template lookup baseline
- Base pretrained model
- Fine-tuned model
- Optional from-scratch model

The honest story is not "tiny model beats everything." The story is "training data, scope, and evaluation design determine whether a small model can be useful."

## Repository Layout For The Future Public Repo

```text
missouri-tiny-llm/
  README.md
  LICENSE
  requirements.txt
  environment.yml
  data/
    README.md
    raw_public/          # gitignored or sample only
    processed/           # sanitized derived data
    qa/                  # generated training/eval QA
  notebooks/
  src/
    data/
    training/
    evaluation/
    inference/
  configs/
  experiments/
    runs.csv
    run_notes/
  docs/
    DATA_CARD.md
    MODEL_CARD.md
    CASE_STUDY.md
    LIMITATIONS.md
  tests/
```

## Context Management Plan

- Keep source notes short and cite URLs instead of copying large pages.
- Store experiment findings in dated run notes.
- Use separate files for data policy, model card, and case study.
- Keep generated data reproducible with scripts rather than hand-edited blobs.
- When using agents, split tasks into data sourcing, training implementation, evaluation, and publication review.

## First Build Milestones

1. Create environment and verify GPU PyTorch.
2. Run nanoGPT-style smoke test.
3. Pull 3 public Missouri datasets through Socrata APIs.
4. Generate a 100-question sanitized QA sample.
5. Run baseline inference with a tiny instruct model.
6. Fine-tune or LoRA-tune the model.
7. Evaluate before/after results.
8. Write public case study with limitations.

## Research Sources

- nanoGPT: https://github.com/karpathy/nanoGPT
- llm.c: https://github.com/karpathy/llm.c
- Neural Networks: Zero to Hero: https://github.com/karpathy/nn-zero-to-hero
- TinyStories paper: https://arxiv.org/abs/2305.07759
- TinyStories dataset: https://huggingface.co/datasets/roneneldan/TinyStories
- PyTorch install selector: https://pytorch.org/get-started/
- Hugging Face TRL SFTTrainer: https://huggingface.co/docs/trl/en/sft_trainer
- Hugging Face PEFT/LoRA: https://huggingface.co/docs/peft
- SmolLM2 135M: https://huggingface.co/HuggingFaceTB/SmolLM2-135M
- SmolLM2 135M Instruct: https://huggingface.co/HuggingFaceTB/SmolLM2-135M-Instruct
- TinyLlama 1.1B Chat: https://huggingface.co/TinyLlama/TinyLlama-1.1B-Chat-v1.0
- Missouri Data Portal: https://data.mo.gov
- Missouri Accountability Portal: https://mapyourtaxes.mo.gov/
- MAP data downloads: https://mapyourtaxes.mo.gov/MAP/Download/
- Missouri government public data page: https://www.mo.gov/government/transparency-and-accountability/
- Missouri OA Bidding & Contracts: https://purch.oa.mo.gov/bidding-contracts
- Missouri OA Contract Compass: https://purch.oa.mo.gov/contractcompass
- Socrata API docs: https://dev.socrata.com/docs/endpoints.html
