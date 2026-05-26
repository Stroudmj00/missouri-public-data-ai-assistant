"""Build and query selected Missouri agriculture data from data.mo.gov."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw_public" / "data_mo_agriculture"
INDEX_PATH = RAW_DIR / "data_mo_agriculture_index.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "data_mo_agriculture_index_report.json"
DATASET_ID = "y9w9-qkg2"
DATASET_NAME = "Missouri Department of Agriculture - feed sample testing results"
DATA_URL = f"https://data.mo.gov/resource/{DATASET_ID}.json"
LANDING_PAGE = f"https://data.mo.gov/d/{DATASET_ID}"
METADATA_URL = f"https://data.mo.gov/api/views/{DATASET_ID}.json"

NUTRIENT_FIELDS = {
    "protein": ("prot", "protein"),
    "fiber": ("fiber", "fiber"),
    "fat": ("fat_ee", "fat ether extract"),
    "moisture": ("moist", "moisture"),
    "calcium": ("ca_min", "calcium minimum"),
    "phosphorus": ("p", "phosphorus"),
    "aflatoxin": ("afl", "aflatoxin"),
    "don": ("don", "DON/vomitoxin"),
    "fumonisin": ("fum", "fumonisin"),
}

GENERIC_FEED_TOKENS = {
    "AGRICULTURE",
    "CLASS",
    "DATA",
    "FEED",
    "INDEX",
    "INDEXED",
    "MISSOURI",
    "MO",
    "REPORT",
    "RESULT",
    "RESULTS",
    "SAMPLE",
    "SAMPLES",
    "TEST",
    "TESTING",
    "THE",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_text(value: str) -> str:
    cleaned = re.sub(r"[^A-Z0-9&./-]+", " ", clean_text(value).upper())
    return re.sub(r"\s+", " ", cleaned).strip()


def feed_tokens(value: str) -> set[str]:
    return {token for token in normalize_text(value).split() if token not in GENERIC_FEED_TOKENS}


def rows_updated_label(value: Any) -> str | None:
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).replace(microsecond=0).isoformat()


def date_year(value: str) -> int | None:
    match = re.search(r"\b(20\d{2})\b", value)
    return int(match.group(1)) if match else None


def nutrient_values(row: dict[str, Any]) -> dict[str, dict[str, str]]:
    nutrients: dict[str, dict[str, str]] = {}
    for key, (prefix, label) in NUTRIENT_FIELDS.items():
        guarantee = clean_text(row.get(f"{prefix}_guar"))
        result = clean_text(row.get(f"{prefix}_rslt"))
        unit = clean_text(row.get(f"{prefix}_unit"))
        if guarantee or result:
            nutrients[key] = {
                "label": label,
                "guarantee": guarantee,
                "result": result,
                "unit": unit,
            }
    return nutrients


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    sample_id = clean_text(row.get("sampleid")).upper()
    feed_class = clean_text(row.get("class_"))
    brand = clean_text(row.get("brandname")).upper()
    taken_date = clean_text(row.get("takendate"))
    complete_date = clean_text(row.get("completedate"))
    return {
        "sample_key": clean_text(row.get("samplekey")),
        "sample_id": sample_id,
        "class": feed_class,
        "class_norm": normalize_text(feed_class),
        "brand_name": brand,
        "brand_norm": normalize_text(brand),
        "wholesaler_business_name": clean_text(row.get("wholesalerbusinessname")).upper(),
        "retailer_business_name": clean_text(row.get("retailerbusinessname")).upper(),
        "taken_date": taken_date,
        "taken_year": date_year(taken_date),
        "complete_date": complete_date,
        "nutrients": nutrient_values(row),
        "source_url": DATA_URL,
        "landing_page": LANDING_PAGE,
    }


def top_counts(counter: Counter[str], limit: int = 12) -> list[dict[str, Any]]:
    return [
        {"label": label, "count": count}
        for label, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:limit]
        if label
    ]


def build_data_mo_agriculture_index(force: bool = False) -> dict[str, Any]:
    if INDEX_PATH.exists() and not force:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (compatible; MissouriPublicDataAssistant/1.0)",
            "Accept": "application/json,*/*;q=0.8",
        }
    )
    start = time.perf_counter()
    metadata_response = session.get(METADATA_URL, timeout=60)
    metadata_response.raise_for_status()
    metadata = metadata_response.json()
    response = session.get(DATA_URL, params={"$limit": 50000}, timeout=90)
    response.raise_for_status()
    raw_text = response.text
    raw_rows = response.json()
    records = sorted(
        [normalize_row(row) for row in raw_rows],
        key=lambda item: (item["taken_year"] or 0, item["class"], item["brand_name"], item["sample_id"]),
        reverse=True,
    )
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    write_json(RAW_DIR / "feed_sample_testing_results.json", raw_rows)
    class_counts = Counter(record["class"] for record in records if record.get("class"))
    year_counts = Counter(str(record["taken_year"]) for record in records if record.get("taken_year"))
    latest_year = max((record["taken_year"] for record in records if record.get("taken_year")), default=None)
    latest_records = [record for record in records if record.get("taken_year") == latest_year]
    latest_class_counts = Counter(record["class"] for record in latest_records if record.get("class"))
    payload = {
        "generated_at_utc": utc_now(),
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "source": DATASET_NAME,
        "source_url": DATA_URL,
        "landing_page": LANDING_PAGE,
        "metadata_url": METADATA_URL,
        "index_path": str(INDEX_PATH.relative_to(PROJECT_ROOT)),
        "dataset_id": DATASET_ID,
        "rows_updated_at_utc": rows_updated_label(metadata.get("rowsUpdatedAt")),
        "bytes": len(raw_text.encode("utf-8")),
        "sha256": sha256_text(raw_text),
        "record_count": len(records),
        "class_count": len(class_counts),
        "year_range": [
            min((record["taken_year"] for record in records if record.get("taken_year")), default=None),
            max((record["taken_year"] for record in records if record.get("taken_year")), default=None),
        ],
        "latest_year": latest_year,
        "latest_year_records": len(latest_records),
        "columns": [column.get("name") for column in metadata.get("columns", []) if column.get("name")],
        "top_classes": top_counts(class_counts),
        "top_years": top_counts(year_counts),
        "top_latest_year_classes": top_counts(latest_class_counts),
        "records": records,
    }
    write_json(INDEX_PATH, payload)
    write_json(
        REPORT_PATH,
        {
            "generated_at_utc": payload["generated_at_utc"],
            "elapsed_seconds": payload["elapsed_seconds"],
            "source": payload["source"],
            "source_url": payload["source_url"],
            "landing_page": payload["landing_page"],
            "index_path": payload["index_path"],
            "dataset_id": payload["dataset_id"],
            "rows_updated_at_utc": payload["rows_updated_at_utc"],
            "bytes": payload["bytes"],
            "sha256": payload["sha256"],
            "record_count": payload["record_count"],
            "class_count": payload["class_count"],
            "year_range": payload["year_range"],
            "latest_year": payload["latest_year"],
            "latest_year_records": payload["latest_year_records"],
            "top_classes": payload["top_classes"],
            "top_years": payload["top_years"],
            "top_latest_year_classes": payload["top_latest_year_classes"],
        },
    )
    return payload


def asks_for_count(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["how many", "count", "number of", "total"])


def asks_for_top(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["top", "highest", "largest", "most"])


def sample_id_in_question(question: str) -> str | None:
    match = re.search(r"\bD\d{9}\b", question.upper())
    return match.group(0) if match else None


def nutrient_key_for_question(question: str) -> str | None:
    lowered = question.lower()
    if "protein" in lowered or re.search(r"\bprot\b", lowered):
        return "protein"
    if "fiber" in lowered:
        return "fiber"
    if "fat" in lowered:
        return "fat"
    if "moisture" in lowered:
        return "moisture"
    if "calcium" in lowered:
        return "calcium"
    if "phosphorus" in lowered:
        return "phosphorus"
    if "aflatoxin" in lowered:
        return "aflatoxin"
    if "vomitoxin" in lowered or re.search(r"\bdon\b", lowered):
        return "don"
    if "fumonisin" in lowered:
        return "fumonisin"
    return None


def render_nutrient(nutrient: dict[str, str], prefix: str = "") -> str:
    unit = f" {nutrient['unit']}" if nutrient.get("unit") else ""
    guarantee = nutrient.get("guarantee") or "not listed"
    result = nutrient.get("result") or "not listed"
    label = prefix or nutrient.get("label", "nutrient")
    return f"{label} guarantee: {guarantee}{unit}; result: {result}{unit}"


class DataMoAgricultureIndex:
    def __init__(self, path: Path = INDEX_PATH) -> None:
        self.path = path
        self._payload: dict[str, Any] | None = None

    def available(self) -> bool:
        return self.path.exists() and self.path.stat().st_size > 0

    def payload(self) -> dict[str, Any]:
        if self._payload is None:
            self._payload = json.loads(self.path.read_text(encoding="utf-8")) if self.available() else {}
        return self._payload

    def records(self) -> list[dict[str, Any]]:
        return list(self.payload().get("records", []))

    def citation(self, matched_rows: int = 0) -> list[dict[str, Any]]:
        payload = self.payload()
        return [
            {
                "dataset": payload.get("source", DATASET_NAME),
                "category": "Agriculture",
                "kind": "feed sample testing row",
                "lookup_table": "data_mo_agriculture_index",
                "year": None,
                "year_range": payload.get("year_range"),
                "source_files": [
                    {
                        "category": "feed_sample_testing_results",
                        "category_label": payload.get("source", DATASET_NAME),
                        "file_name": payload.get("source_url", DATA_URL),
                        "row_count": payload.get("record_count"),
                        "bytes": payload.get("bytes"),
                        "sha256": payload.get("sha256"),
                    },
                    {
                        "category": "feed_sample_testing_results",
                        "category_label": "data.mo.gov landing page",
                        "file_name": payload.get("landing_page", LANDING_PAGE),
                        "row_count": None,
                        "bytes": None,
                        "sha256": None,
                    },
                ],
                "source_file_count": 2,
                "source_rows": payload.get("record_count"),
                "matched_rows": matched_rows,
            }
        ]

    def unavailable_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "The selected data.mo.gov agriculture index has not been built yet. Run "
                "`python scripts/build_data_mo_agriculture_index.py --force` to download the public feed sample table and build exact lookups."
            ),
            "retrieved_context_id": "data_mo_agriculture_index:missing",
            "retrieved_source": "data_mo_agriculture_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "The agriculture route exists, but the local ignored index is missing.",
            "citations": [],
            "source_rows": [],
        }

    def summary_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        top = "; ".join(f"{item['label']}: {item['count']}" for item in payload.get("top_classes", [])[:5])
        year_range = payload.get("year_range") or [None, None]
        return {
            "question": question,
            "answer": (
                f"The selected agriculture/feed exact lookup layer indexes the data.mo.gov {payload.get('source', DATASET_NAME)} table. "
                f"It contains {payload.get('record_count', 0):,} public feed sample testing rows across "
                f"{payload.get('class_count', 0):,} feed classes from {year_range[0]} to {year_range[1]}. "
                f"Latest indexed sample year: {payload.get('latest_year')} with {payload.get('latest_year_records', 0):,} row(s). "
                f"It can answer sample ID lookups, feed class counts, class rankings, and selected nutrient guarantee/result questions. "
                f"Top feed classes: {top}."
            ),
            "retrieved_context_id": "data_mo_agriculture_index:summary",
            "retrieved_source": "data_mo_agriculture_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local data.mo.gov agriculture feed-sample index.",
            "citations": self.citation(matched_rows=payload.get("record_count", 0)),
            "source_rows": [],
        }

    def find_by_sample_id(self, sample_id: str) -> dict[str, Any] | None:
        for record in self.records():
            if record.get("sample_id") == sample_id:
                return record
        return None

    def class_from_question(self, question: str) -> str | None:
        question_norm = normalize_text(question)
        classes = sorted({record["class"] for record in self.records() if record.get("class")}, key=len, reverse=True)
        for feed_class in classes:
            if re.search(rf"\b{re.escape(normalize_text(feed_class))}\b", question_norm):
                return feed_class
        return None

    def records_for_class(self, feed_class: str) -> list[dict[str, Any]]:
        return [record for record in self.records() if record.get("class") == feed_class]

    def find_by_brand(self, question: str) -> dict[str, Any] | None:
        question_norm = normalize_text(question)
        question_tokens = feed_tokens(question)
        candidates: list[tuple[int, dict[str, Any]]] = []
        for record in self.records():
            brand_norm = record.get("brand_norm", "")
            tokens = feed_tokens(record.get("brand_name", ""))
            score = 0
            if brand_norm and brand_norm in question_norm:
                score += 100 + len(brand_norm)
            if tokens and tokens <= question_tokens:
                score += 40 + len(tokens)
            if tokens & question_tokens:
                score += len(tokens & question_tokens)
            if score >= 3:
                candidates.append((score, record))
        if not candidates:
            return None
        return sorted(candidates, key=lambda item: item[0], reverse=True)[0][1]

    def sample_answer(self, question: str, record: dict[str, Any]) -> dict[str, Any]:
        nutrient_key = nutrient_key_for_question(question)
        nutrient_text = ""
        if nutrient_key and nutrient_key in record.get("nutrients", {}):
            nutrient_text = " " + render_nutrient(record["nutrients"][nutrient_key], nutrient_key)
        else:
            rendered = [
                render_nutrient(nutrient, nutrient["label"])
                for nutrient in list(record.get("nutrients", {}).values())[:4]
            ]
            if rendered:
                nutrient_text = " Selected results: " + "; ".join(rendered) + "."
        return {
            "question": question,
            "answer": (
                f"The indexed feed sample {record['sample_id']} is {record['brand_name'] or 'an unnamed brand'} "
                f"in class {record['class'] or 'not listed'}, taken {record['taken_date'] or 'date not listed'} "
                f"and completed {record['complete_date'] or 'date not listed'}.{nutrient_text}"
            ),
            "retrieved_context_id": f"data_mo_agriculture_index:sample:{record['sample_id']}",
            "retrieved_source": "data_mo_agriculture_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local data.mo.gov agriculture feed-sample index.",
            "citations": self.citation(matched_rows=1),
            "source_rows": [{"source_file": DATA_URL, "values": record}],
        }

    def class_answer(self, question: str, feed_class: str) -> dict[str, Any]:
        records = self.records_for_class(feed_class)
        examples = "; ".join(f"{record['sample_id']} {record['brand_name']}" for record in records[:5])
        return {
            "question": question,
            "answer": (
                f"The indexed {DATASET_NAME} table lists {len(records):,} {feed_class} sample row(s). "
                f"Example samples: {examples}."
            ),
            "retrieved_context_id": f"data_mo_agriculture_index:class:{normalize_text(feed_class)}",
            "retrieved_source": "data_mo_agriculture_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local data.mo.gov agriculture feed-sample index.",
            "citations": self.citation(matched_rows=len(records)),
            "source_rows": [{"source_file": DATA_URL, "values": record} for record in records[:5]],
        }

    def rank_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        top = payload.get("top_classes", [])
        rendered = "; ".join(f"{item['label']}: {item['count']}" for item in top[:5])
        winner = top[0] if top else {"label": "unknown", "count": 0}
        return {
            "question": question,
            "answer": (
                f"In the indexed {DATASET_NAME} table, the feed class with the most rows is "
                f"{winner['label']}: {winner['count']} sample row(s). Top feed classes: {rendered}."
            ),
            "retrieved_context_id": "data_mo_agriculture_index:rank:feed_class",
            "retrieved_source": "data_mo_agriculture_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed by ranking feed classes in the local data.mo.gov agriculture index.",
            "citations": self.citation(matched_rows=payload.get("record_count", 0)),
            "source_rows": [{"source_file": DATA_URL, "values": item} for item in top[:5]],
        }

    def missing_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                f"I have indexed {DATASET_NAME}, but this question did not match a listed feed sample ID, feed class, brand, or supported ranking. "
                "Try `What agriculture feed testing data is indexed?`, `How many Poultry Feed samples are indexed?`, "
                "or `What are the protein values for sample D202500550?`."
            ),
            "retrieved_context_id": "data_mo_agriculture_index:no_match",
            "retrieved_source": "data_mo_agriculture_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Answered from agriculture coverage metadata because no exact row matched.",
            "citations": self.citation(),
            "source_rows": [],
        }

    def answer(self, question: str) -> dict[str, Any] | None:
        if not self.available():
            return self.unavailable_answer(question)
        lowered = question.lower()
        if (
            re.search(r"\b(agriculture|feed|feed sample|feed testing)\b.*\b(indexed|lookup|data)\b", lowered)
            and not asks_for_top(question)
        ):
            if sample_id_in_question(question) is None and self.class_from_question(question) is None and self.find_by_brand(question) is None:
                return self.summary_answer(question)
        sample_id = sample_id_in_question(question)
        if sample_id:
            record = self.find_by_sample_id(sample_id)
            return self.sample_answer(question, record) if record else self.missing_answer(question)
        if asks_for_top(question):
            return self.rank_answer(question)
        feed_class = self.class_from_question(question)
        if feed_class:
            return self.class_answer(question, feed_class)
        brand_record = self.find_by_brand(question)
        if brand_record:
            return self.sample_answer(question, brand_record)
        return self.missing_answer(question)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    payload = build_data_mo_agriculture_index(force=args.force)
    print(json.dumps({key: value for key, value in payload.items() if key != "records"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
