"""Generate expanded MAP QA examples from the local public lookup index."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

from missouri_public_data_ai.map_public_index import INDEX_PATH, PROJECT_ROOT, format_money


TRAIN_PATH = PROJECT_ROOT / "data" / "qa" / "train_map_run_002.jsonl"
EVAL_PATH = PROJECT_ROOT / "data" / "qa" / "eval_map_run_002.jsonl"


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def qa_row(item_id: str, source: str, question: str, answer: str, context: str, split: str) -> dict[str, Any]:
    return {
        "id": item_id,
        "source": source,
        "question": question,
        "answer": answer,
        "context": context,
        "split": split,
        "answer_type": "short_fact",
        "safety": "public MAP aggregate/source QA; exact row-level records are served by deterministic lookup",
    }


def query_rows(conn: sqlite3.Connection, kind: str, limit: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        select kind, year, display_name, amount, row_count
        from public_amount_lookup
        where kind = ? and amount > 0
        order by year desc, amount desc
        limit ?
        """,
        [kind, limit],
    ).fetchall()


def build_rows(train_limit: int, eval_limit: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not INDEX_PATH.exists():
        raise FileNotFoundError(f"Build the MAP public index first: {INDEX_PATH}")

    conn = sqlite3.connect(INDEX_PATH)
    conn.row_factory = sqlite3.Row
    summary = conn.execute(
        "select category, count(*) as files, sum(row_count) as rows from file_summary group by category order by category"
    ).fetchall()
    total_files = sum(row["files"] for row in summary)
    total_rows = sum(row["rows"] for row in summary)
    categories = ", ".join(row["category"] for row in summary)

    rows: list[dict[str, Any]] = [
        qa_row(
            "map_index_summary_001",
            "map_public_index",
            "How many MAP text files are covered by the local lookup index?",
            f"{total_files} text files.",
            f"The local MAP lookup index covers {total_files} text files and {total_rows:,} parsed rows.",
            "train",
        ),
        qa_row(
            "map_index_summary_002",
            "map_public_index",
            "Which MAP categories are indexed locally?",
            f"{categories}.",
            f"The local MAP lookup index categories are: {categories}.",
            "train",
        ),
        qa_row(
            "map_lookup_policy_001",
            "map_public_index",
            "Should exact named MAP employee pay questions be answered from model memory?",
            "No. Exact named employee pay questions should use deterministic lookup over the indexed public MAP employee files.",
            "The case-study architecture uses deterministic lookup for exact public records and model QA for short aggregate/source questions.",
            "train",
        ),
        qa_row(
            "map_lookup_policy_002",
            "map_public_index",
            "Should exact named vendor payment questions be answered from model memory?",
            "No. Exact named vendor payment questions should use deterministic lookup over the indexed public MAP expenditure files.",
            "The case-study architecture uses deterministic lookup for exact public records and model QA for short aggregate/source questions.",
            "train",
        ),
    ]

    specs = [
        ("expenditure_agency", "map_expenditures", "What was the MAP expenditure total for {name} in {year}?", "MAP expenditure agency"),
        ("expenditure_category", "map_expenditures", "What was the MAP expenditure total for the {name} category in {year}?", "MAP expenditure category"),
        ("federal_grant_agency", "map_federal_grants", "How much federal grant money did {name} receive in {year}?", "MAP federal grant agency"),
        ("tax_credit_category", "map_tax_credits", "What was the MAP tax credit issued amount for {name} in {year}?", "MAP tax credit category"),
        ("budget_restricted_agency", "map_budget_restrictions", "What was the MAP restricted amount for {name} in {year}?", "MAP budget restriction agency"),
    ]

    for kind, source, template, label in specs:
        for index, row in enumerate(query_rows(conn, kind, train_limit + eval_limit), start=1):
            split = "eval" if index > train_limit else "train"
            year = row["year"]
            name = row["display_name"]
            answer = f"{format_money(row['amount'])}."
            context = (
                f"In the indexed public {label} data, {name} has amount {format_money(row['amount'])} "
                f"for {year} across {row['row_count']:,} row(s)."
            )
            rows.append(
                qa_row(
                    f"{kind}_{year}_{index:03d}",
                    source,
                    template.format(name=name, year=year),
                    answer,
                    context,
                    split,
                )
            )
    conn.close()
    train_rows = [row for row in rows if row["split"] == "train"]
    eval_rows = [row for row in rows if row["split"] == "eval"]
    return train_rows, eval_rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-per-kind", type=int, default=60)
    parser.add_argument("--eval-per-kind", type=int, default=8)
    args = parser.parse_args()
    train_rows, eval_rows = build_rows(args.train_per_kind, args.eval_per_kind)
    write_jsonl(TRAIN_PATH, train_rows)
    write_jsonl(EVAL_PATH, eval_rows)
    print(
        json.dumps(
            {
                "train_path": str(TRAIN_PATH.relative_to(PROJECT_ROOT)),
                "eval_path": str(EVAL_PATH.relative_to(PROJECT_ROOT)),
                "train_rows": len(train_rows),
                "eval_rows": len(eval_rows),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
