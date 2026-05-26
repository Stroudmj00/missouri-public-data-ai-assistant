# Deep Answer Upgrade

## Current Upgrade

The assistant now uses Deep Answer Mode as the normal architecture. Local code retrieves and verifies Missouri evidence; Vertex AI Gemini can synthesize a more natural answer when credentials are configured.

## Why This Is Better

The prior local-synthesis path read like a compact local-model demo. The current path is cleaner:

- exact facts stay in local indexed evidence
- Gemini is used for reasoning and explanation, not memorized public records
- missing credentials fail gracefully
- tests run without cloud access through fake and unavailable providers

## Provider Setup

Live Vertex AI calls use environment configuration:

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

## Default Test Behavior

The test suite does not require Vertex credentials. It verifies:

- fake-provider synthesis
- missing-provider fallback
- privacy guardrail preservation
- unsupported complex-question refusal
- comparison and ranking evidence tools

## Historical Local Models

SmolLM2 and Qwen LoRA runs are retained as historical evidence. They are not the main answer engine.
