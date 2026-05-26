# Roadmap

## Current State

The assistant already has broad indexed Missouri public-data coverage, deterministic exact lookup, routing metadata, guardrails, citation checks, fake provider tests, and a Vertex AI Gemini provider layer.

The current public-facing name is Missouri Public Data AI Assistant.

## Near-Term Roadmap

### 1. Live Vertex Smoke Test

Configure Google Cloud credentials and run:

```powershell
.\.venv\Scripts\python scripts\smoke_vertex_deep_answer.py
```

Success means the response returns `deep_answer_status: synthesized` with cited local evidence.

### 2. Better Evidence Ranking

Move more source families behind shared scoring so complex questions can gather several relevant evidence bundles before synthesis.

Priority question types:

- comparison
- ranking
- source-discovery plus exact lookup
- plain-English report explanation

### 3. Multi-Tool Deep Answers

Allow complex questions to use more than one local evidence call before synthesis. The first version should stay bounded and auditable:

- maximum 3 tool calls
- compact evidence bundle
- citations required for public-data claims
- refusal if evidence is missing

### 4. Public Demo Polish

Keep the five-minute demo focused on:

- exact public-record lookup
- comparison
- ranking
- source discovery
- report explanation
- privacy refusal
- missing-provider fallback

### 5. Repo Hygiene

Keep raw public downloads, SQLite indexes, model weights, caches, checkpoints, and local logs out of Git. Keep historical model artifacts only when they support the case-study story.

## Deferred

- adding new public-data families
- live web search
- production authentication
- deployment
- broad legal/procurement/financial advisory features
- training another local model
