# Data Card

## Dataset Name

Missouri Tiny LLM Public QA

## Intended Use

Educational case study for testing whether a tiny local language model can answer simple questions over Missouri public-data aggregates, with deterministic lookup for indexed row-level public MAP records.

## Sources

- Missouri Accountability Portal data download page: https://mapyourtaxes.mo.gov/MAP/Download/
- MAP public download categories: expenditures, employees, tax credits, federal grants, budget restrictions, bonds, stimulus, and check cancellations
- data.mo.gov Profile of Hospitals: https://data.mo.gov/resource/q8me-hzr8.json
- data.mo.gov LTC Census Report: https://data.mo.gov/resource/bf8b-a47t.json

## Generated Artifacts

- Training QA rows: 100
- Evaluation QA rows: 20
- Expanded MAP run 002 training QA rows: 304
- Expanded MAP run 002 evaluation QA rows: 40
- Processed summary: `data/processed/public_data_summary.json`
- Evaluation prompts: `data/eval/evaluation_prompts.jsonl`
- Local MAP lookup index: `data/raw_public/map_public_lookup.sqlite` (ignored by Git)

## Source Volumes

- MAP expenditure rows processed: 94,731
- MAP total aggregate payments: $35,836,030,005.81
- MAP all-files download inventory: 107 listed items
- MAP local lookup index: 104 text files, 6,123,427 parsed rows
- MAP raw public download footprint: about 589 MB
- MAP SQLite lookup footprint: about 1.15 GB, ignored by Git
- Hospital profile rows processed: 166
- LTC census rows processed: 47

## Sanitization

Raw MAP downloads may contain vendor names and other row-level public records. The public QA files do not emit vendor names, employee salaries, person-level salary records, addresses, phone numbers, fax numbers, or hospital administrator names.

The local UI may answer exact public-record questions when the entity appears in the local MAP lookup index. Those answers come from deterministic lookup over local public source files, not from model memorization.

## Current Scope

- Employee pay lookup is allowed for indexed public MAP employee files.
- Named-vendor expenditure lookup is allowed for indexed public MAP expenditure files.
- Capped raw-row previews are allowed for non-person exact-record answers; employee raw-row previews are suppressed in the UI/API.

## Exclusions

- Internal State of Missouri notes or non-public work material
- Raw MAP downloads in the public Git repo
- Local SQLite lookup index in the public Git repo
- Local model caches and LoRA checkpoints in the public Git repo
- Any claim of State of Missouri endorsement

## Limitations

The QA set is small and aggregate-focused. The row-level MAP lookup is limited to the public source files present under `data/raw_public/`. It is suitable for a constrained learning case study, not a production public-finance assistant.
