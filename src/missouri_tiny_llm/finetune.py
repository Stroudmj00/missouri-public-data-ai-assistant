"""Conservative LoRA fine-tuning for the Missouri Tiny LLM case study."""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import psutil
import torch
import yaml
from peft import LoraConfig, TaskType, get_peft_model
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModelForCausalLM, AutoTokenizer, get_linear_schedule_with_warmup

from missouri_tiny_llm.baseline_inference import estimate_model_download_mb


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = PROJECT_ROOT / "docs"


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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def make_user_prompt(row: dict[str, Any]) -> str:
    return (
        "You are answering a narrow public-data QA question for an educational case study.\n"
        "Use only the provided context. If the answer is excluded or absent, say you do not know from the provided data.\n\n"
        f"Context: {row['context']}\n"
        f"Question: {row['question']}\n"
        "Answer briefly:"
    )


def render_texts(tokenizer: Any, row: dict[str, Any]) -> tuple[str, str]:
    user_prompt = make_user_prompt(row)
    answer = row["answer"]
    if getattr(tokenizer, "chat_template", None):
        prompt_text = tokenizer.apply_chat_template(
            [{"role": "user", "content": user_prompt}],
            tokenize=False,
            add_generation_prompt=True,
        )
        full_text = tokenizer.apply_chat_template(
            [
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": answer},
            ],
            tokenize=False,
            add_generation_prompt=False,
        )
        return prompt_text, full_text
    return user_prompt + "\n", user_prompt + "\n" + answer


class QADataset(Dataset[dict[str, torch.Tensor]]):
    def __init__(self, rows: list[dict[str, Any]], tokenizer: Any, max_seq_length: int) -> None:
        self.examples: list[dict[str, torch.Tensor]] = []
        for row in rows:
            prompt_text, full_text = render_texts(tokenizer, row)
            full = tokenizer(
                full_text,
                truncation=True,
                max_length=max_seq_length,
                padding="max_length",
                return_tensors="pt",
            )
            prompt = tokenizer(
                prompt_text,
                truncation=True,
                max_length=max_seq_length,
                padding=False,
                return_tensors="pt",
            )
            input_ids = full["input_ids"][0]
            attention_mask = full["attention_mask"][0]
            labels = input_ids.clone()
            prompt_len = min(prompt["input_ids"].shape[-1], max_seq_length)
            labels[:prompt_len] = -100
            labels[attention_mask == 0] = -100
            if torch.all(labels == -100):
                continue
            self.examples.append(
                {
                    "input_ids": input_ids,
                    "attention_mask": attention_mask,
                    "labels": labels,
                }
            )

    def __len__(self) -> int:
        return len(self.examples)

    def __getitem__(self, index: int) -> dict[str, torch.Tensor]:
        return self.examples[index]


@dataclass
class TrainResources:
    disk_free_gb: float
    ram_available_gb: float
    cuda_available: bool
    gpu_name: str | None
    gpu_total_vram_gb: float | None


def current_resources() -> TrainResources:
    disk = psutil.disk_usage("C:\\")
    memory = psutil.virtual_memory()
    if torch.cuda.is_available():
        props = torch.cuda.get_device_properties(0)
        gpu_name = props.name
        total = round(props.total_memory / 1024**3, 2)
    else:
        gpu_name = None
        total = None
    return TrainResources(
        disk_free_gb=round(disk.free / 1024**3, 2),
        ram_available_gb=round(memory.available / 1024**3, 2),
        cuda_available=torch.cuda.is_available(),
        gpu_name=gpu_name,
        gpu_total_vram_gb=total,
    )


def count_trainable_params(model: torch.nn.Module) -> tuple[int, int, float]:
    total = sum(param.numel() for param in model.parameters())
    trainable = sum(param.numel() for param in model.parameters() if param.requires_grad)
    pct = round(trainable / total * 100, 4) if total else 0
    return total, trainable, pct


