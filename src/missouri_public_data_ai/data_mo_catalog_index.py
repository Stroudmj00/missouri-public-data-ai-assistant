"""Build and query the State of Missouri data.mo.gov catalog metadata."""

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
RAW_DIR = PROJECT_ROOT / "data" / "raw_public" / "data_mo_catalog"
INDEX_PATH = RAW_DIR / "data_mo_catalog_index.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "data_mo_catalog_index_report.json"
DATA_JSON_URL = "https://data.mo.gov/data.json"

STOPWORDS = {
    "about",
    "available",
    "catalog",
    "cataloged",
    "connected",
    "data",
    "dataset",
    "datasets",
    "does",
    "find",
    "from",
    "gov",
    "have",
    "many",
    "mention",
    "mentions",
    "missouri",
    "open",
    "public",
    "show",
    "source",
    "sources",
    "state",
    "the",
    "there",
    "what",
    "which",
    "with",
}

KNOWN_EXACT_DATASET_CAPABILITIES = {
    "8yaf-xv66": (
        "exact high-school senior count lookup by school/year is implemented. "
        "Try asking: How many high school seniors did Columbia schools list?"
    ),
    "t9f4-ncza": (
        "exact completed-FAFSA lookup by school/year is implemented, with suppression-aware values. "
        "Try asking: Which school had the most completed FAFSA applications?"
    ),
    "fk75-fa28": (
        "exact communicable-disease aggregate lookup is implemented for current-week YTD counts, rates, medians, and rankings. "
        "Try asking: How many anaplasmosis cases are listed YTD?"
    ),
    "q8me-hzr8": (
        "exact hospital-profile lookup is implemented for facility, county, region, statewide licensed-bed totals, ICU beds, and largest-facility rankings. "
        "Try asking: Which hospital has the most licensed beds?"
    ),
    "diyi-fr2a": (
        "exact WIC aggregate lookup is implemented for county and municipality household rows, redeemed benefits, average benefits, and rankings. "
        "Try asking: How many WIC household rows are listed for Boone County?"
    ),
    "eb3y-vtsa": (
        "exact food-pantry lookup is implemented for county, city, agency, hours, phone, address, and top-county counts. "
        "Try asking: How many food pantries are listed in Boone County?"
    ),
    "fenu-sipv": (
        "exact long-term-care directory lookup is implemented for sanitized county, city, facility capacity, and level-of-care summaries. "
        "Try asking: How many LTC beds are listed in Boone County?"
    ),
    "bf8b-a47t": (
        "exact long-term-care census lookup is implemented for statewide occupancy, licensure-level totals, and region facts. "
        "Try asking: What is the statewide LTC census occupancy ratio?"
    ),
    "3mwf-kse4": (
        "exact public drinking-water system lookup is implemented for county counts, PWSID lookup, system-name lookup, and county rankings. "
        "Try asking: What is the PWSID for City of Columbia Utilities?"
    ),
    "y64b-aec2": (
        "exact oil-and-gas permit lookup is implemented for permit IDs, county/status counts, company/operator rankings, and permit PDF links. "
        "Try asking: What is DNR oil and gas permit 013-00120?"
    ),
    "m7dn-rv29": (
        "exact hazardous-waste facility lookup is implemented for EPA IDs, facility names, county/status counts, county rankings, and DNR region summaries. "
        "Try asking: What is listed for EPA ID MOD054950670?"
    ),
    "yeiz-h2m2": (
        "exact utility-provider lookup is implemented for city/county electric, gas, water, and telephone providers. "
        "Try asking: What utilities serve Columbia in Boone County?"
    ),
    "y9w9-qkg2": (
        "exact feed-sample testing lookup is implemented for sample IDs, feed class counts/rankings, and selected nutrient guarantee/result values. "
        "Try asking: What are the protein values for sample D202500550?"
    ),
    "2zg8-cta8": (
        "exact Missouri Farmers' Markets lookup is implemented for county counts, city lookups, public business/listing details, websites, addresses, and top-county rankings. "
        "Try asking: How many farmers markets are listed in Adair County?"
    ),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def clean_text(value: Any) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    return re.sub(r"\s+", " ", text).strip()


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def dataset_id(dataset: dict[str, Any]) -> str:
    for key in ("identifier", "landingPage"):
        value = str(dataset.get(key) or "")
        match = re.search(r"/(?:api/views|d)/([^/?#]+)", value)
        if match:
            return match.group(1)
    return clean_text(dataset.get("title", "unknown")).lower().replace(" ", "-")[:80] or "unknown"


def format_from_media_type(media_type: str) -> str:
    lowered = media_type.lower()
    if "csv" in lowered:
        return "CSV"
    if "json" in lowered:
        return "JSON"
    if "pdf" in lowered:
        return "PDF"
    if "xml" in lowered and "rdf" not in lowered:
        return "XML"
    if "rdf" in lowered:
        return "RDF"
    return media_type or "unknown"


def normalize_dataset(dataset: dict[str, Any]) -> dict[str, Any]:
    distributions = []
    for item in as_list(dataset.get("distribution")):
        if not isinstance(item, dict):
            continue
        media_type = clean_text(item.get("mediaType"))
        distributions.append(
            {
                "download_url": clean_text(item.get("downloadURL")),
                "media_type": media_type,
                "format": format_from_media_type(media_type),
                "described_by": clean_text(item.get("describedBy")),
            }
        )
    themes = [clean_text(item) for item in as_list(dataset.get("theme")) if clean_text(item)]
    keywords = [clean_text(item) for item in as_list(dataset.get("keyword")) if clean_text(item)]
    if not themes:
        themes = ["uncategorized"]
    formats = sorted({item["format"] for item in distributions if item.get("format")})
    record = {
        "id": dataset_id(dataset),
        "title": clean_text(dataset.get("title")),
        "description": clean_text(dataset.get("description")),
        "themes": themes,
        "keywords": keywords,
        "modified": clean_text(dataset.get("modified")),
        "identifier": clean_text(dataset.get("identifier")),
        "landing_page": clean_text(dataset.get("landingPage")),
        "publisher": clean_text((dataset.get("publisher") or {}).get("name") if isinstance(dataset.get("publisher"), dict) else ""),
        "distribution_count": len(distributions),
        "formats": formats,
        "distributions": distributions,
    }
    record["search_blob"] = " ".join(
        [
            record["id"],
            record["title"],
            record["description"],
            " ".join(record["themes"]),
            " ".join(record["keywords"]),
            " ".join(item.get("download_url", "") for item in distributions),
        ]
    ).lower()
    return record


def build_data_mo_catalog_index(force: bool = False) -> dict[str, Any]:
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
    response = session.get(DATA_JSON_URL, timeout=90)
    response.raise_for_status()
    raw_text = response.text
    catalog = response.json()
    records = [normalize_dataset(dataset) for dataset in catalog.get("dataset", []) if isinstance(dataset, dict)]

    theme_counts = Counter(theme for record in records for theme in record["themes"])
    format_counts = Counter(format_name for record in records for format_name in record["formats"])
    with_distribution = [record for record in records if record["distribution_count"] > 0]
    payload = {
        "generated_at_utc": utc_now(),
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "source": "State of Missouri data.mo.gov catalog",
        "source_url": DATA_JSON_URL,
        "index_path": str(INDEX_PATH.relative_to(PROJECT_ROOT)),
        "catalog_bytes": len(raw_text.encode("utf-8")),
        "catalog_sha256": sha256_text(raw_text),
        "dataset_count": len(records),
        "datasets_with_distribution": len(with_distribution),
        "theme_counts": dict(sorted(theme_counts.items(), key=lambda item: (-item[1], item[0]))),
        "top_themes": [
            {"label": label, "count": count}
            for label, count in sorted(theme_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        "format_counts": dict(sorted(format_counts.items(), key=lambda item: (-item[1], item[0]))),
        "top_formats": [
            {"label": label, "count": count}
            for label, count in sorted(format_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
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
            "index_path": payload["index_path"],
            "catalog_bytes": payload["catalog_bytes"],
            "catalog_sha256": payload["catalog_sha256"],
            "dataset_count": payload["dataset_count"],
            "datasets_with_distribution": payload["datasets_with_distribution"],
            "theme_counts": payload["theme_counts"],
            "top_themes": payload["top_themes"],
            "format_counts": payload["format_counts"],
            "top_formats": payload["top_formats"],
            "sample_records": [
                {
                    "id": record["id"],
                    "title": record["title"],
                    "themes": record["themes"],
                    "formats": record["formats"],
                    "landing_page": record["landing_page"],
                }
                for record in records[:12]
            ],
        },
    )
    return payload


def requested_limit(question: str, default: int = 5, maximum: int = 10) -> int:
    match = re.search(r"\b(?:top|first|show(?: me)?|list)\s+(\d{1,2})\b", question.lower())
    if match:
        return max(1, min(maximum, int(match.group(1))))
    return default


def search_terms(question: str) -> list[str]:
    lowered = question.lower().replace("data.mo.gov", " ")
    tokens = re.findall(r"[a-z0-9]+", lowered)
    return [token for token in tokens if len(token) > 2 and token not in STOPWORDS]


def format_list(values: list[str], fallback: str = "none listed") -> str:
    return ", ".join(values) if values else fallback


def usefulness_note(records: list[dict[str, Any]]) -> str:
    connected = []
    for record in records:
        capability = KNOWN_EXACT_DATASET_CAPABILITIES.get(record.get("id", ""))
        if capability:
            connected.append(f"{record['title']} ({record['id']}): {capability}")
    if connected:
        return "Usefulness: " + " ".join(connected[:3])
    return "Usefulness: these are catalog metadata matches; exact numeric answers still need a dedicated parser for the selected dataset."


class DataMoCatalogIndex:
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

    def coverage_citation(self, matched_rows: int = 0, source_files: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        files = source_files or [
            {
                "category": "data_mo_catalog",
                "category_label": "Official data.mo.gov DCAT catalog",
                "file_name": DATA_JSON_URL,
                "row_count": self.payload().get("dataset_count"),
                "bytes": self.payload().get("catalog_bytes"),
                "sha256": self.payload().get("catalog_sha256"),
            }
        ]
        return [
            {
                "dataset": "State of Missouri data.mo.gov catalog",
                "category": "Open data catalog",
                "kind": "DCAT catalog metadata index",
                "lookup_table": "data_mo_catalog_index",
                "year": 2026,
                "year_range": None,
                "source_files": files,
                "source_file_count": len(files),
                "source_rows": self.payload().get("dataset_count"),
                "matched_rows": matched_rows,
            }
        ]

    def summary_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        top_themes = payload.get("top_themes") or [
            {"label": label, "count": count}
            for label, count in sorted(payload.get("theme_counts", {}).items(), key=lambda item: (-item[1], item[0]))
        ]
        top_formats = payload.get("top_formats") or [
            {"label": label, "count": count}
            for label, count in sorted(payload.get("format_counts", {}).items(), key=lambda item: (-item[1], item[0]))
        ]
        theme_text = ", ".join(f"{item['label']} ({item['count']})" for item in top_themes[:6])
        formats = ", ".join(f"{item['label']} ({item['count']})" for item in top_formats[:6])
        return {
            "question": question,
            "answer": (
                "State of Missouri data.mo.gov catalog is connected as an exact metadata lookup layer. "
                f"The indexed DCAT snapshot has {payload.get('dataset_count', 0):,} datasets and "
                f"{payload.get('datasets_with_distribution', 0):,} datasets with distribution/download links. "
                f"Top catalog themes: {theme_text}. Distribution formats: {formats}. "
                "It can search titles, descriptions, themes, keywords, landing pages, and download URLs to find candidate datasets for dedicated parsers."
            ),
            "retrieved_context_id": "data_mo_catalog_index:summary",
            "retrieved_source": "data_mo_catalog_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local data.mo.gov DCAT catalog index.",
            "citations": self.coverage_citation(matched_rows=payload.get("dataset_count", 0)),
            "source_rows": [],
        }

    def unavailable_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "The data.mo.gov catalog index has not been built yet. Run "
                "`python scripts/build_data_mo_catalog_index.py --force` to download the public DCAT catalog and build exact metadata search."
            ),
            "retrieved_context_id": "data_mo_catalog_index:missing",
            "retrieved_source": "data_mo_catalog_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "The data.mo.gov route exists, but the local ignored index is missing.",
            "citations": [],
            "source_rows": [],
        }

    def theme_answer(self, question: str) -> dict[str, Any]:
        items = self.payload().get("top_themes") or [
            {"label": label, "count": count}
            for label, count in sorted(self.payload().get("theme_counts", {}).items(), key=lambda item: (-item[1], item[0]))
        ]
        limit = requested_limit(question, default=10, maximum=15)
        lines = [
            f"{index}. {item['label']}: {item['count']:,} dataset(s)"
            for index, item in enumerate(items[:limit], 1)
        ]
        return {
            "question": question,
            "answer": "Top themes in the indexed data.mo.gov catalog:\n" + "\n".join(lines),
            "retrieved_context_id": "data_mo_catalog_index:themes",
            "retrieved_source": "data_mo_catalog_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from theme metadata in the local data.mo.gov DCAT catalog index.",
            "citations": self.coverage_citation(matched_rows=self.payload().get("dataset_count", 0)),
            "source_rows": [],
        }

    def score_record(self, record: dict[str, Any], terms: list[str]) -> int:
        score = 0
        title = record["title"].lower()
        description = record["description"].lower()
        themes = " ".join(record["themes"]).lower()
        keywords = " ".join(record["keywords"]).lower()
        blob = record["search_blob"]
        for term in terms:
            if term in title:
                score += 8
            if term in themes:
                score += 5
            if term in keywords:
                score += 4
            if term in description:
                score += 2
            if term in blob:
                score += 1
        return score

    def search(self, question: str) -> tuple[list[str], list[dict[str, Any]]]:
        terms = search_terms(question)
        if not terms:
            return [], []
        ranked = [
            (self.score_record(record, terms), record)
            for record in self.records()
        ]
        matches = [record for score, record in sorted(ranked, key=lambda item: (-item[0], item[1]["title"])) if score > 0]
        return terms, matches

    def search_answer(self, question: str) -> dict[str, Any]:
        terms, matches = self.search(question)
        query_label = " ".join(terms) if terms else "the requested terms"
        limit = requested_limit(question)
        if not matches:
            return {
                "question": question,
                "answer": (
                    f"I searched the indexed data.mo.gov catalog metadata for '{query_label}' and found no matching dataset records. "
                    "That does not prove the data does not exist elsewhere; it means this specific data.mo.gov catalog snapshot does not expose a matching title, description, theme, keyword, landing page, or download URL."
                ),
                "retrieved_context_id": f"data_mo_catalog_index:search:{query_label}",
                "retrieved_source": "data_mo_catalog_lookup_index",
                "retrieval_score": 1.0,
                "used_model": False,
                "model": "deterministic_public_lookup",
                "source_note": "Computed from local data.mo.gov catalog metadata search.",
                "citations": self.coverage_citation(),
                "source_rows": [],
            }

        selected = matches[:limit]
        lines = []
        source_files = [
            {
                "category": "data_mo_catalog",
                "category_label": "Official data.mo.gov DCAT catalog",
                "file_name": DATA_JSON_URL,
                "row_count": self.payload().get("dataset_count"),
                "bytes": self.payload().get("catalog_bytes"),
                "sha256": self.payload().get("catalog_sha256"),
            }
        ]
        for index, record in enumerate(selected, 1):
            csv_urls = [item["download_url"] for item in record["distributions"] if item.get("format") == "CSV" and item.get("download_url")]
            json_urls = [item["download_url"] for item in record["distributions"] if item.get("format") == "JSON" and item.get("download_url")]
            download_hint = csv_urls[0] if csv_urls else json_urls[0] if json_urls else "no direct CSV/JSON distribution listed"
            lines.append(
                f"{index}. {record['title']} ({record['id']}) - themes: {format_list(record['themes'])}; "
                f"formats: {format_list(record['formats'])}; page: {record['landing_page']}; download: {download_hint}"
            )
            if record.get("landing_page"):
                source_files.append(
                    {
                        "category": "data_mo_dataset",
                        "category_label": record["title"],
                        "file_name": record["landing_page"],
                        "row_count": None,
                        "bytes": None,
                        "sha256": None,
                    }
                )
        source_rows = [
            {
                "source_file": DATA_JSON_URL,
                "values": {
                    "id": record["id"],
                    "title": record["title"],
                    "themes": record["themes"],
                    "keywords": record["keywords"],
                    "modified": record["modified"],
                    "landing_page": record["landing_page"],
                    "formats": record["formats"],
                    "distribution_count": record["distribution_count"],
                },
            }
            for record in selected[:5]
        ]
        return {
            "question": question,
            "answer": (
                f"I found {len(matches):,} data.mo.gov catalog dataset(s) matching '{query_label}'. "
                "Best matches:\n"
                + "\n".join(lines)
                + "\n"
                + usefulness_note(selected)
            ),
            "retrieved_context_id": f"data_mo_catalog_index:search:{query_label}",
            "retrieved_source": "data_mo_catalog_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from local data.mo.gov catalog metadata search.",
            "citations": self.coverage_citation(matched_rows=len(matches), source_files=source_files[:6]),
            "source_rows": source_rows,
        }

    def answer(self, question: str) -> dict[str, Any] | None:
        if not self.available():
            return self.unavailable_answer(question)
        lowered = question.lower()
        if re.search(r"\b(top|theme|themes|categories|category)\b", lowered) and not any(
            term in lowered for term in ["health", "hospital", "school", "labor", "unemployment", "budget", "finance"]
        ):
            return self.theme_answer(question)
        if re.search(r"\bhow many\b.*\bdata\.mo\.gov\b.*\bdatasets?\b", lowered) or re.search(
            r"\bdata\.mo\.gov\b.*\b(count|cataloged|connected|summary)\b", lowered
        ):
            return self.summary_answer(question)
        if search_terms(question):
            return self.search_answer(question)
        return self.summary_answer(question)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    payload = build_data_mo_catalog_index(force=args.force)
    print(json.dumps({key: value for key, value in payload.items() if key != "records"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
