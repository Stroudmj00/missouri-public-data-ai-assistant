"""Run a small baseline inference pass against sanitized evaluation prompts."""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil
import requests
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EVAL_PROMPTS = PROJECT_ROOT / "data" / "eval" / "evaluation_prompts.jsonl"
REPORTS_DIR = PROJECT_ROOT / "reports"

DEFAULT_MODEL = "HuggingFaceTB/SmolLM2-135M-Instruct"
MAX_SAFE_PROMPTS = 8
MAX_SAFE_NEW_TOKENS = 64


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def estimate_model_download_mb(model_id: str) -> dict[str, Any]:
    # HEAD requests avoid downloading model weights during preflight.
    files = ["model.safetensors", "tokenizer.json", "config.json", "generation_config.json"]
    estimates: dict[str, Any] = {}
    total = 0
    for filename in files:
        url = f"https://huggingface.co/{model_id}/resolve/main/{filename}"
        try:
            response = requests.head(url, allow_redirects=True, timeout=30)
            size = int(response.headers.get("content-length") or 0)
            estimates[filename] = {
                "status_code": response.status_code,
                "content_length_bytes": size,
                "content_length_mb": round(size / 1024**2, 3) if size else None,
            }
            total += size
        except requests.RequestException as exc:
            estimates[filename] = {"error": str(exc)}
    return {
        "model_id": model_id,
        "known_file_estimates": estimates,
        "known_total_mb": round(total / 1024**2, 3),
        "practical_cache_estimate_mb": "about 300-500 MB for the first baseline run",
    }


def make_prompt(row: dict[str, Any]) -> str:
    return (
        "You are answering a narrow public-data QA question for an educational case study.\n"
        "Use only the provided context. If the answer is excluded or absent, say you do not know from the provided data.\n\n"
        f"Context: {row['context']}\n"
        f"Question: {row['question']}\n"
        "Answer briefly:"
    )


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def numeric_tokens(text: str) -> list[str]:
    return re.findall(r"\d+(?:\.\d+)?", text.replace(",", ""))


def score_output(expected: str, generated: str, answer_type: str) -> dict[str, Any]:
    expected_norm = normalize(expected)
    generated_norm = normalize(generated)

    if answer_type == "unknown_or_refusal":
        passed = any(
            phrase in generated_norm
            for phrase in ["do not know", "don't know", "not know", "excluded", "not provided"]
        )
        return {"passed": passed, "method": "unknown/refusal phrase"}

    expected_numbers = numeric_tokens(expected)
    generated_numbers = numeric_tokens(generated)
    if expected_numbers:
        passed = any(number in generated_numbers for number in expected_numbers)
        return {
            "passed": passed,
            "method": "numeric token overlap",
            "expected_numbers": expected_numbers,
            "generated_numbers": generated_numbers[:10],
        }

    passed = expected_norm.rstrip(".") in generated_norm
    return {"passed": passed, "method": "normalized substring"}


def preflight(model_id: str, max_prompts: int, max_new_tokens: int) -> dict[str, Any]:
    disk = psutil.disk_usage("C:\\")
    memory = psutil.virtual_memory()
    gpu = {
        "cuda_available": torch.cuda.is_available(),
        "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu",
        "total_vram_gb": round(torch.cuda.get_device_properties(0).total_memory / 1024**3, 2)
        if torch.cuda.is_available()
        else None,
    }
    payload = {
        "generated_at_utc": utc_now(),
        "model_download_estimate": estimate_model_download_mb(model_id),
        "disk_free_gb": round(disk.free / 1024**3, 2),
        "ram_available_gb": round(memory.available / 1024**3, 2),
        "gpu": gpu,
        "run_limits": {
            "max_prompts": max_prompts,
            "max_new_tokens": max_new_tokens,
            "training": False,
            "expected_runtime": "under 5 minutes on the first run after model download",
        },
        "safety_limits": [
            "no training",
            "no gradient calculation",
            "evaluation prompts capped",
            "short generation length",
        ],
    }
    write_json(REPORTS_DIR / "baseline_preflight.json", payload)
    return payload


def load_model(model_id: str) -> tuple[Any, Any, torch.device]:
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    dtype = torch.float16 if device.type == "cuda" else torch.float32
    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        dtype=dtype,
        low_cpu_mem_usage=True,
    )
    model.to(device)
    model.eval()
    return tokenizer, model, device


def generate_answer(tokenizer: Any, model: Any, device: torch.device, prompt: str, max_new_tokens: int) -> str:
    messages = [{"role": "user", "content": prompt}]
    if getattr(tokenizer, "chat_template", None):
        text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    else:
        text = prompt

    inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=768).to(device)
    with torch.inference_mode():
        generated = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            pad_token_id=tokenizer.eos_token_id,
        )
    new_tokens = generated[0, inputs["input_ids"].shape[-1] :]
    return tokenizer.decode(new_tokens, skip_special_tokens=True).strip()