def write_preflight(config: dict[str, Any], train_rows: int, eval_rows: int) -> dict[str, Any]:
    reports_dir = PROJECT_ROOT / config["reports_dir"]
    reports_dir.mkdir(parents=True, exist_ok=True)
    resources = current_resources()
    payload = {
        "generated_at_utc": utc_now(),
        "run_id": config["run_id"],
        "model_id": config["model_id"],
        "train_file": config["train_file"],
        "eval_file": config["eval_file"],
        "method": config["training"]["method"],
        "train_rows": train_rows,
        "eval_rows": eval_rows,
        "download_estimate": estimate_model_download_mb(config["model_id"]),
        "resource_snapshot": resources.__dict__,
        "limits": {
            "max_steps": config["training"]["max_steps"],
            "max_seq_length": config["training"]["max_seq_length"],
            "batch_size": config["training"]["batch_size"],
            "gradient_accumulation_steps": config["training"]["gradient_accumulation_steps"],
            "expected_runtime_minutes": config["training"]["expected_runtime_minutes"],
            "vram_stop_limit_mb": config["training"]["vram_stop_limit_mb"],
        },
        "safety": [
            "uses generated aggregate/source QA rather than raw-row memorization",
            "keeps exact public-record answers behind deterministic lookup",
            "does not train on full row-level MAP files as completion targets",
            "saves adapter/checkpoint under ignored checkpoints directory",
        ],
    }
    write_json(reports_dir / f"{config['run_id']}_preflight.json", payload)
    return payload


