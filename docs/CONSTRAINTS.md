# Constraints

## Core Constraint

The assistant must stay source-grounded. Public-data claims should come from local indexed evidence and citations, not from model memory.

## Runtime Constraints

- Vertex AI credentials are optional.
- Missing Vertex credentials must return `deep_answer_status: unavailable_fallback`.
- Default tests must pass without cloud access.
- The app must not hardcode secrets.
- Raw public downloads and SQLite indexes stay local and ignored by Git.

## Data Constraints

- Do not add new datasets until retrieval, ranking, and demo quality are stable.
- Suppress private identifiers and unnecessary contact fields.
- Avoid full table dumps.
- Keep row previews capped and sanitized.
- Treat public-but-sensitive records with explicit source and scope notes.

## Model Constraints

- The historical local models are not trusted stores of exact public facts.
- Vertex AI synthesis must use supplied evidence only.
- Unsupported questions should refuse instead of speculating.
- Privacy-sensitive questions should refuse before synthesis.

## Public Repo Constraints

- Keep the root focused: README, license, requirements, code, docs, data stubs, scripts, reports.
- Keep generated local state out of Git: `.venv`, caches, checkpoints, models, raw downloads, SQLite files, logs, and `tmp`.
- Keep historical reports only when they support reproducibility or the portfolio story.
