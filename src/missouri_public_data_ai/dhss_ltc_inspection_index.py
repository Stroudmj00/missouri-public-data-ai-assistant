"""Build and query DHSS long-term-care inspection resource metadata."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw_public" / "dhss_ltc_inspections"
INDEX_PATH = RAW_DIR / "dhss_ltc_inspection_index.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "dhss_ltc_inspection_index_report.json"
SOURCE_NAME = "DHSS long-term-care inspection resources"


@dataclass(frozen=True)
class LtcInspectionPage:
    key: str
    label: str
    url: str
    default_topic: str


PAGES: tuple[LtcInspectionPage, ...] = (
    LtcInspectionPage(
        "nursing_homes_inspected",
        "DHSS Nursing Homes Inspected",
        "https://health.mo.gov/safety/nursinghomesinspected/index.php",
        "inspection source registry",
    ),
    LtcInspectionPage(
        "show_me_ltc",
        "Show Me Long Term Care",
        "https://healthapps.dhss.mo.gov/showmeltc/default.aspx",
        "inspection search app",
    ),
)

KEEP_LINK_PATTERN = re.compile(
    r"show me long|long[-\s]+term care|nursing home|inspection|inspected|compare|laws|regulations|manuals|"
    r"skilled nursing|intermediate care|residential care|assisted living|scope|severity|class i|class ii|class iii|"
    r"lvlo|region|sunshine|records request|mobile|desktop",
    re.I,
)
SKIP_LINK_PATTERN = re.compile(
    r"^(skip to|home$|healthy living$|data & statistics$|email us$|facebook|twitter|instagram|flickr|youtube|mo\.gov|governor|find an agency|online services)",
    re.I,
)

GENERIC_QUERY_TOKENS = {
    "ABOUT",
    "AND",
    "CARE",
    "CAN",
    "DATA",
    "DHSS",
    "DOES",
    "FOR",
    "HAVE",
    "INDEX",
    "INDEXED",
    "INSPECTION",
    "INSPECTIONS",
    "LINK",
    "LINKS",
    "LONG",
    "LOOK",
    "LOOKUP",
    "LTC",
    "ME",
    "MISSOURI",
    "NURSING",
    "REPORT",
    "REPORTS",
    "RESOURCE",
    "RESOURCES",
    "SEARCH",
    "SHOW",
    "SOURCE",
    "SOURCES",
    "TERM",
    "THE",
    "WHAT",
    "WHERE",
}


class LtcPageParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.links: list[dict[str, str]] = []
        self.selects: list[dict[str, Any]] = []
        self._current_href: str | None = None
        self._current_link_text: list[str] = []
        self._current_select: dict[str, Any] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        if tag == "a" and values.get("href"):
            self._current_href = urljoin(self.base_url, html.unescape(values["href"]))
            self._current_link_text = []
        if tag == "select":
            self._current_select = {"attrs": values, "options": []}
            self.selects.append(self._current_select)
        if tag == "option" and self._current_select is not None:
            self._current_select["options"].append({"value": values.get("value", ""), "text": ""})

    def handle_data(self, data: str) -> None:
        if self._current_href is not None:
            self._current_link_text.append(data)
        if self._current_select is not None and self._current_select["options"]:
            self._current_select["options"][-1]["text"] += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._current_href is not None:
            self.links.append(
                {
                    "label": clean_text(" ".join(self._current_link_text)),
                    "url": self._current_href,
                }
            )
            self._current_href = None
            self._current_link_text = []
        if tag == "select":
            self._current_select = None


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
    cleaned = re.sub(r"[^A-Z0-9/-]+", " ", clean_text(value).upper())
    return re.sub(r"\s+", " ", cleaned).strip()


def query_tokens(value: Any) -> set[str]:
    return {
        token
        for token in normalize_text(value).replace("/", " ").replace("-", " ").split()
        if len(token) > 2 and token not in GENERIC_QUERY_TOKENS
    }


def page_text(html_text: str) -> str:
    without_script = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html_text, flags=re.I | re.S)
    return clean_text(without_script)


def resource_type(url: str, label: str) -> str:
    lowered = f"{url} {label}".lower()
    parsed = urlparse(url)
    if "showmeltc" in lowered:
        return "inspection_search_app"
    if "medicare.gov" in lowered or "care-compare" in lowered or "nhcompare" in lowered:
        return "federal_compare_tool"
    if lowered.endswith(".pdf") or "/pdf/" in lowered:
        return "pdf"
    if parsed.netloc.endswith("health.mo.gov"):
        return "dhss_page"
    return "external_page"


def infer_topic(label: str, url: str, default_topic: str) -> str:
    lowered = f"{label} {url}".lower()
    if "showmeltc" in lowered or "inspection" in lowered or "scope" in lowered or "severity" in lowered:
        return "inspection search"
    if "compare" in lowered or "medicare" in lowered:
        return "federal comparison"
    if "laws" in lowered or "regulations" in lowered or "manuals" in lowered:
        return "laws/regulations"
    if "skilled nursing" in lowered or "intermediate care" in lowered or "residential care" in lowered or "assisted living" in lowered or "lvlo" in lowered:
        return "facility levels"
    if "region" in lowered:
        return "regions"
    if "sunshine" in lowered or "records request" in lowered:
        return "records request"
    return default_topic


def select_kind(select_id: str) -> str:
    lowered = select_id.lower()
    if "county" in lowered:
        return "county_filter"
    if "city" in lowered:
        return "city_filter"
    return "search_filter"


def parse_links(page: LtcInspectionPage, parser: LtcPageParser) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for link in parser.links:
        label = clean_text(link["label"])
        url = link["url"]
        if not label or SKIP_LINK_PATTERN.search(label):
            continue
        if not KEEP_LINK_PATTERN.search(f"{label} {url}"):
            continue
        key = (normalize_text(label), url)
        if key in seen:
            continue
        seen.add(key)
        records.append(
            {
                "record_type": "resource_link",
                "label": label,
                "url": url,
                "topic": infer_topic(label, url, page.default_topic),
                "resource_type": resource_type(url, label),
                "source_page_key": page.key,
                "source_page_label": page.label,
                "source_page_url": page.url,
            }
        )
    return records


def parse_filters(page: LtcInspectionPage, parser: LtcPageParser) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for select in parser.selects:
        select_id = select["attrs"].get("id") or select["attrs"].get("name") or "search_filter"
        kind = select_kind(select_id)
        for option in select["options"]:
            value = clean_text(option.get("value"))
            label = clean_text(option.get("text"))
            if not value or value.startswith("-Select") or not label or label.startswith("-Select"):
                continue
            records.append(
                {
                    "record_type": kind,
                    "label": label.upper(),
                    "value": value,
                    "select_id": select_id,
                    "topic": "county search filter" if kind == "county_filter" else "city search filter",
                    "resource_type": "search_filter",
                    "source_page_key": page.key,
                    "source_page_label": page.label,
                    "source_page_url": page.url,
                    "url": page.url,
                }
            )
    return records


def parse_page(page: LtcInspectionPage, html_text: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    parser = LtcPageParser(page.url)
    parser.feed(html_text)
    records = parse_links(page, parser) + parse_filters(page, parser)
    text = page_text(html_text)
    page_info = {
        "key": page.key,
        "label": page.label,
        "url": page.url,
        "bytes": len(html_text.encode("utf-8", errors="replace")),
        "sha256": sha256_text(html_text),
        "record_count": len(records),
        "resource_link_count": sum(1 for record in records if record["record_type"] == "resource_link"),
        "county_filter_count": sum(1 for record in records if record["record_type"] == "county_filter"),
        "city_filter_count": sum(1 for record in records if record["record_type"] == "city_filter"),
        "mentions": {
            "certified_snf_disruption": "certified Skilled Nursing Facilities" in text and "This disruption" in text,
            "state_licensed_facility_types": [
                label
                for label in [
                    "Nursing Facilities (NF)",
                    "Intermediate Care Facilities (ICF)",
                    "Assisted Living Facilities (ALF)",
                    "Residential Care Facilities (RCF)",
                ]
                if label in text
            ],
            "facility_public_inspection_notice": "retain and make available for public inspection" in text,
        },
    }
    return records, page_info


def build_dhss_ltc_inspection_index(force: bool = False, delay_seconds: float = 0.03) -> dict[str, Any]:
    if INDEX_PATH.exists() and not force:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))

    session = requests.Session()
    session.headers.update({"User-Agent": "missouri-public-data-ai-assistant/1.0"})
    all_records: list[dict[str, Any]] = []
    pages: list[dict[str, Any]] = []
    for page in PAGES:
        response = session.get(page.url, timeout=60)
        response.raise_for_status()
        html_text = response.text
        raw_path = RAW_DIR / f"{page.key}.html"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(html_text, encoding="utf-8")
        page_records, page_info = parse_page(page, html_text)
        all_records.extend(page_records)
        pages.append(page_info)
        time.sleep(delay_seconds)

    record_type_counts = Counter(record["record_type"] for record in all_records)
    topic_counts = Counter(record["topic"] for record in all_records)
    resource_type_counts = Counter(record["resource_type"] for record in all_records)
    payload = {
        "source": SOURCE_NAME,
        "generated_at_utc": utc_now(),
        "index_path": str(INDEX_PATH.relative_to(PROJECT_ROOT)),
        "page_count": len(pages),
        "record_count": len(all_records),
        "resource_link_count": record_type_counts.get("resource_link", 0),
        "county_filter_count": record_type_counts.get("county_filter", 0),
        "city_filter_count": record_type_counts.get("city_filter", 0),
        "record_type_counts": dict(sorted(record_type_counts.items())),
        "resource_type_counts": dict(sorted(resource_type_counts.items())),
        "top_topics": [{"label": label, "count": count} for label, count in topic_counts.most_common(10)],
        "pages": pages,
        "notes": [
            "This index stores DHSS long-term-care inspection resource links and Show Me Long Term Care county/city search filters.",
            "It does not parse facility inspection findings, complaint narratives, survey findings, addresses, owners, or recommendations.",
            "Use the official Show Me Long Term Care and Nursing Home Compare links for current facility-level inspection details.",
        ],
        "records": sorted(all_records, key=lambda item: (item["record_type"], item["label"], item.get("url", ""))),
    }
    write_json(INDEX_PATH, payload)
    write_json(REPORT_PATH, {key: value for key, value in payload.items() if key != "records"})
    return payload


def asks_for_summary(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["indexed", "coverage", "what data", "what resources", "what reports", "summary", "available", "connected"])


def asks_about_facility_types(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["facility type", "facility types", "snf", "nursing facilities", "assisted living", "residential care", "intermediate care"])


def asks_about_scope_severity(question: str) -> bool:
    lowered = question.lower()
    return "scope" in lowered or "severity" in lowered or "class i" in lowered or "class ii" in lowered or "class iii" in lowered


class DhssLtcInspectionIndex:
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
                "category": "Long-term care",
                "kind": "DHSS LTC inspection resource lookup",
                "lookup_table": "dhss_ltc_inspection_index",
                "year": None,
                "year_range": "current public source pages",
                "source_files": [
                    {
                        "category": page.get("key"),
                        "category_label": page.get("label"),
                        "file_name": page.get("url"),
                        "row_count": page.get("record_count"),
                        "bytes": page.get("bytes"),
                        "sha256": page.get("sha256"),
                    }
                    for page in payload.get("pages", [])
                ],
                "source_file_count": payload.get("page_count", 0),
                "source_rows": payload.get("record_count", 0),
                "matched_rows": matched_rows,
            }
        ]

    def unavailable_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "The DHSS long-term-care inspection resource index has not been built yet. Run "
                "`python scripts/build_dhss_ltc_inspection_index.py --force` to index the public resource pages."
            ),
            "retrieved_context_id": "dhss_ltc_inspection_index:missing",
            "retrieved_source": "dhss_ltc_inspection_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "The DHSS LTC inspection resource route exists, but the local ignored index is missing.",
            "citations": [],
            "source_rows": [],
        }

    def summary_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        return {
            "question": question,
            "answer": (
                "The DHSS long-term-care inspection resource metadata layer indexes official Nursing Homes Inspected and Show Me Long Term Care pages. "
                f"It contains {payload.get('record_count', 0):,} metadata row(s): {payload.get('resource_link_count', 0):,} resource link(s), "
                f"{payload.get('county_filter_count', 0):,} county search filter(s), and {payload.get('city_filter_count', 0):,} city search filter(s). "
                "It can point users to official LTC inspection search pages, facility-level search filters, levels-of-care resources, laws/regulations, records requests, and Nursing Home Compare. "
                "It does not parse facility inspection findings, complaint narratives, survey findings, addresses, or quality recommendations."
            ),
            "retrieved_context_id": "dhss_ltc_inspection_index:summary",
            "retrieved_source": "dhss_ltc_inspection_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local DHSS LTC inspection resource metadata index.",
            "citations": self.citation(matched_rows=payload.get("record_count", 0)),
            "source_rows": [],
        }

    def matching_filters(self, question: str) -> list[dict[str, Any]]:
        tokens = query_tokens(question)
        if not tokens:
            return []
        matches: list[tuple[int, dict[str, Any]]] = []
        for record in self.records():
            if record["record_type"] not in {"county_filter", "city_filter"}:
                continue
            record_tokens = query_tokens(record["label"])
            score = len(tokens & record_tokens)
            label_norm = normalize_text(record["label"])
            question_norm = normalize_text(question)
            if label_norm and label_norm in question_norm:
                score += 10
            if score:
                matches.append((score, record))
        if not matches:
            return []
        best = max(score for score, _ in matches)
        return [record for score, record in sorted(matches, key=lambda item: (-item[0], item[1]["record_type"], item[1]["label"])) if score == best]

    def matching_links(self, question: str) -> list[dict[str, Any]]:
        lowered = question.lower()
        if asks_about_scope_severity(question):
            preferred = ["scope", "severity", "class i", "class ii", "class iii", "show me long"]
        elif asks_about_facility_types(question):
            preferred = ["skilled nursing", "intermediate care", "residential care", "assisted living", "lvlo", "show me long"]
        elif "compare" in lowered or "medicare" in lowered:
            preferred = ["compare", "medicare"]
        elif "law" in lowered or "regulation" in lowered or "manual" in lowered:
            preferred = ["laws", "regulations", "manuals"]
        elif "region" in lowered:
            preferred = ["region"]
        elif "records" in lowered or "sunshine" in lowered:
            preferred = ["records request", "sunshine"]
        else:
            preferred = ["show me long", "inspection", "inspected"]
        rows = [
            record
            for record in self.records()
            if record["record_type"] == "resource_link"
            and any(term in f"{record['label']} {record['url']}".lower() for term in preferred)
        ]
        return rows[:5]

    def filters_answer(self, question: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
        county_rows = [row for row in rows if row["record_type"] == "county_filter"]
        city_rows = [row for row in rows if row["record_type"] == "city_filter"]
        parts = []
        if county_rows:
            parts.append(
                "; ".join(f"{row['label']} County is available as county filter code {row['value']}" for row in county_rows[:5])
            )
        if city_rows:
            parts.append("; ".join(f"{row['label']} is available as a city filter" for row in city_rows[:5]))
        rendered = "; ".join(parts)
        return {
            "question": question,
            "answer": (
                f"{rendered}. Use the official Show Me Long Term Care search page to run the current lookup: "
                "https://healthapps.dhss.mo.gov/showmeltc/default.aspx. "
                "This local index stores search-filter metadata only, not facility inspection findings or quality conclusions."
            ),
            "retrieved_context_id": "dhss_ltc_inspection_index:filter_match",
            "retrieved_source": "dhss_ltc_inspection_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local DHSS LTC inspection resource metadata index.",
            "citations": self.citation(matched_rows=len(rows)),
            "source_rows": [{"source_file": row["source_page_url"], "values": row} for row in rows[:5]],
        }

    def facility_types_answer(self, question: str) -> dict[str, Any]:
        rows = self.matching_links(question)
        return {
            "question": question,
            "answer": (
                "The Show Me Long Term Care page mentions state-licensed Nursing Facilities (NF), Intermediate Care Facilities (ICF), "
                "Assisted Living Facilities (ALF), and Residential Care Facilities (RCF). It also notes a disruption for certified Skilled Nursing Facilities (SNF) "
                "and points users to Nursing Home Compare for current certified nursing-home survey and complaint investigation information. "
                "This is source guidance, not a facility quality rating."
            ),
            "retrieved_context_id": "dhss_ltc_inspection_index:facility_types",
            "retrieved_source": "dhss_ltc_inspection_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from DHSS Show Me Long Term Care page metadata.",
            "citations": self.citation(matched_rows=len(rows)),
            "source_rows": [{"source_file": row["source_page_url"], "values": row} for row in rows[:5]],
        }

    def links_answer(self, question: str) -> dict[str, Any]:
        rows = self.matching_links(question)
        if not rows:
            return self.summary_answer(question)
        rendered = "; ".join(f"{row['label']}: {row['url']}" for row in rows)
        suffix = " These are source links and search metadata, not parsed inspection findings."
        return {
            "question": question,
            "answer": f"Relevant DHSS long-term-care inspection resource link(s): {rendered}.{suffix}",
            "retrieved_context_id": "dhss_ltc_inspection_index:resource_links",
            "retrieved_source": "dhss_ltc_inspection_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local DHSS LTC inspection resource metadata index.",
            "citations": self.citation(matched_rows=len(rows)),
            "source_rows": [{"source_file": row["source_page_url"], "values": row} for row in rows[:5]],
        }

    def answer(self, question: str) -> dict[str, Any] | None:
        if not self.available():
            return self.unavailable_answer(question)
        if asks_about_facility_types(question):
            return self.facility_types_answer(question)
        if asks_about_scope_severity(question):
            return self.links_answer(question)
        filter_rows = self.matching_filters(question)
        if filter_rows:
            return self.filters_answer(question, filter_rows)
        if asks_for_summary(question):
            return self.summary_answer(question)
        return self.links_answer(question)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--delay-seconds", type=float, default=0.03)
    args = parser.parse_args()
    payload = build_dhss_ltc_inspection_index(force=args.force, delay_seconds=args.delay_seconds)
    print(json.dumps({key: value for key, value in payload.items() if key != "records"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