def plot_loss(metrics_path: Path, output_path: Path, title: str = "Training Loss") -> None:
    steps: list[int] = []
    losses: list[float] = []
    with metrics_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            steps.append(int(row["step"]))
            losses.append(float(row["loss"]))
    plt.figure(figsize=(7, 4))
    plt.plot(steps, losses, marker="o", linewidth=1.5)
    plt.title(title)
    plt.xlabel("Optimizer Step")
    plt.ylabel("Loss")
    plt.grid(True, alpha=0.25)
    plt.tight_layout()
    plt.savefig(output_path, dpi=160)
    plt.close()


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def train(config_path: Path) -> dict[str, Any]:
    config = load_config(config_path)
    reports_dir = PROJECT_ROOT / config["reports_dir"]
    output_dir = PROJECT_ROOT / config["output_dir"]
    reports_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    random.seed(config["seed"])
    torch.manual_seed(config["seed"])
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(config["seed"])

    train_rows = read_jsonl(PROJECT_ROOT / config["train_file"])
    eval_rows = read_jsonl(PROJECT_ROOT / config["eval_file"])
    preflight = write_preflight(config, len(train_rows), len(eval_rows))

    if not torch.cuda.is_available():
        raise SystemExit("CUDA is required for this safe configured run.")

    device = torch.device("cuda")
    started = time.perf_counter()
    tokenizer = AutoTokenizer.from_pretrained(config["model_id"])
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    dtype = torch.float16
    model = AutoModelForCausalLM.from_pretrained(
        config["model_id"],
        dtype=dtype,
        low_cpu_mem_usage=True,
    )
    if bool(config["training"].get("gradient_checkpointing", False)):
        model.gradient_checkpointing_enable()
        model.config.use_cache = False
    lora_cfg = config["lora"]
    peft_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=int(lora_cfg["r"]),
        lora_alpha=int(lora_cfg["alpha"]),
        lora_dropout=float(lora_cfg["dropout"]),
        target_modules=list(lora_cfg["target_modules"]),
        bias="none",
    )
    model = get_peft_model(model, peft_config)
    model.to(device)
    model.train()

    total_params, trainable_params, trainable_pct = count_trainable_params(model)

    training_cfg = config["training"]
    dataset = QADataset(train_rows, tokenizer, int(training_cfg["max_seq_length"]))
    if len(dataset) == 0:
        raise SystemExit("No trainable examples were produced after tokenization.")
    dataloader = DataLoader(dataset, batch_size=int(training_cfg["batch_size"]), shuffle=True)
    optimizer = torch.optim.AdamW(
        (param for param in model.parameters() if param.requires_grad),
        lr=float(training_cfg["learning_rate"]),
        weight_decay=float(training_cfg["weight_decay"]),
    )
    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=int(training_cfg["warmup_steps"]),
        num_training_steps=int(training_cfg["max_steps"]),
    )
    scaler = torch.amp.GradScaler("cuda")

    run_id = str(config["run_id"])
    metrics_path = reports_dir / f"{run_id}_metrics.csv"
    fieldnames = ["step", "loss", "lr", "elapsed_seconds", "peak_vram_mb"]
    max_steps = int(training_cfg["max_steps"])
    grad_accum = int(training_cfg["gradient_accumulation_steps"])
    log_every = int(training_cfg["log_every"])
    vram_stop_limit = float(training_cfg["vram_stop_limit_mb"])

    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()
    step = 0
    accum = 0
    micro_loss_sum = 0.0
    log_loss_sum = 0.0
    log_loss_count = 0
    data_iter = iter(dataloader)

    with metrics_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        optimizer.zero_grad(set_to_none=True)

        while step < max_steps:
            try:
                batch = next(data_iter)
            except StopIteration:
                data_iter = iter(dataloader)
                batch = next(data_iter)

            batch = {key: value.to(device) for key, value in batch.items()}
            with torch.amp.autocast("cuda", dtype=torch.float16):
                output = model(**batch)
                loss = output.loss / grad_accum
            scaler.scale(loss).backward()
            micro_loss_sum += float(loss.detach().cpu()) * grad_accum
            accum += 1

            if accum % grad_accum == 0:
                step_loss = micro_loss_sum / grad_accum
                micro_loss_sum = 0.0
                scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(model.parameters(), float(training_cfg["max_grad_norm"]))
                scaler.step(optimizer)
                scaler.update()
                scheduler.step()
                optimizer.zero_grad(set_to_none=True)
                step += 1

                peak_vram = (
                    round(torch.cuda.max_memory_allocated() / 1024**2, 2)
                    if torch.cuda.is_available()
                    else 0
                )
                log_loss_sum += step_loss
                log_loss_count += 1
                if step % log_every == 0 or step == 1 or step == max_steps:
                    writer.writerow(
                        {
                            "step": step,
                            "loss": round(log_loss_sum / max(log_loss_count, 1), 6),
                            "lr": scheduler.get_last_lr()[0],
                            "elapsed_seconds": round(time.perf_counter() - started, 3),
                            "peak_vram_mb": peak_vram,
                        }
                    )
                    handle.flush()
                    log_loss_sum = 0.0
                    log_loss_count = 0

                if peak_vram > vram_stop_limit:
                    raise RuntimeError(
                        f"Peak VRAM {peak_vram} MB exceeded configured limit {vram_stop_limit} MB"
                    )

    if bool(training_cfg["save_adapter"]):
        model.save_pretrained(output_dir)
        tokenizer.save_pretrained(output_dir)

    loss_chart = reports_dir / f"{run_id}_loss.png"
    plot_loss(metrics_path, loss_chart, title=f"{run_id.replace('_', ' ').title()} Loss")

    elapsed = round(time.perf_counter() - started, 3)
    peak_vram = (
        round(torch.cuda.max_memory_allocated() / 1024**2, 2) if torch.cuda.is_available() else None
    )
    adapter_size = sum(path.stat().st_size for path in output_dir.rglob("*") if path.is_file())
    summary = {
        "generated_at_utc": utc_now(),
        "run_id": config["run_id"],
        "config": str(config_path.relative_to(PROJECT_ROOT)),
        "model_id": config["model_id"],
        "adapter_dir": str(output_dir.relative_to(PROJECT_ROOT)),
        "train_rows": len(train_rows),
        "tokenized_train_examples": len(dataset),
        "eval_rows": len(eval_rows),
        "max_steps": max_steps,
        "elapsed_seconds": elapsed,
        "peak_allocated_vram_mb": peak_vram,
        "total_params": total_params,
        "trainable_params": trainable_params,
        "trainable_pct": trainable_pct,
        "adapter_size_mb": round(adapter_size / 1024**2, 3),
        "metrics_csv": str(metrics_path.relative_to(PROJECT_ROOT)),
        "loss_chart": str(loss_chart.relative_to(PROJECT_ROOT)),
        "preflight": preflight,
    }
    write_json(reports_dir / f"{run_id}_summary.json", summary)
    write_training_report(summary)
    update_model_card_after_training(summary)
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return summary


