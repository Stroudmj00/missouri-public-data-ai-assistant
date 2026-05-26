"""Capped text/value extraction for selected Agricultural Market News PDFs."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from pypdf import PdfReader

from missouri_public_data_ai.ag_market_news_index import INDEX_PATH as AG_MARKET_INDEX_PATH
from missouri_public_data_ai.ag_market_news_index import LANDING_PAGE, build_ag_market_news_index


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw_public" / "ag_market_report_documents"
DOCUMENT_DIR = RAW_DIR / "documents"
INDEX_PATH = RAW_DIR / "ag_market_report_documents_index.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "ag_market_report_document_index_report.json"
SOURCE_NAME = "Missouri Agricultural Market News selected report PDFs"
DEFAULT_REPORT_CODES = ["ams_1245", "ams_2932", "ams_2929"]

TOPIC_TERMS = {
    "receipts": ("receipt", "receipts", "volume", "head"),
    "steers": ("steer", "steers", "feeder steers"),
    "heifers": ("heifer", "heifers"),
    "grain": ("grain", "corn", "soybeans", "wheat"),
    "hay": ("hay", "alfalfa", "forage"),
    "special_note": ("special note", "holiday", "memorial day"),
    "demand": ("demand", "supply"),
    "price": ("price", "prices", "bid", "bids"),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def clean_text(value: Any) -> str:
    text = str(value or "").replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([,.;:)])", r"\1", text)
    text = re.sub(r"([(])\s+", r"\1", text)
    return text.strip()


def clean_lines(text: str) -> list[str]:
    return [clean_text(line) for line in text.splitlines() if clean_text(line)]


def safe_pdf_name(record: dict[str, Any], url: str) -> str:
    report_id = str(record.get("report_code") or record.get("report_id") or "report").lower()
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(url.split("?", 1)[0]).stem)[:80]
    return f"{report_id}_{stem}.pdf"


def load_ag_market_metadata() -> dict[str, Any]:
    if not AG_MARKET_INDEX_PATH.exists():
        return build_ag_market_news_index(force=True)
    return json.loads(AG_MARKET_INDEX_PATH.read_text(encoding="utf-8"))


def selected_records(payload: dict[str, Any], report_codes: list[str], limit: int) -> list[dict[str, Any]]:
    records = [record for record in payload.get("records", []) if record.get("source_type") == "pdf_link"]
    wanted = {code.lower() for code in report_codes if code}
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        code = str(record.get("report_code") or "").lower()
        if code in wanted and code not in seen:
            selected.append(record)
            seen.add(code)
    for record in records:
        if len(selected) >= limit:
            break
        code = str(record.get("report_code") or record.get("report_id") or "").lower()
        if code and code not in seen:
            selected.append(record)
            seen.add(code)
    return selected[:limit]


def extract_pdf_text(pdf_bytes: bytes, max_pages: int, max_chars: int) -> tuple[str, int]:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    parts: list[str] = []
    for page in reader.pages[:max_pages]:
        if sum(len(part) for part in parts) >= max_chars:
            break
        parts.append(page.extract_text() or "")
    return "\n".join(parts)[:max_chars], len(reader.pages)


def extract_report_date(lines: list[str]) -> str | None:
    month_names = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
    for line in lines[:20]:
        match = re.search(rf"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)?\s*(?:{month_names})\s+\d{{1,2}},\s+20\d{{2}}\b", line)
        if match:
            return clean_text(match.group(0))
    return None


def collect_until(lines: list[str], start_index: int, stop_patterns: list[str], limit: int = 420) -> str:
    parts: list[str] = []
    for line in lines[start_index:]:
        if parts and any(re.search(pattern, line, re.I) for pattern in stop_patterns):
            break
        parts.append(line)
        if len(clean_text(" ".join(parts))) >= limit:
            break
    return clean_text(" ".join(parts))[:limit].strip(" .")


def extract_special_note(lines: list[str]) -> str | None:
    for index, line in enumerate(lines):
        if re.match(r"^(Special Notes?|Please Note):?", line, re.I):
            return collect_until(
                lines,
                index,
                [r"^\*\*CLOSE\*\*$", r"^Daily Trends", r"^Source:", r"^Page \d+", r"^N/A$", r"^Hay \(Conventional\)", r"^[A-Z].* Report for"],
                limit=520,
            )
    return None


def extract_commentary(lines: list[str], report_code: str) -> str | None:
    lowered_code = report_code.lower()
    if lowered_code == "ams_1245":
        for index, line in enumerate(lines):
            if line.strip().upper() == "**CLOSE**":
                return collect_until(lines, index + 1, [r"^Supply included:", r"^AUCTION$", r"^Livestock Weighted"], limit=680)
    if lowered_code == "ams_2932":
        for index, line in enumerate(lines):
            if line.startswith("Daily Trends:"):
                return collect_until(lines, index, [r"^Page \d+", r"^USDA AMS"], limit=560)
    if lowered_code == "ams_2929":
        for index, line in enumerate(lines):
            if line == "Volume":
                return collect_until(lines, index + 1, [r"^Please Note:", r"^Hay \(Conventional\)"], limit=760)
    return None


def extract_hay_market_tone(lines: list[str]) -> str | None:
    compact = clean_text(" ".join(lines))
    match = re.search(r"Hay prices are .*?supplies are .*?\.", compact, re.I)
    return clean_text(match.group(0)) if match else None


def extract_receipts(lines: list[str]) -> dict[str, str] | None:
    for index, line in enumerate(lines):
        if line.startswith("Total Receipts"):
            values: list[str] = []
            for candidate in lines[index + 1 : index + 12]:
                if re.fullmatch(r"\d{1,3}(?:,\d{3})*", candidate):
                    values.append(candidate)
                if len(values) >= 3:
                    return {"this_week": values[0], "last_reported": values[1], "last_year": values[2]}
    return None


def is_count(value: str) -> bool:
    return bool(re.fullmatch(r"\d{1,3}(?:,\d{3})*|\d+", value))


def is_weight(value: str) -> bool:
    return bool(re.fullmatch(r"\d{2,4}(?:-\d{2,4})?", value))


def is_price(value: str) -> bool:
    return bool(re.fullmatch(r"\d+\.\d{2}(?:-\d+\.\d{2})?", value))


def next_section(value: str) -> bool:
    return bool(
        re.match(r"^(STEERS|HEIFERS|BULLS|FEEDER|Special Note|AUCTION|Livestock Weighted|Source:|Page \d+)", value, re.I)
    )


def parse_int(value: str) -> int:
    return int(value.replace(",", ""))


def parse_joplin_steer_rows(lines: list[str], limit: int = 40) -> list[dict[str, Any]]:
    section = "STEERS - Medium and Large 1 (Per Cwt / Actual Wt)"
    try:
        start = next(index for index, line in enumerate(lines) if line.startswith(section))
    except StopIteration:
        return []
    index = start
    while index < len(lines) and lines[index] != "Avg Price":
        index += 1
    index += 1
    rows: list[dict[str, Any]] = []
    while index + 4 < len(lines) and len(rows) < limit:
        if next_section(lines[index]):
            break
        if (
            is_count(lines[index])
            and is_weight(lines[index + 1])
            and is_weight(lines[index + 2])
            and is_price(lines[index + 3])
            and is_price(lines[index + 4])
        ):
            row = {
                "section": section,
                "head": parse_int(lines[index]),
                "weight_range": lines[index + 1],
                "avg_weight": parse_int(lines[index + 2]),
                "price_range": lines[index + 3],
                "avg_price": lines[index + 4],
            }
            index += 5
            notes: list[str] = []
            while index < len(lines) and not is_count(lines[index]) and not next_section(lines[index]):
                notes.append(lines[index])
                index += 1
            if notes:
                row["note"] = clean_text(" ".join(notes))
            rows.append(row)
            continue
        index += 1
    return rows


HAY_HEADER_TERMS = {
    "Qty",
    "Price Range",
    "Wtd Avg",
    "Freight/Use",
    "Description",
    "Crop Age",
}


def parse_price_bounds(value: str) -> tuple[float | None, float | None]:
    match = re.fullmatch(r"(\d+\.\d{2})(?:-(\d+\.\d{2}))?", value)
    if not match:
        return None, None
    low = float(match.group(1))
    high = float(match.group(2) or match.group(1))
    return low, high


def parse_hay_price_rows(lines: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    row_pattern = re.compile(
        r"^(?P<product>Alfalfa|Mixed Grass|Wheat)\s*-\s*(?P<quality>.*?)\s*\((?P<offer_type>Ask)/(?P<unit>Per Ton|Per Bale)\)$",
        re.I,
    )
    index = 0
    while index < len(lines):
        match = row_pattern.match(lines[index])
        if not match:
            index += 1
            continue
        product = clean_text(match.group("product")).title()
        quality = clean_text(match.group("quality")).strip("- ") or None
        offer_type = clean_text(match.group("offer_type"))
        unit = clean_text(match.group("unit"))
        index += 1
        description_parts: list[str] = []
        price_range = None
        freight_use = None
        while index < len(lines):
            line = lines[index]
            if row_pattern.match(line) or line.startswith("Source:") or line.startswith("Page "):
                break
            if line in HAY_HEADER_TERMS or line == "Click here for Hay glossary of terms":
                index += 1
                continue
            if line.startswith("https://") or line.startswith("http://"):
                index += 1
                continue
            if is_price(line):
                price_range = line
                index += 1
                if index < len(lines) and re.fullmatch(r"F\.O\.B\.|Delivered", lines[index], re.I):
                    freight_use = lines[index]
                    index += 1
                break
            description_parts.append(line)
            index += 1
        if price_range:
            low_price, high_price = parse_price_bounds(price_range)
            rows.append(
                {
                    "product": product,
                    "quality": quality,
                    "offer_type": offer_type,
                    "unit": unit,
                    "package": clean_text(" ".join(description_parts)),
                    "price_range": price_range,
                    "low_price": low_price,
                    "high_price": high_price,
                    "freight_use": freight_use,
                }
            )
    return rows


def report_topics(text: str) -> dict[str, int]:
    lowered = text.lower()
    counts: dict[str, int] = {}
    for topic, terms in TOPIC_TERMS.items():
        count = 0
        for term in terms:
            count += len(re.findall(rf"\b{re.escape(term.lower())}\b", lowered))
        if count:
            counts[topic] = count
    return dict(sorted(counts.items(), key=lambda item: item[1], reverse=True))


def snippets_for_terms(text: str, terms: list[str], limit: int = 4) -> list[str]:
    snippets: list[str] = []
    compact = clean_text(text)
    lowered = compact.lower()
    for term in terms:
        for match in re.finditer(re.escape(term.lower()), lowered):
            start = max(0, match.start() - 170)
            end = min(len(compact), match.end() + 260)
            snippet = clean_text(compact[start:end]).strip(" .")
            if snippet and snippet not in snippets:
                snippets.append(snippet)
            if len(snippets) >= limit:
                return snippets
    return snippets


def requested_search_terms(question: str) -> list[str]:
    lowered = question.lower()
    terms: list[str] = []
    for topic, topic_terms in TOPIC_TERMS.items():
        if topic in lowered or any(term in lowered for term in topic_terms):
            terms.extend(topic_terms[:2])
    quoted = re.findall(r'"([^"]{3,60})"', question)
    terms.extend(quoted)
    return list(dict.fromkeys(term for term in terms if term))


def weight_range_query(question: str) -> str | None:
    match = re.search(r"\b(\d{2,4})\s*(?:-|to)\s*(\d{2,4})\b", question)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    return None


def weight_point_query(question: str) -> int | None:
    match = re.search(r"\b(\d{3,4})\s*(?:lb|lbs|pound|pounds)\b", question, re.I)
    if match:
        return int(match.group(1))
    return None


def row_contains_weight(row: dict[str, Any], weight: int) -> bool:
    value = str(row.get("weight_range") or "")
    if "-" in value:
        low, high = [int(part) for part in value.split("-", 1)]
        return low <= weight <= high
    return int(value) == weight


def normalize_document(
    record: dict[str, Any],
    pdf_url: str,
    local_file: Path,
    pdf_bytes: bytes,
    text: str,
    page_count: int,
    max_pages: int,
) -> dict[str, Any]:
    lines = clean_lines(text)
    report_code = str(record.get("report_code") or "").lower()
    parsed_values: dict[str, Any] = {
        "report_date": extract_report_date(lines),
        "special_note": extract_special_note(lines),
        "commentary": extract_commentary(lines, report_code),
        "receipts": extract_receipts(lines),
        "joplin_steer_rows": parse_joplin_steer_rows(lines) if report_code == "ams_1245" else [],
        "hay_price_rows": parse_hay_price_rows(lines) if report_code == "ams_2929" else [],
        "market_tone": extract_hay_market_tone(lines) if report_code == "ams_2929" else None,
    }
    parsed_values = {key: value for key, value in parsed_values.items() if value}
    return {
        "report_id": record.get("report_id"),
        "report_code": report_code,
        "label": record.get("label"),
        "category": record.get("category"),
        "commodity": record.get("commodity"),
        "region": record.get("region"),
        "location": record.get("location"),
        "schedule": record.get("schedule"),
        "pdf_url": pdf_url,
        "source_page": record.get("source_page") or LANDING_PAGE,
        "local_file": str(local_file.relative_to(PROJECT_ROOT)),
        "bytes": len(pdf_bytes),
        "sha256": sha256_bytes(pdf_bytes),
        "page_count": page_count,
        "extracted_page_limit": max_pages,
        "text_chars": len(text),
        "title": lines[0] if lines else record.get("label"),
        "topic_counts": report_topics(text),
        "parsed_values": parsed_values,
        "text": text,
    }


def build_ag_market_report_document_index(
    limit: int = 3,
    max_mb: float = 3.0,
    max_pages_per_document: int = 8,
    max_chars_per_document: int = 24_000,
    report_codes: list[str] | None = None,
    delay_seconds: float = 0.05,
    force: bool = False,
) -> dict[str, Any]:
    if INDEX_PATH.exists() and not force:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))

    metadata = load_ag_market_metadata()
    records = selected_records(metadata, report_codes or DEFAULT_REPORT_CODES, limit)
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (compatible; MissouriPublicDataAssistant/1.0)",
            "Accept": "application/pdf,*/*;q=0.8",
        }
    )
    max_bytes = int(max_mb * 1024 * 1024)
    downloaded_bytes = 0
    documents: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    start = time.perf_counter()

    for record in records:
        pdf_url = str(record.get("url") or "")
        if not pdf_url or len(documents) >= limit or downloaded_bytes >= max_bytes:
            continue
        try:
            response = session.get(pdf_url, timeout=90)
            response.raise_for_status()
            pdf_bytes = response.content
            content_type = response.headers.get("content-type", "")
            if "pdf" not in content_type.lower() and not pdf_bytes.startswith(b"%PDF"):
                raise ValueError(f"Response does not look like a PDF: {content_type}")
            if downloaded_bytes + len(pdf_bytes) > max_bytes:
                errors.append(
                    {
                        "report_code": str(record.get("report_code") or ""),
                        "url": pdf_url,
                        "error": f"Skipping PDF because it would exceed {max_mb} MB cap.",
                    }
                )
                continue
            local_file = DOCUMENT_DIR / safe_pdf_name(record, pdf_url)
            local_file.parent.mkdir(parents=True, exist_ok=True)
            local_file.write_bytes(pdf_bytes)
            text, page_count = extract_pdf_text(pdf_bytes, max_pages_per_document, max_chars_per_document)
            documents.append(
                normalize_document(record, pdf_url, local_file, pdf_bytes, text, page_count, max_pages_per_document)
            )
            downloaded_bytes += len(pdf_bytes)
        except Exception as exc:  # noqa: BLE001 - continue indexing other public PDFs.
            errors.append({"report_code": str(record.get("report_code") or ""), "url": pdf_url, "error": str(exc)})
        if delay_seconds > 0:
            time.sleep(delay_seconds)

    document_summaries = [
        {
            "report_code": document.get("report_code"),
            "label": document.get("label"),
            "commodity": document.get("commodity"),
            "report_date": document.get("parsed_values", {}).get("report_date"),
            "pdf_url": document.get("pdf_url"),
            "bytes": document.get("bytes"),
            "page_count": document.get("page_count"),
            "text_chars": document.get("text_chars"),
            "topic_counts": document.get("topic_counts", {}),
            "parsed_fields": sorted(document.get("parsed_values", {}).keys()),
            "joplin_steer_row_count": len(document.get("parsed_values", {}).get("joplin_steer_rows", [])),
            "hay_price_row_count": len(document.get("parsed_values", {}).get("hay_price_rows", [])),
        }
        for document in documents
    ]
    payload = {
        "generated_at_utc": utc_now(),
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "source": SOURCE_NAME,
        "source_url": LANDING_PAGE,
        "source_metadata_index": str(AG_MARKET_INDEX_PATH.relative_to(PROJECT_ROOT)),
        "index_path": str(INDEX_PATH.relative_to(PROJECT_ROOT)),
        "candidate_pdf_count": sum(1 for record in metadata.get("records", []) if record.get("source_type") == "pdf_link"),
        "document_count": len(documents),
        "downloaded_bytes": downloaded_bytes,
        "downloaded_mb": round(downloaded_bytes / 1024 / 1024, 3),
        "limit": limit,
        "max_mb": max_mb,
        "max_pages_per_document": max_pages_per_document,
        "max_chars_per_document": max_chars_per_document,
        "error_count": len(errors),
        "errors": errors,
        "document_summaries": document_summaries,
        "notes": [
            "Downloaded Agricultural Market News PDFs and extracted text are local-only and ignored by Git.",
            "The default build is intentionally capped to selected small report PDFs for Joplin feeder cattle, Missouri grain, and Missouri hay.",
            "Answers provide plain-English orientation, official PDF links, selected parsed values, and capped snippets.",
            "This is not live trading advice, a guarantee of future prices, or a substitute for the official report wording.",
        ],
        "documents": documents,
    }
    write_json(INDEX_PATH, payload)
    write_json(REPORT_PATH, {key: value for key, value in payload.items() if key != "documents"})
    return payload


class AgMarketReportDocumentIndex:
    def __init__(self, path: Path = INDEX_PATH) -> None:
        self.path = path
        self._payload: dict[str, Any] | None = None

    def available(self) -> bool:
        return self.path.exists() and self.path.stat().st_size > 0

    def payload(self) -> dict[str, Any]:
        if self._payload is None:
            self._payload = json.loads(self.path.read_text(encoding="utf-8")) if self.available() else {}
        return self._payload

    def documents(self) -> list[dict[str, Any]]:
        return list(self.payload().get("documents", []))

    def citation(self, document: dict[str, Any] | None = None, matched_rows: int = 0) -> list[dict[str, Any]]:
        payload = self.payload()
        if document:
            source_files = [
                {
                    "category": "ag_market_report_document",
                    "category_label": document.get("label") or "Agricultural Market News report PDF",
                    "file_name": document.get("pdf_url"),
                    "source_url": document.get("pdf_url"),
                    "row_count": 1,
                    "bytes": document.get("bytes"),
                    "sha256": document.get("sha256"),
                }
            ]
        else:
            source_files = [
                {
                    "category": "ag_market_report_document",
                    "category_label": "Missouri Agricultural Market News reports",
                    "file_name": payload.get("source_url", LANDING_PAGE),
                    "source_url": payload.get("source_url", LANDING_PAGE),
                    "row_count": payload.get("document_count"),
                    "bytes": payload.get("downloaded_bytes"),
                    "sha256": None,
                }
            ]
        return [
            {
                "dataset": payload.get("source", SOURCE_NAME),
                "category": "Agriculture",
                "kind": "selected market report PDF text and parsed values",
                "lookup_table": "ag_market_report_document_index",
                "year": None,
                "year_range": None,
                "source_files": source_files,
                "source_file_count": len(source_files),
                "source_rows": payload.get("document_count"),
                "matched_rows": matched_rows,
            }
        ]

    def unavailable_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "The selected Agricultural Market News report document index has not been built yet. Run "
                "`python scripts/build_ag_market_report_document_index.py --force` to enable capped PDF text and parsed market values."
            ),
            "retrieved_context_id": "ag_market_report_document_index:missing",
            "retrieved_source": "ag_market_report_document_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "The Agricultural Market News document route exists, but the local ignored PDF text index is missing.",
            "citations": [],
            "source_rows": [],
        }

    def summary_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        lowered = question.lower()
        summaries = payload.get("document_summaries", [])
        examples = "; ".join(
            f"{item.get('report_code')} {item.get('label')} ({item.get('report_date') or 'date not parsed'})"
            for item in summaries[:4]
        )
        steer_rows = sum(int(item.get("joplin_steer_row_count") or 0) for item in summaries)
        hay_rows = sum(int(item.get("hay_price_row_count") or 0) for item in summaries)
        return {
            "question": question,
            "answer": (
                "The selected Agricultural Market News document layer indexes capped text from official USDA/Missouri market-report PDFs. "
                f"It currently has {payload.get('document_count', 0):,} PDF(s), {payload.get('downloaded_mb', 0)} MB downloaded locally, "
                f"{hay_rows:,} Missouri Direct Hay Report price row(s), and {steer_rows:,} selected Joplin weighted-average steer price row(s). "
                f"Indexed reports include the Missouri Direct Hay Report / Missouri Bi-Weekly Hay Summary: {examples}. "
                "It can answer plain-English summaries, hay demand/supply context, hay price ranges, "
                "receipt totals, selected Joplin steer price rows, special notes, and source snippets."
            ),
            "retrieved_context_id": "ag_market_report_document_index:summary",
            "retrieved_source": "ag_market_report_document_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the capped local Agricultural Market News report document index.",
            "citations": self.citation(
                document=self.find_document(question)
                if any(term in lowered for term in ["hay", "alfalfa", "mixed grass", "straw"])
                else None,
                matched_rows=payload.get("document_count", 0),
            ),
            "source_rows": [],
        }

    def find_document(self, question: str) -> dict[str, Any] | None:
        lowered = question.lower()
        code_match = re.search(r"\bams[_-]?(\d{4})\b", lowered)
        if code_match:
            code = f"ams_{code_match.group(1)}"
            for document in self.documents():
                if document.get("report_code") == code:
                    return document
            return None
        preferences: list[str] = []
        if any(term in lowered for term in ["joplin", "carthage", "feeder", "steer", "steers", "receipt", "receipts"]):
            preferences.append("ams_1245")
        if any(term in lowered for term in ["grain", "corn", "soybean", "soybeans", "wheat"]):
            preferences.append("ams_2932")
        if any(term in lowered for term in ["hay", "alfalfa", "forage"]):
            preferences.append("ams_2929")
        for code in preferences:
            for document in self.documents():
                if document.get("report_code") == code:
                    return document
        docs = self.documents()
        return docs[0] if docs else None

    def explain_answer(self, question: str, document: dict[str, Any]) -> dict[str, Any]:
        parsed = document.get("parsed_values", {})
        bits = [
            f"{document.get('label')} is an official market report PDF",
            f"report date: {parsed.get('report_date') or 'not parsed'}",
        ]
        if parsed.get("receipts"):
            receipts = parsed["receipts"]
            bits.append(
                f"total receipts were {receipts.get('this_week')} this week, {receipts.get('last_reported')} last reported, and {receipts.get('last_year')} last year"
            )
        if parsed.get("commentary"):
            bits.append(f"plain-English market context: {parsed['commentary'][:500]}")
        if parsed.get("market_tone"):
            bits.append(f"market tone: {parsed['market_tone']}")
        if parsed.get("hay_price_rows"):
            sample = "; ".join(
                f"{row.get('product')} {row.get('quality') or ''} {row.get('unit')} {row.get('price_range')}"
                for row in parsed["hay_price_rows"][:4]
            )
            bits.append(f"sample parsed hay price ranges: {sample}")
        if parsed.get("special_note"):
            bits.append(f"special note: {parsed['special_note'][:220]}")
        bits.append(f"official PDF: {document.get('pdf_url')}")
        answer = ". ".join(bit.rstrip(" .") for bit in bits if bit).strip()
        return {
            "question": question,
            "answer": f"{answer}.",
            "retrieved_context_id": f"ag_market_report_document_index:explain:{document.get('report_code')}",
            "retrieved_source": "ag_market_report_document_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Plain-English orientation from capped local extraction of the official Agricultural Market News PDF.",
            "citations": self.citation(document=document, matched_rows=1),
            "source_rows": [
                {
                    "source_file": document.get("pdf_url"),
                    "values": {
                        "report_code": document.get("report_code"),
                        "label": document.get("label"),
                        "report_date": parsed.get("report_date"),
                        "commentary_excerpt": (parsed.get("commentary") or "")[:260],
                        "market_tone": parsed.get("market_tone"),
                        "price_row_count": len(parsed.get("hay_price_rows") or parsed.get("joplin_steer_rows") or []),
                        "special_note": (parsed.get("special_note") or "")[:220],
                    },
                }
            ],
        }

    def receipts_answer(self, question: str, document: dict[str, Any]) -> dict[str, Any]:
        receipts = document.get("parsed_values", {}).get("receipts")
        if not receipts:
            return self.missing_answer(question, document=document)
        return {
            "question": question,
            "answer": (
                f"{document.get('label')} lists total receipts of {receipts.get('this_week')} for this week, "
                f"{receipts.get('last_reported')} for the last reported sale, and {receipts.get('last_year')} for last year. "
                f"Official PDF: {document.get('pdf_url')}."
            ),
            "retrieved_context_id": f"ag_market_report_document_index:receipts:{document.get('report_code')}",
            "retrieved_source": "ag_market_report_document_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Receipt totals parsed from capped local extraction of the official Agricultural Market News PDF.",
            "citations": self.citation(document=document, matched_rows=1),
            "source_rows": [{"source_file": document.get("pdf_url"), "values": receipts}],
        }

    def price_answer(self, question: str, document: dict[str, Any]) -> dict[str, Any]:
        rows = document.get("parsed_values", {}).get("joplin_steer_rows", [])
        if not rows:
            return self.missing_answer(question, document=document)
        wanted_range = weight_range_query(question)
        wanted_weight = weight_point_query(question)
        match: dict[str, Any] | None = None
        if wanted_range:
            for row in rows:
                if row.get("weight_range") == wanted_range:
                    match = row
                    break
        elif wanted_weight is not None:
            for row in rows:
                if row_contains_weight(row, wanted_weight):
                    match = row
                    break
        if match is None:
            return self.missing_answer(
                question,
                "The selected Joplin report has parsed Medium and Large 1 steer rows, but I could not match that requested weight range. "
                "Try `What price range did Joplin list for 502-547 lb Medium and Large 1 steers?`.",
                document=document,
            )
        return {
            "question": question,
            "answer": (
                f"In {document.get('label')}, Medium and Large 1 steers at {match.get('weight_range')} lb "
                f"({match.get('head')} head, average weight {match.get('avg_weight')}) listed a price range of "
                f"{match.get('price_range')} per cwt and an average price of {match.get('avg_price')}. "
                f"Official PDF: {document.get('pdf_url')}."
            ),
            "retrieved_context_id": f"ag_market_report_document_index:price:{document.get('report_code')}:{match.get('weight_range')}",
            "retrieved_source": "ag_market_report_document_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Selected weighted-average row parsed from the official Joplin Agricultural Market News PDF.",
            "citations": self.citation(document=document, matched_rows=1),
            "source_rows": [{"source_file": document.get("pdf_url"), "values": match}],
        }

    def hay_price_answer(self, question: str, document: dict[str, Any]) -> dict[str, Any]:
        rows = list(document.get("parsed_values", {}).get("hay_price_rows", []))
        if not rows:
            return self.missing_answer(question, document=document)
        lowered = question.lower()
        if "alfalfa" in lowered:
            rows = [row for row in rows if row.get("product") == "Alfalfa"]
        if "mixed grass" in lowered or "grass" in lowered:
            rows = [row for row in rows if row.get("product") == "Mixed Grass"]
        if "straw" in lowered or "wheat" in lowered:
            rows = [row for row in rows if row.get("product") == "Wheat"]
        quality_terms = ["supreme", "premium", "good/premium", "fair/good", "good", "fair"]
        matched_quality = next((term for term in quality_terms if term in lowered), None)
        if matched_quality:
            rows = [row for row in rows if matched_quality in str(row.get("quality") or "").lower()]
        if "per ton" in lowered:
            rows = [row for row in rows if row.get("unit") == "Per Ton"]
        if "per bale" in lowered or "bale" in lowered:
            rows = [row for row in rows if row.get("unit") == "Per Bale"]
        if not rows:
            return self.missing_answer(
                question,
                "The selected Missouri hay report has parsed price rows, but I could not match that product, quality, or unit. "
                "Try `What is the Alfalfa Supreme per ton price range in the Missouri hay report?` or `Show mixed grass hay price ranges.`",
                document=document,
            )
        preview = rows[:6]
        rendered = "; ".join(
            f"{row.get('product')} {row.get('quality') or ''} {row.get('unit')} ({row.get('package')}): "
            f"{row.get('price_range')} {row.get('freight_use') or ''}".strip()
            for row in preview
        )
        return {
            "question": question,
            "answer": (
                f"In {document.get('label')}, parsed hay price range row(s): {rendered}. "
                "These are report asks/offers from the official market report, not buying advice. "
                f"Official PDF: {document.get('pdf_url')}."
            ),
            "retrieved_context_id": f"ag_market_report_document_index:hay_prices:{document.get('report_code')}",
            "retrieved_source": "ag_market_report_document_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Selected hay price rows parsed from the official Missouri Direct Hay Report PDF.",
            "citations": self.citation(document=document, matched_rows=len(preview)),
            "source_rows": [{"source_file": document.get("pdf_url"), "values": row} for row in preview],
        }

    def search_answer(self, question: str, document: dict[str, Any], terms: list[str]) -> dict[str, Any]:
        snippets = snippets_for_terms(document.get("text", ""), terms)
        if not snippets:
            return self.missing_answer(question, document=document)
        return {
            "question": question,
            "answer": (
                f"I found {len(snippets)} capped snippet(s) in {document.get('label')} for {', '.join(terms[:4])}: "
                f"{' | '.join(snippets)}. Official PDF: {document.get('pdf_url')}."
            ),
            "retrieved_context_id": f"ag_market_report_document_index:search:{document.get('report_code')}",
            "retrieved_source": "ag_market_report_document_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Search snippets from capped local extraction of the official Agricultural Market News PDF.",
            "citations": self.citation(document=document, matched_rows=len(snippets)),
            "source_rows": [
                {
                    "source_file": document.get("pdf_url"),
                    "values": {
                        "report_code": document.get("report_code"),
                        "label": document.get("label"),
                        "matched_terms": ", ".join(terms),
                        "snippets": " | ".join(snippets),
                    },
                }
            ],
        }

    def missing_answer(
        self,
        question: str,
        message: str | None = None,
        document: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "question": question,
            "answer": message
            or (
                "I have a capped Agricultural Market News report document index, but that exact report/value is not parsed. "
                "Try `What Agricultural Market News report text is indexed?`, `What were Joplin feeder cattle total receipts?`, "
                "or `What price range did Joplin list for 502-547 lb Medium and Large 1 steers?`."
            ),
            "retrieved_context_id": "ag_market_report_document_index:no_match",
            "retrieved_source": "ag_market_report_document_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Answered from Agricultural Market News document coverage metadata because no selected parsed value matched.",
            "citations": self.citation(document=document),
            "source_rows": [],
        }

    def answer(self, question: str) -> dict[str, Any] | None:
        if not self.available():
            return self.unavailable_answer(question)
        lowered = question.lower()
        if re.search(r"\bshould\s+i\s+(buy|sell|trade)\b", lowered) or "buying advice" in lowered:
            return {
                "question": question,
                "answer": (
                    "I can summarize indexed Agricultural Market News report facts, but I cannot provide buying, selling, trading, or forecast advice. "
                    "Ask for the report date, demand/supply wording, or a specific parsed price range with the official PDF link."
                ),
                "retrieved_context_id": "ag_market_report_document_index:advice_guardrail",
                "retrieved_source": "ag_market_report_document_lookup_index",
                "retrieval_score": 1.0,
                "used_model": False,
                "model": "unsupported_scope_guardrail",
                "source_note": "Market-report facts are allowed; buying/selling advice and forecasts are outside this prototype.",
                "citations": self.citation(),
                "source_rows": [],
            }
        if any(term in lowered for term in ["indexed", "coverage", "what data", "data is parsed", "parsed", "document text", "pdf text"]):
            return self.summary_answer(question)
        document = self.find_document(question)
        if document is None:
            return self.missing_answer(question)
        if any(term in lowered for term in ["hay", "alfalfa", "mixed grass", "straw"]) and any(
            term in lowered for term in ["price", "prices", "range", "ranges", "per ton", "per bale", "bale"]
        ):
            return self.hay_price_answer(question, document)
        if any(term in lowered for term in ["receipt", "receipts", "volume"]):
            return self.receipts_answer(question, document)
        if any(term in lowered for term in ["price", "prices", "price range", "average price", "avg price"]) and any(
            term in lowered for term in ["steer", "steers", "502", "547", "pound", "lb"]
        ):
            return self.price_answer(question, document)
        terms = requested_search_terms(question)
        if terms and any(term in lowered for term in ["find", "search", "mention", "mentions", "snippet", "inside", "note"]):
            return self.search_answer(question, document, terms)
        return self.explain_answer(question, document)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--max-mb", type=float, default=3.0)
    parser.add_argument("--max-pages-per-document", type=int, default=8)
    parser.add_argument("--max-chars-per-document", type=int, default=24_000)
    parser.add_argument("--report-code", action="append", default=[])
    parser.add_argument("--delay-seconds", type=float, default=0.05)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    payload = build_ag_market_report_document_index(
        limit=args.limit,
        max_mb=args.max_mb,
        max_pages_per_document=args.max_pages_per_document,
        max_chars_per_document=args.max_chars_per_document,
        report_codes=args.report_code or DEFAULT_REPORT_CODES,
        delay_seconds=args.delay_seconds,
        force=args.force,
    )
    print(json.dumps({key: value for key, value in payload.items() if key != "documents"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
