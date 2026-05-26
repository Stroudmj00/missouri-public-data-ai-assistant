"""Build and query Missouri Agricultural Market News report metadata."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw_public" / "ag_market_news"
INDEX_PATH = RAW_DIR / "ag_market_news_index.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "ag_market_news_index_report.json"
LANDING_PAGE = "https://agmarketnews.mo.gov/reports/"
SOURCE_NAME = "Missouri Agricultural Market News reports"

TOKEN_PATTERN = re.compile(
    r"<h([23])[^>]*>(.*?)</h\1>|<a\s+[^>]*href=['\"]([^'\"]+)['\"][^>]*>(.*?)</a>",
    re.I | re.S,
)
REPORT_CODE_PATTERN = re.compile(r"\b(?:ams|AMS)_(\d{4})\b")
SCHEDULE_PATTERN = re.compile(r"\(([^()]+)\)")

GENERIC_SEARCH_TOKENS = {
    "AG",
    "AGRICULTURAL",
    "AGRICULTURE",
    "AND",
    "AUCTION",
    "CATTLE",
    "DATA",
    "FEEDSTUFF",
    "FORAGE",
    "FOR",
    "GIVE",
    "GOAT",
    "GRAIN",
    "HAY",
    "HEIFER",
    "INDEX",
    "INDEXED",
    "LINK",
    "LIVESTOCK",
    "MARKET",
    "ME",
    "MISSOURI",
    "MO",
    "NEWS",
    "PIG",
    "REPORT",
    "REPORTS",
    "SHEEP",
    "SHOW",
    "SWINE",
    "THE",
    "WHAT",
    "WHICH",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def clean_text(value: Any) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", str(value or ""), flags=re.S)
    decoded = html.unescape(without_tags).replace("\xa0", " ")
    return re.sub(r"\s+", " ", decoded).strip()


def normalize_text(value: Any) -> str:
    cleaned = re.sub(r"[^A-Z0-9&/-]+", " ", clean_text(value).upper())
    return re.sub(r"\s+", " ", cleaned).strip()


def search_tokens(value: Any) -> set[str]:
    return {
        token
        for token in normalize_text(value).replace("/", " ").replace("-", " ").split()
        if token and token not in GENERIC_SEARCH_TOKENS and len(token) > 2
    }


def report_code(url: str) -> str | None:
    match = REPORT_CODE_PATTERN.search(url)
    return f"ams_{match.group(1)}" if match else None


def infer_schedule(label: str, category: str) -> str | None:
    matches = [clean_text(match.group(1)) for match in SCHEDULE_PATTERN.finditer(f"{label} {category}")]
    if not matches:
        return None
    return matches[-1]


def infer_location(label: str) -> str | None:
    parts = [clean_text(part) for part in label.split(" - ") if clean_text(part)]
    if len(parts) >= 2:
        location = parts[-1]
        if not SCHEDULE_PATTERN.search(location):
            return location
    return None


def infer_commodity(category: str, label: str) -> str:
    combined = f"{category} {label}".lower()
    if re.search(r"\b(swine|hog|hogs|boar|boars|pig|pigs)\b", combined):
        return "swine"
    if "sheep" in combined or "goat" in combined:
        return "sheep/goats"
    if "hay" in combined or "forage" in combined:
        return "hay/forages"
    if "feedstuff" in combined or "mill-feed" in combined or "by-product" in combined:
        return "feedstuffs"
    if "grain" in combined or "oilseed" in combined:
        return "grain"
    if "heifer" in combined:
        return "show me select heifers"
    if "cattle" in combined or "livestock" in combined or "stocker" in combined or "feeder" in combined:
        return "cattle/livestock"
    if "crop progress" in combined:
        return "crop progress"
    return "market resource"


def source_type(url: str) -> str:
    parsed = urlparse(url)
    if parsed.path.lower().endswith(".pdf"):
        return "pdf_link"
    if "mymarketnews.ams.usda.gov" in parsed.netloc:
        return "usda_dashboard"
    if parsed.netloc.endswith("agmarketnews.mo.gov"):
        return "missouri_page"
    if "nass.usda.gov" in parsed.netloc:
        return "usda_nass_page"
    if "ams.usda.gov" in parsed.netloc:
        return "usda_ams_page"
    return "external_page"


def parse_report_links(page_text: str) -> list[dict[str, Any]]:
    start = page_text.find("Market Resources")
    end = page_text.find("Browse Reports")
    body = page_text[start:end] if start >= 0 and end > start else page_text
    category: str | None = None
    region: str | None = None
    records: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for match in TOKEN_PATTERN.finditer(body):
        if match.group(1):
            heading = clean_text(match.group(2))
            if match.group(1) == "2":
                category = heading
                region = None
            else:
                region = heading
            continue

        if category is None:
            continue
        href = match.group(3)
        label = clean_text(match.group(4))
        if not label or href.startswith("#"):
            continue
        absolute = urljoin(LANDING_PAGE, href)
        if absolute in seen_urls:
            continue
        seen_urls.add(absolute)
        commodity = infer_commodity(category, label)
        code = report_code(absolute)
        records.append(
            {
                "report_id": code or normalize_text(label).lower().replace(" ", "-")[:90],
                "report_code": code,
                "label": label,
                "category": category,
                "region": region,
                "commodity": commodity,
                "schedule": infer_schedule(label, category),
                "location": infer_location(label),
                "url": absolute,
                "source_type": source_type(absolute),
                "source_host": urlparse(absolute).netloc,
                "source_page": LANDING_PAGE,
            }
        )
    return records


def top_counts(counter: Counter[str], limit: int = 12) -> list[dict[str, Any]]:
    return [
        {"label": label, "count": count}
        for label, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:limit]
        if label
    ]


def build_ag_market_news_index(force: bool = False) -> dict[str, Any]:
    if INDEX_PATH.exists() and not force:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (compatible; MissouriPublicDataAssistant/1.0)",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        }
    )
    start = time.perf_counter()
    response = session.get(LANDING_PAGE, timeout=60)
    response.raise_for_status()
    page_text = response.text
    records = parse_report_links(page_text)
    categories = Counter(record["category"] for record in records if record.get("category"))
    commodities = Counter(record["commodity"] for record in records if record.get("commodity"))
    regions = Counter(record["region"] for record in records if record.get("region"))
    source_types = Counter(record["source_type"] for record in records if record.get("source_type"))
    hosts = Counter(record["source_host"] for record in records if record.get("source_host"))

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_DIR / "ag_market_news_reports_page.html").write_text(page_text, encoding="utf-8")
    payload = {
        "generated_at_utc": utc_now(),
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "source": SOURCE_NAME,
        "landing_page": LANDING_PAGE,
        "index_path": str(INDEX_PATH.relative_to(PROJECT_ROOT)),
        "bytes": len(page_text.encode("utf-8", errors="replace")),
        "sha256": sha256_text(page_text),
        "record_count": len(records),
        "pdf_count": sum(1 for record in records if record.get("source_type") == "pdf_link"),
        "category_count": len(categories),
        "commodity_count": len(commodities),
        "region_count": len(regions),
        "top_categories": top_counts(categories),
        "top_commodities": top_counts(commodities),
        "top_regions": top_counts(regions),
        "source_type_counts": dict(sorted(source_types.items())),
        "source_host_counts": dict(sorted(hosts.items())),
        "notes": [
            "This index stores Agricultural Market News report-link metadata only.",
            "It does not download or interpret USDA AMS PDF contents, prices, receipts, weights, or market commentary.",
            "Exact price and volume answers require dedicated parsers for selected report PDFs or dashboards.",
        ],
        "records": records,
    }
    write_json(INDEX_PATH, payload)
    write_json(REPORT_PATH, {key: value for key, value in payload.items() if key != "records"})
    return payload


def asks_for_summary(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["indexed", "connected", "available", "coverage", "what data", "what reports"])


def commodity_terms(question: str) -> set[str]:
    lowered = question.lower()
    terms: set[str] = set()
    if any(term in lowered for term in ["cattle", "livestock", "feeder", "stocker", "cow", "bull"]):
        terms.add("cattle/livestock")
    if any(term in lowered for term in ["swine", "hog", "boar", "pig"]):
        terms.add("swine")
    if "sheep" in lowered or "goat" in lowered:
        terms.add("sheep/goats")
    if "hay" in lowered or "forage" in lowered:
        terms.add("hay/forages")
    if "feedstuff" in lowered or "feedstuffs" in lowered or "mill-feed" in lowered:
        terms.add("feedstuffs")
    if "grain" in lowered or "oilseed" in lowered:
        terms.add("grain")
    if "heifer" in lowered:
        terms.add("show me select heifers")
    if "crop" in lowered:
        terms.add("crop progress")
    return terms


class AgMarketNewsIndex:
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
                "dataset": payload.get("source", SOURCE_NAME),
                "category": "Agriculture",
                "kind": "Agricultural Market News report metadata",
                "lookup_table": "ag_market_news_index",
                "year": None,
                "year_range": None,
                "source_files": [
                    {
                        "category": "ag_market_news",
                        "category_label": "Missouri Agricultural Market News reports page",
                        "file_name": payload.get("landing_page", LANDING_PAGE),
                        "row_count": payload.get("record_count"),
                        "bytes": payload.get("bytes"),
                        "sha256": payload.get("sha256"),
                    }
                ],
                "source_file_count": 1,
                "source_rows": payload.get("record_count"),
                "matched_rows": matched_rows,
            }
        ]

    def unavailable_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "The Agricultural Market News report metadata index has not been built yet. Run "
                "`python scripts/build_ag_market_news_index.py --force` to index the official report links."
            ),
            "retrieved_context_id": "ag_market_news_index:missing",
            "retrieved_source": "ag_market_news_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "The Agricultural Market News route exists, but the local ignored index is missing.",
            "citations": [],
            "source_rows": [],
        }

    def summary_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        categories = "; ".join(f"{item['label']}: {item['count']}" for item in payload.get("top_categories", [])[:5])
        commodities = "; ".join(f"{item['label']}: {item['count']}" for item in payload.get("top_commodities", [])[:6])
        return {
            "question": question,
            "answer": (
                "The Missouri Agricultural Market News exact metadata layer indexes official report and resource links from "
                f"{payload.get('source', SOURCE_NAME)}. It contains {payload.get('record_count', 0):,} report/resource link(s), "
                f"including {payload.get('pdf_count', 0):,} PDF link(s), across {payload.get('category_count', 0)} category group(s). "
                f"Top categories: {categories}. Commodity groups: {commodities}. "
                "It can answer which report links exist for cattle/livestock, swine, sheep/goats, hay/forages, feedstuffs, grain, and named markets. "
                "It does not parse prices from the linked PDFs."
            ),
            "retrieved_context_id": "ag_market_news_index:summary",
            "retrieved_source": "ag_market_news_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local Agricultural Market News report metadata index.",
            "citations": self.citation(matched_rows=payload.get("record_count", 0)),
            "source_rows": [],
        }

    def rows_for_question(self, question: str) -> list[dict[str, Any]]:
        records = self.records()
        lowered = question.lower()
        code_match = REPORT_CODE_PATTERN.search(question)
        if code_match:
            code = f"ams_{code_match.group(1)}"
            return [record for record in records if record.get("report_code") == code]
        commodities = commodity_terms(question)
        if commodities:
            records = [record for record in records if record.get("commodity") in commodities]
        if any(term in lowered for term in ["daily", "weekly", "monthly", "seasonal", "monday", "tuesday", "wednesday", "thursday", "friday"]):
            schedule_terms = {
                "daily": "daily",
                "weekly": "weekly",
                "monthly": "monthly",
                "seasonal": "seasonal",
                "monday": "mon",
                "tuesday": "tue",
                "wednesday": "wed",
                "thursday": "thu",
                "friday": "fri",
            }
            wanted = {value for key, value in schedule_terms.items() if key in lowered}
            records = [record for record in records if any(value in str(record.get("schedule", "")).lower() for value in wanted)]
        question_tokens = search_tokens(question)
        if question_tokens:
            scored: list[tuple[int, dict[str, Any]]] = []
            for record in records:
                blob = " ".join(
                    str(record.get(key, ""))
                    for key in ["label", "category", "region", "location", "commodity", "report_code"]
                )
                tokens = search_tokens(blob)
                overlap = question_tokens & tokens
                score = len(overlap)
                if normalize_text(record.get("label", "")) in normalize_text(question):
                    score += 10
                if score > 0:
                    scored.append((score, record))
            if scored:
                ranked = sorted(scored, key=lambda item: (-item[0], item[1]["label"]))
                best_score = ranked[0][0]
                records = [record for score, record in ranked if score == best_score]
        return records

    def rows_answer(self, question: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
        if not rows:
            return self.missing_answer(question)
        matched_count = len(rows)
        preview = rows[:5]
        rendered = "; ".join(
            f"{row['label']} ({row['commodity']}, {row.get('region') or 'statewide/resource'}): {row['url']}"
            for row in preview
        )
        return {
            "question": question,
            "answer": f"Showing {len(preview)} of {matched_count} matching Agricultural Market News report metadata row(s): {rendered}.",
            "retrieved_context_id": "ag_market_news_index:match",
            "retrieved_source": "ag_market_news_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local Agricultural Market News report metadata index.",
            "citations": self.citation(matched_rows=matched_count),
            "source_rows": [{"source_file": row["source_page"], "values": row} for row in preview],
        }

    def missing_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "I have indexed Missouri Agricultural Market News report-link metadata, but this question did not match a supported "
                "commodity group, named market, report code, schedule, or report label. Try `What agriculture market reports are indexed?`, "
                "`What swine market reports are indexed?`, or `Give me the link for the Joplin Regional Stockyards feeder cattle report.`"
            ),
            "retrieved_context_id": "ag_market_news_index:no_match",
            "retrieved_source": "ag_market_news_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Answered from Agricultural Market News coverage metadata because no exact report row matched.",
            "citations": self.citation(),
            "source_rows": [],
        }

    def answer(self, question: str) -> dict[str, Any] | None:
        if not self.available():
            return self.unavailable_answer(question)
        if asks_for_summary(question) and not commodity_terms(question) and not REPORT_CODE_PATTERN.search(question):
            return self.summary_answer(question)
        rows = self.rows_for_question(question)
        if rows:
            return self.rows_answer(question, rows)
        if asks_for_summary(question):
            return self.summary_answer(question)
        return self.missing_answer(question)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    payload = build_ag_market_news_index(force=args.force)
    print(json.dumps({key: value for key, value in payload.items() if key != "records"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
