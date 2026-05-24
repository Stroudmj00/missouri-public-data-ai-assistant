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
| LTC Directory selected fields | 1,101 sanitized rows | about 0.6 MB selected-source footprint with census and metadata |
| data.mo.gov DCAT catalog metadata | 277 dataset records | about 0.4 MB |
| DHSS WIC aggregate queries | 86,044 source household rows summarized into aggregate county/municipality rows | less than 1 MB local aggregate-query footprint |
| data.mo.gov agriculture feed sample testing results | 8,388 | about 18 MB local raw/index footprint |
| Agricultural Market News metadata | 77 report/resource links, 71 PDF links | less than 1 MB local page snapshot/index footprint |
| DHSS cannabis verified dispensary locator and selected annual reports | 223 dispensary records and 3 selected annual-report PDFs | about 24.7 MB local source/index footprint |
| DESE child-care compliance dashboards | 5 quarterly dashboard PDFs | about 1 MB local source/index footprint |
| PSC report metadata | 27 official report PDF links | about 17 KB source page snapshot |
| OA Budget and Planning metadata | 114 official page/link records | about 225 KB source page snapshot |
| DESE School Directory by District PDF | 489 district rows and 2,433 school/building rows | about 4.6 MB local PDF/index footprint |
| DESE School Data resource metadata | 382 public resource links across 8 official source pages | less than 2 MB local source/index footprint |
| DESE APR ranking PDFs | 28 LEA rows and 101 school-building rows | less than 2 MB local PDF/index footprint |
| DHSS public-health resource metadata | 285 public resource links across 9 official source pages | less than 2 MB local source/index footprint |
| DHSS LTC inspection metadata | 434 metadata rows from 2 official pages | less than 1 MB local source/index footprint |
| MoDOT latest-year AADT route segments | 14,205 directional segment records across 229 routes | about 15.7 MB local JSON index footprint |
| MEC public-resource metadata | 157 public resource/search/form/report links across 11 official source pages | less than 2 MB local source/index footprint |
| Missouri State Auditor report metadata | 3,447 report records | about 2 MB selected-source footprint |
| SOS selected statewide election returns | 782 contests and 1,604 candidate/ballot rows | about 4 MB local PDF/index footprint |

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
