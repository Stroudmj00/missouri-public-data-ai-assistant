# Data Directory

This project uses public Missouri sources, local evidence indexes, and generated QA pairs.

## Policy

- `raw_public/`: local-only public downloads and SQLite indexes used for reproducibility and deterministic lookup. Ignored from Git because some public files contain row-level names or contact fields.
- `processed/`: sanitized aggregate summaries that are safe to publish.
- `qa/`: sanitized train/eval QA pairs.
- `eval/`: fixed evaluation prompts for baseline and future model runs.

Do not commit raw MAP downloads, employee salary files, person-level rows, named-vendor payment rows, local SQLite indexes, or provider credentials. Exact public-record answers should be generated from local indexed files and returned with citations, not committed as copied raw rows.
