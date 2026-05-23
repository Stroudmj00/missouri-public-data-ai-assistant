# Data Directory

This project uses public Missouri sources and generated QA pairs.

## Policy

- `raw_public/`: local-only public downloads used for reproducibility and deterministic lookup. Ignored from Git because some public files contain row-level names.
- `processed/`: sanitized aggregate summaries that are safe to publish.
- `qa/`: sanitized train/eval QA pairs.
- `eval/`: fixed evaluation prompts for baseline and future model runs.

Do not commit raw MAP downloads, employee salary files, person-level rows, or named-vendor payment rows. Exact MAP public-record answers should be generated from local indexed files, not committed as copied raw rows.
