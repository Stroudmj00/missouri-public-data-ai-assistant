"""Compare base and fine-tuned adapter outputs on fixed evaluation prompts."""

from __future__ import annotations

import argparse
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil
import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

from missouri_tiny_llm.baseline_inference import (
    estimate_model_download_mb,
    generate_answer,
    make_prompt,
    read_jsonl,
    score_output,
    write_json,
    write_jsonl,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EVAL_PROMPTS = PROJECT_ROOT / "data" / "eval" / "evaluation_prompts.jsonl"
REPORTS_DIR = PROJECT_ROOT / "reports"
DOCS_DIR = PROJECT_ROOT / "docs"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def current_resource_snapshot() -> dict[str, Any]:
    disk = psutil.disk_usage("C:\\")
    memory = psutil.virtual_memory()
    return {
        "disk_free_gb": round(disk.free / 1024**3, 2),
        "ram_available_gb": round(memory.available / 1024**3, 2),
        "cuda_available": torch.cuda.is_available(),
        "gpu_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "gpu_total_vram_gb": round(torch.cuda.get_device_properties(0).total_memory / 1024**3, 2)
        if torch.cuda.is_available()
        else None,
    }


def load_base(model_id: str) -> tuple[Any, Any, torch.device]:
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
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


def load_adapter(model_id: str, adapter_path: Path) -> tuple[Any, Any, torch.device]:
    tokenizer, base_model, device = load_base(model_id)
    model = PeftModel.from_pretrained(base_model, adapter_path)
    model.to(device)
    model.eval()
    return tokenizer, model, device


def run_model(
    label: str,
    tokenizer: Any,
    model: Any,
    device: torch.device,
    prompts: list[dict[str, Any]],
    max_new_tokens: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    outputs: list[dict[str, Any]] = []
    started = time.perf_counter()
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()
    for row in prompts:
        generated = generate_answer(tokenizer, model, device, make_prompt(row), max_new_tokens)
        score = score_output(row["expected_answer"], generated, row["answer_type"])
        outputs.append(
            {
                "id": row["id"],
                "source": row["source"],
                "answer_type": row["answer_type"],
                "question": row["question"],
                "expected_answer": row["expected_answer"],
                "generated_answer": generated,
                "score": score,
                "model_label": label,
            }
        )
    summary = {
        "label": label,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "passed_count": sum(1 for row in outputs if row["score"]["passed"]),
        "prompt_count": len(outputs),
        "pass_rate": round(
            sum(1 for row in outputs if row["score"]["passed"]) / max(len(outputs), 1),
            4,
        ),
        "peak_allocated_vram_mb": round(torch.cuda.max_memory_allocated() / 1024**2, 2)
        if torch.cuda.is_available()
        else None,
    }
    return outputs, summary


def compare_outputs(
    base_outputs: list[dict[str, Any]],
    tuned_outputs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    tuned_by_id = {row["id"]: row for row in tuned_outputs}
    rows: list[dict[str, Any]] = []
    for base in base_outputs:
        tuned = tuned_by_id[base["id"]]
        base_pass = bool(base["score"]["passed"])
        tuned_pass = bool(tuned["score"]["passed"])
        if tuned_pass and not base_pass:
            outcome = "improved"
        elif base_pass and not tuned_pass:
            outcome = "regressed"
        elif tuned_pass and base_pass:
            outcome = "both_passed"
        else:
            outcome = "both_failed"
        rows.append(
            {
                "id": base["id"],
                "source": base["source"],
                "answer_type": base["answer_type"],
                "question": base["question"],
                "expected_answer": base["expected_answer"],
                "base_passed": base_pass,
                "tuned_passed": tuned_pass,
                "outcome": outcome,
                "base_answer": base["generated_answer"],
                "tuned_answer": tuned["generated_answer"],
            }
        )
    return rows


def write_comparison_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def summarize_by_answer_type(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    answer_types = sorted({row["answer_type"] for row in rows})
    summary: list[dict[str, Any]] = []
    for answer_type in answer_types:
        subset = [row for row in rows if row["answer_type"] == answer_type]
        summary.append(
            {
                "answer_type": answer_type,
                "count": len(subset),
                "base_passed": sum(1 for row in subset if row["base_passed"]),
                "tuned_passed": sum(1 for row in subset if row["tuned_passed"]),
                "improved": sum(1 for row in subset if row["outcome"] == "improved"),
                "regressed": sum(1 for row in subset if row["outcome"] == "regressed"),
            }
        )
    return summary


def write_markdown_report(
    report: dict[str, Any],
    comparison_rows: list[dict[str, Any]],
    type_summary: list[dict[str, Any]],
) -> None:
    improved = [row for row in comparison_rows if row["outcome"] == "improved"]
    regressed = [row for row in comparison_rows if row["outcome"] == "regressed"]
    failed = [row for row in comparison_rows if not row["tuned_passed"]]
    sample_rows = []
    seen_ids: set[str] = set()
    for row in improved[:2] + regressed[:2] + failed[:2]:
        if row["id"] not in seen_ids:
            sample_rows.append(row)
            seen_ids.add(row["id"])
    if not sample_rows:
        sample_rows = comparison_rows[:4]

    lines = [
        "# Evaluation Comparison",
        "",
        f"Generated at: `{report['generated_at_utc']}`",
        "",
        "## Scope",
        "",
        "This report compares the base model against the LoRA-adapted model using the same fixed sanitized evaluation prompts. It is a small case-study evaluation, not a broad benchmark.",
        "",
        "## Summary",
        "",
        f"- Base model: `{report['model_id']}`",
        f"- Adapter: `{report['adapter_path']}`",
        f"- Prompt count: {report['prompt_count']}",
        f"- Base pass rate: {report['base']['passed_count']} / {report['prompt_count']} ({report['base']['pass_rate']:.2%})",
        f"- Fine-tuned pass rate: {report['fine_tuned']['passed_count']} / {report['prompt_count']} ({report['fine_tuned']['pass_rate']:.2%})",
        f"- Improved prompts: {report['outcomes']['improved']}",
        f"- Regressed prompts: {report['outcomes']['regressed']}",
        f"- Both passed: {report['outcomes']['both_passed']}",
        f"- Both failed: {report['outcomes']['both_failed']}",
        f"- Peak allocated VRAM, base eval: {report['base']['peak_allocated_vram_mb']} MB",
        f"- Peak allocated VRAM, fine-tuned eval: {report['fine_tuned']['peak_allocated_vram_mb']} MB",
        "",
        "## By Answer Type",
        "",
        "| Answer Type | Count | Base Passed | Fine-Tuned Passed | Improved | Regressed |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in type_summary:
        lines.append(
            f"| {row['answer_type']} | {row['count']} | {row['base_passed']} | {row['tuned_passed']} | {row['improved']} | {row['regressed']} |"
        )

    lines.extend(["", "## Interpretation", ""])
    if report["fine_tuned"]["passed_count"] > report["base"]["passed_count"]:
        lines.append("The adapter improved the simple score on this fixed evaluation set.")
    elif report["fine_tuned"]["passed_count"] == report["base"]["passed_count"]:
        lines.append("The adapter matched the base model on the simple score. The small run proved the training loop, but did not improve the headline metric.")
    else:
        lines.append("The adapter underperformed the base model on the simple score. This is useful evidence: the first safe run is not automatically better, and the next iteration should tune training data, steps, and evaluation coverage.")
    lines.append("")
    lines.append("Because the evaluation set is small and partly generated from aggregate templates, the result should be treated as a case-study signal rather than a production-quality measure.")

    lines.extend(["", "## Example Comparisons", ""])
    for row in sample_rows:
        lines.extend(
            [
                f"### {row['id']} ({row['outcome']})",
                "",
                f"Question: {row['question']}",
                "",
                f"Expected: {row['expected_answer']}",
                "",
                f"Base: {row['base_answer']}",
                "",
                f"Fine-tuned: {row['tuned_answer']}",
                "",
            ]
        )

    (REPORTS_DIR / "evaluation_comparison.md").write_text("\n".join(lines), encoding="utf-8")


def update_evaluation_doc(report: dict[str, Any]) -> None:
    content = f"""# Evaluation Plan

## Evaluation Set

Fixed prompts live in:

```text
data/eval/evaluation_prompts.jsonl
```

Each prompt includes question, short sanitized context, expected answer, source, and answer type.

## Completed Comparison

- Base model: `{report['model_id']}`
- Fine-tuned adapter: `{report['adapter_path']}`
- Prompt count: {report['prompt_count']}
- Base pass rate: {report['base']['passed_count']} / {report['prompt_count']} ({report['base']['pass_rate']:.2%})
- Fine-tuned pass rate: {report['fine_tuned']['passed_count']} / {report['prompt_count']} ({report['fine_tuned']['pass_rate']:.2%})

Full results:

- `reports/evaluation_comparison.md`
- `reports/evaluation_comparison.csv`
- `reports/base_eval_outputs.jsonl`
- `reports/finetuned_outputs.jsonl`

## Metrics

- Numeric token overlap for aggregate numeric answers
- Normalized substring match for short factual answers
- Refusal/unknown phrase check for excluded data requests
- Runtime
- Peak allocated VRAM

## Interpretation

This is a small portfolio case-study evaluation. It is useful for showing reproducibility, model behavior, and iteration discipline, but it is not a broad benchmark.
"""
    (DOCS_DIR / "EVALUATION.md").write_text(content, encoding="utf-8")


def evaluate(model_id: str, adapter_path: Path, max_prompts: int, max_new_tokens: int) -> dict[str, Any]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    prompts = read_jsonl(EVAL_PROMPTS)[:max_prompts]
    if not prompts:
        raise SystemExit("No evaluation prompts found. Run the dataset build first.")

    preflight = {
        "generated_at_utc": utc_now(),
        "model_id": model_id,
        "adapter_path": str(adapter_path.relative_to(PROJECT_ROOT)),
        "prompt_count": len(prompts),
        "max_new_tokens": max_new_tokens,
        "model_download_estimate": estimate_model_download_mb(model_id),
        "adapter_size_mb": round(
            sum(path.stat().st_size for path in adapter_path.rglob("*") if path.is_file()) / 1024**2,
            3,
        ),
        "resource_snapshot": current_resource_snapshot(),
        "safety_limits": [
            "no training",
            "same fixed prompts for base and fine-tuned model",
            "short capped generations",
        ],
    }
    write_json(REPORTS_DIR / "evaluation_preflight.json", preflight)

    tokenizer, base_model, device = load_base(model_id)
    base_outputs, base_summary = run_model("base", tokenizer, base_model, device, prompts, max_new_tokens)
    del base_model
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    tokenizer, tuned_model, device = load_adapter(model_id, adapter_path)
    tuned_outputs, tuned_summary = run_model(
        "fine_tuned",
        tokenizer,
        tuned_model,
        device,
        prompts,
        max_new_tokens,
    )
    del tuned_model
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    write_jsonl(REPORTS_DIR / "base_eval_outputs.jsonl", base_outputs)
    write_jsonl(REPORTS_DIR / "finetuned_outputs.jsonl", tuned_outputs)
    comparison_rows = compare_outputs(base_outputs, tuned_outputs)
    write_comparison_csv(REPORTS_DIR / "evaluation_comparison.csv", comparison_rows)
    outcomes = {
        "improved": sum(1 for row in comparison_rows if row["outcome"] == "improved"),
        "regressed": sum(1 for row in comparison_rows if row["outcome"] == "regressed"),
        "both_passed": sum(1 for row in comparison_rows if row["outcome"] == "both_passed"),
        "both_failed": sum(1 for row in comparison_rows if row["outcome"] == "both_failed"),
    }
    type_summary = summarize_by_answer_type(comparison_rows)
    report = {
        "generated_at_utc": utc_now(),
        "model_id": model_id,
        "adapter_path": str(adapter_path.relative_to(PROJECT_ROOT)),
        "prompt_count": len(prompts),
        "max_new_tokens": max_new_tokens,
        "base": base_summary,
        "fine_tuned": tuned_summary,
        "outcomes": outcomes,
        "by_answer_type": type_summary,
        "preflight": preflight,
    }
    write_json(REPORTS_DIR / "evaluation_comparison_summary.json", report)
    write_markdown_report(report, comparison_rows, type_summary)
    update_evaluation_doc(report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-id", default="HuggingFaceTB/SmolLM2-135M-Instruct")
    parser.add_argument("--adapter-path", default="checkpoints/smollm2_135m_lora_run_001")
    parser.add_argument("--max-prompts", type=int, default=20)
    parser.add_argument("--max-new-tokens", type=int, default=48)
    args = parser.parse_args()

    if args.max_prompts < 1 or args.max_prompts > 20:
        raise SystemExit("--max-prompts must be between 1 and 20 for this fixed evaluation set")
    if args.max_new_tokens < 1 or args.max_new_tokens > 64:
        raise SystemExit("--max-new-tokens must be between 1 and 64 for this safe run")
    report = evaluate(
        model_id=args.model_id,
        adapter_path=PROJECT_ROOT / args.adapter_path,
        max_prompts=args.max_prompts,
        max_new_tokens=args.max_new_tokens,
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
