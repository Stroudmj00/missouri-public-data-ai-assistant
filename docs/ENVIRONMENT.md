# Environment

## Local Python Setup

Use a project-local virtual environment:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements.txt
```

Run commands directly through the venv:

```powershell
.\.venv\Scripts\python scripts\test_assistant_behavior.py
```

The script name is historical; it validates assistant behavior.

If the venv is not present, the Windows launcher can run the scripts when dependencies are installed globally:

```powershell
py -3 scripts\test_assistant_behavior.py
```

## Vertex AI Setup

Deep Answer Mode uses Vertex AI only when credentials are configured:

```powershell
$env:GOOGLE_CLOUD_PROJECT="your-project-id"
$env:GOOGLE_CLOUD_LOCATION="global"
$env:GOOGLE_GENAI_USE_VERTEXAI="True"
$env:MISSOURI_DEEP_ANSWER_MODEL="gemini-3-flash-preview"
$env:MISSOURI_VERTEX_THINKING_LEVEL="MEDIUM"
```

Then run:

```powershell
.\.venv\Scripts\python scripts\smoke_vertex_deep_answer.py
```

Without those settings, the assistant keeps running and returns local evidence with `deep_answer_status: unavailable_fallback`.

## Historical Training Environment

The historical LoRA runs were verified on a Windows desktop with:

- Python 3.11
- CUDA-enabled PyTorch
- NVIDIA RTX 3060 Ti with 8 GB VRAM

The current assistant does not require GPU training for normal evidence lookup, tests, or missing-provider fallback.

## Clean Repo Rules

Do not commit local runtime state:

- `.venv/`
- `models/`
- `checkpoints/`
- `data/raw_public/*`
- SQLite files
- logs
- `tmp/`

These are already covered by `.gitignore`.