def write_training_report(summary: dict[str, Any]) -> None:
    run_title = summary["run_id"].replace("_", " ").title()
    train_file = summary["preflight"].get("train_file", "configured training file")
    content = f"""# {run_title}

Generated at: `{summary['generated_at_utc']}`

## Scope

This was a conservative LoRA fine-tuning run for the Missouri Tiny LLM case study. It trained only adapter weights on generated aggregate/source QA pairs.

## Configuration

- Base model: `{summary['model_id']}`
- Config: `{summary['config']}`
- Adapter output: `{summary['adapter_dir']}`
- Training rows: {summary['train_rows']}
- Tokenized training examples: {summary['tokenized_train_examples']}
- Max optimizer steps: {summary['max_steps']}
- Trainable parameters: {summary['trainable_params']:,} / {summary['total_params']:,} ({summary['trainable_pct']}%)

## Resource Usage

- Runtime: {summary['elapsed_seconds']} seconds
- Peak allocated VRAM: {summary['peak_allocated_vram_mb']} MB
- Adapter size: {summary['adapter_size_mb']} MB
- Loss chart: `{summary['loss_chart']}`
- Metrics CSV: `{summary['metrics_csv']}`

## Safety Boundary

- Input data was `{train_file}`
- Exact employee, vendor, customer, and other row-level public-record answers are handled by deterministic lookup
- Raw row-level records were not used as model memorization targets
- Raw public downloads remain ignored from Git

## Interpretation

This run is intentionally small. It is meant to prove the full training/evaluation loop and create a measured comparison point, not to produce a production assistant.
"""
    (PROJECT_ROOT / "reports" / f"{summary['run_id']}.md").write_text(content, encoding="utf-8")


def update_model_card_after_training(summary: dict[str, Any]) -> None:
    content = f"""# Model Card

## Current Model State

The project now has a small LoRA adapter trained on generated aggregate/source Missouri public-data QA pairs.

## Base Model

`{summary['model_id']}`

## Adapter

- Adapter path: `{summary['adapter_dir']}`
- Adapter size: {summary['adapter_size_mb']} MB
- Training rows: {summary['train_rows']}
- Max optimizer steps: {summary['max_steps']}
- Trainable parameters: {summary['trainable_params']:,} ({summary['trainable_pct']}% of total)
- Peak allocated VRAM during training: {summary['peak_allocated_vram_mb']} MB

## Intended Use

Educational case study for constrained QA over retrieved public-data snippets. Exact row-level MAP public records are answered by deterministic lookup over the local public index.

## Out Of Scope

- Production public-finance assistant
- Legal, procurement, financial, or employment advice
- Model-memory lookup for exact employee salary, vendor payment, customer tax-credit, or other row-level records
- State of Missouri endorsement or official representation

## Data Boundary

Training used `{summary['preflight'].get('train_file', 'the configured training file')}`. It did not train on raw MAP rows as memorization targets. The local UI uses `data/raw_public/map_public_lookup.sqlite` for exact public-record lookup.

## Evaluation

See `reports/evaluation_comparison.md` after running the before/after evaluation.
"""
    (DOCS_DIR / "MODEL_CARD.md").write_text(content, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/finetune_smollm2_135m_lora.yaml")
    args = parser.parse_args()
    summary = train(PROJECT_ROOT / args.config)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
