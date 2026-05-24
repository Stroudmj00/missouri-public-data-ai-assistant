# Constraints And Safe Operating Limits

## Main Constraint

The limiting resource is GPU memory, not disk or public Missouri data size.

The RTX 3060 Ti has 8 GB VRAM. Keep early experiments intentionally small so Windows, browser windows, and Codex can continue running normally.

## Data Download Estimates

Initial public Missouri data candidates are small:

| Dataset | Rows Checked | Estimated CSV Size |
| --- | ---: | ---: |
| 2023 State Expenditures | 107,523 | about 9.85 MB |
| Profile of Hospitals | 166 | about 0.05 MB |
| LTC Census Report | 47 | about 0.002 MB |
| data.mo.gov DCAT catalog metadata | 277 dataset records | about 0.4 MB |
| DHSS WIC aggregate queries | 86,044 source household rows summarized into aggregate county/municipality rows | less than 1 MB local aggregate-query footprint |
| data.mo.gov agriculture feed sample testing results | 8,388 | about 18 MB local raw/index footprint |
| DESE School Directory by District PDF | 489 district rows and 2,433 school/building rows | about 4.6 MB local PDF/index footprint |

The Missouri Accountability Portal download page is also manageable for this project:

| MAP Download Type | Current Observed Size Range |
| --- | ---: |
| Expenditures by fiscal year | about 8-10 MB for recent years |
| Employee data by calendar year | about 4-5 MB for recent years |
| Tax credit data by year | tens of KB for recent years |
| Budget restrictions by fiscal year | about 1 KB for recent years |
| Federal grants by fiscal year | about 100-125 KB for recent years |
| Bonds cumulative file | about 1 MB |

The generated sanitized QA set should be much smaller than the raw expenditure data, likely under 5 MB for the first public version.

Avoid downloading full external corpora at first. Use tiny subsets for smoke tests and only expand after training scripts prove stable.

For MAP, prefer a single recent expenditure file first. Do not download the full history or employee salary files for the first training pass.

## Model Download Estimates

Approximate first-pass model storage:

| Model Type | Expected Download/Cache |
| --- | ---: |
| From-scratch 1M-10M parameter toy GPT | no pretrained weight download |
| SmolLM2 135M Instruct | roughly a few hundred MB |
| SmolLM2 360M Instruct | roughly under 1 GB |
| TinyLlama 1.1B Chat | roughly 2-3 GB for common fp16/bf16 weights |

Hugging Face caches model weights under the user cache directory by default, not inside the project folder.

## Training Risk Controls

Use these defaults until a run proves stable:

- Close games, video editing, and heavy browser tabs before training.
- Prefer scripts that log every 10-50 steps and checkpoint infrequently.
- Start with `batch_size=1` or `2` for pretrained fine-tuning.
- Use short sequence lengths first: `max_seq_length=128` or `256`.
- Use gradient accumulation instead of large batch sizes.
- Use mixed precision only after a basic fp32/fp16 smoke test works.
- Keep the first real run under 15 minutes.
- Stop if GPU temperature stays above 80 C or system responsiveness drops.
- Do not run overnight training until we have a tested checkpoint/resume path.

## Safe Initial Scope

Recommended first implementation:

1. Pull only metadata and small samples from `data.mo.gov`.
2. Generate 100-500 sanitized QA pairs.
3. Run base-model inference on 20 fixed evaluation questions.
4. Fine-tune SmolLM2 135M first, not a 1B model.
5. Cap first fine-tuning run at 100-500 optimizer steps.

## When To Scale Up

Only scale after the first run records:

- peak VRAM
- wall-clock time
- loss curve
- sample outputs
- exact model/config
- checkpoint size
- system temperature/responsiveness notes

Scaling order:

1. More QA examples
2. More training steps
3. Longer sequence length
4. Larger model

Do not scale all four at once.