def run_baseline(model_id: str, max_prompts: int, max_new_tokens: int) -> dict[str, Any]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    if max_prompts < 1 or max_prompts > MAX_SAFE_PROMPTS:
        raise SystemExit(f"--max-prompts must be between 1 and {MAX_SAFE_PROMPTS}")
    if max_new_tokens < 1 or max_new_tokens > MAX_SAFE_NEW_TOKENS:
        raise SystemExit(f"--max-new-tokens must be between 1 and {MAX_SAFE_NEW_TOKENS}")

    prompts = read_jsonl(EVAL_PROMPTS)[:max_prompts]
    if not prompts:
        raise SystemExit("No evaluation prompts found. Run ingest_public_data.py first.")

    preflight_payload = preflight(model_id, max_prompts, max_new_tokens)
    started = time.perf_counter()
    tokenizer, model, device = load_model(model_id)
    load_elapsed = time.perf_counter() - started

    outputs: list[dict[str, Any]] = []
    inference_started = time.perf_counter()
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()

    for row in prompts:
        prompt = make_prompt(row)
        generated = generate_answer(tokenizer, model, device, prompt, max_new_tokens)
        score = score_output(row["expected_answer"], generated, row["answer_type"])
        outputs.append(
            {
                "id": row["id"],
                "source": row["source"],
                "question": row["question"],
                "expected_answer": row["expected_answer"],
                "generated_answer": generated,
                "score": score,
            }
        )

    inference_elapsed = time.perf_counter() - inference_started
    passed = sum(1 for row in outputs if row["score"]["passed"])
    peak_vram_mb = (
        round(torch.cuda.max_memory_allocated() / 1024**2, 2) if torch.cuda.is_available() else None
    )
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    write_jsonl(REPORTS_DIR / "baseline_outputs.jsonl", outputs)
    report = {
        "generated_at_utc": utc_now(),
        "model_id": model_id,
        "device": str(device),
        "prompt_count": len(outputs),
        "max_new_tokens": max_new_tokens,
        "load_elapsed_seconds": round(load_elapsed, 3),
        "inference_elapsed_seconds": round(inference_elapsed, 3),
        "passed_count": passed,
        "pass_rate": round(passed / len(outputs), 4),
        "peak_allocated_vram_mb": peak_vram_mb,
        "preflight": preflight_payload,
    }
    write_json(REPORTS_DIR / "baseline_summary.json", report)
    write_markdown_report(report, outputs)
    write_baseline_model_card(report)
    return report


def write_markdown_report(report: dict[str, Any], outputs: list[dict[str, Any]]) -> None:
    lines = [
        "# Baseline Inference Report",
        "",
        f"Generated at: `{report['generated_at_utc']}`",
        "",
        "## Scope",
        "",
        "This is a no-training baseline run against sanitized aggregate evaluation prompts. It uses short context snippets, caps prompt count and output length, and does not download or use employee salary/person-level data.",
        "",
        "## Run Summary",
        "",
        f"- Model: `{report['model_id']}`",
        f"- Device: `{report['device']}`",
        f"- Prompt count: {report['prompt_count']}",
        f"- Max new tokens: {report['max_new_tokens']}",
        f"- Model load time: {report['load_elapsed_seconds']} seconds",
        f"- Inference time: {report['inference_elapsed_seconds']} seconds",
        f"- Peak allocated VRAM: {report['peak_allocated_vram_mb']} MB",
        f"- Simple pass count: {report['passed_count']} / {report['prompt_count']}",
        f"- Simple pass rate: {report['pass_rate']:.2%}",
        "",
        "## Sample Outputs",
        "",
    ]
    for row in outputs:
        lines.extend(
            [
                f"### {row['id']}",
                "",
                f"Question: {row['question']}",
                "",
                f"Expected: {row['expected_answer']}",
                "",
                f"Generated: {row['generated_answer']}",
                "",
                f"Score: `{row['score']['passed']}` by {row['score']['method']}",
                "",
            ]
        )
    (REPORTS_DIR / "baseline_inference_report.md").write_text("\n".join(lines), encoding="utf-8")


def write_baseline_model_card(report: dict[str, Any]) -> None:
    content = f"""# Baseline Model Card

## Historical Baseline State

This report describes a historical no-training baseline inference run using `{report['model_id']}`. It is not the current runtime model card for the Missouri Public Data AI Assistant.

## Baseline Purpose

The baseline tests whether a compact local instruct model can answer simple questions when each prompt includes a short, sanitized public-data context snippet.

## Training Status

- Training performed: no
- Fine-tuning performed: no
- Evaluation prompts: {report['prompt_count']}
- Max generated tokens per prompt: {report['max_new_tokens']}
- Device used: {report['device']}
- Peak allocated VRAM during baseline: {report['peak_allocated_vram_mb']} MB

## Intended Use

Educational case study and reproducibility scaffold for historical local LoRA fine-tuning experiments.

## Out Of Scope

- Production public-finance assistant
- Legal, procurement, financial, or employment advice
- Employee salary lookup
- Named-vendor payment lookup
- State of Missouri endorsement or official representation

## Known Limitations

The model had not yet been trained on the generated QA set for this run. The baseline should be interpreted as a starting point for comparison, not the current assistant architecture.
"""
    (REPORTS_DIR / "baseline_model_card.md").write_text(content, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-id", default=DEFAULT_MODEL)
    parser.add_argument("--max-prompts", type=int, default=6)
    parser.add_argument("--max-new-tokens", type=int, default=48)
    args = parser.parse_args()

    report = run_baseline(args.model_id, args.max_prompts, args.max_new_tokens)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
