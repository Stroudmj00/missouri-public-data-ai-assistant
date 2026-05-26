"""Capped text extraction for selected Missouri Public Service Commission report PDFs."""

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

from missouri_public_data_ai.psc_reports_index import INDEX_PATH as PSC_METADATA_INDEX_PATH
from missouri_public_data_ai.psc_reports_index import LANDING_PAGE, build_psc_reports_index, requested_volume, requested_years


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw_public" / "psc_report_documents"
DOCUMENT_DIR = RAW_DIR / "documents"
INDEX_PATH = RAW_DIR / "psc_report_documents_index.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "psc_report_document_index_report.json"
SOURCE_NAME = "Missouri Public Service Commission selected report PDFs"

TOPIC_TERMS = {
    "electric": ("electric", "electricity", "amerens", "ameren", "kcp&l", "evergy"),
    "gas": ("gas", "natural gas", "spire"),
    "water": ("water",),
    "sewer": ("sewer",),
    "telecommunications": ("telecommunications", "telecom", "telephone"),
    "consumer": ("consumer", "customers"),
    "rate": ("rate", "tariff"),
    "solar": ("solar", "renewable"),
    "orders": ("order", "orders", "report and order", "reports and orders"),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def clean_text(value: Any) -> str:
    text = re.sub(r"_+", " ", str(value or ""))
    text = re.sub(r"\b(19|20)\s+(\d{2})\b", r"\1\2", text)
    return re.sub(r"\s+", " ", text).strip()


def safe_pdf_name(record: dict[str, Any], url: str) -> str:
    volume = int(record.get("volume") or 0)
    end_year = record.get("end_year") or "unknown"
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(url.split("?", 1)[0]).stem)[:90]
    return f"psc_vol_{volume:02d}_{end_year}_{stem}.pdf"


def load_psc_metadata() -> dict[str, Any]:
    if not PSC_METADATA_INDEX_PATH.exists():
        return build_psc_reports_index(force=True)
    return json.loads(PSC_METADATA_INDEX_PATH.read_text(encoding="utf-8"))


def selected_records(payload: dict[str, Any], volumes: list[int], limit: int) -> list[dict[str, Any]]:
    records = [record for record in payload.get("records", []) if record.get("pdf_url")]
    if not volumes:
        return records[:limit]

    requested = set(volumes)
    selected: list[dict[str, Any]] = []
    seen: set[int] = set()
    for record in records:
        volume = int(record.get("volume") or 0)
        if volume in requested and volume not in seen:
            selected.append(record)
            seen.add(volume)
    for record in records:
        if len(selected) >= limit:
            break
        volume = int(record.get("volume") or 0)
        if volume and volume not in seen:
            selected.append(record)
            seen.add(volume)
    return selected[:limit]


def extract_pdf_text(pdf_bytes: bytes, max_pages: int, max_chars: int) -> tuple[str, int]:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    parts: list[str] = []
    for page in reader.pages[:max_pages]:
        if sum(len(item) for item in parts) >= max_chars:
            break
        parts.append(page.extract_text() or "")
    return clean_text("\n".join(parts))[:max_chars], len(reader.pages)


def extract_preface(text: str) -> str:
    match = re.search(r"\bPREFACE\b(.*?)(?:\bReported Cases\b|\bDIGEST\b|\bTABLE OF CONTENTS\b)", text, re.I | re.S)
    if not match:
        return ""
    return clean_text(match.group(1))[:900].strip(" .")


def topic_counts(text: str) -> dict[str, int]:
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
    lowered = text.lower()
    for term in terms:
        for match in re.finditer(re.escape(term.lower()), lowered):
            start = max(0, match.start() - 150)
            end = min(len(text), match.end() + 240)
            snippet = clean_text(text[start:end]).strip(" .")
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
    return list(dict.fromkeys(terms))


def normalize_document(record: dict[str, Any], pdf_url: str, local_file: Path, pdf_bytes: bytes, text: str, page_count: int, max_pages: int) -> dict[str, Any]:
    return {
        "title": record.get("title"),
        "volume": record.get("volume"),
        "volume_label": record.get("volume_label"),
        "series": record.get("series"),
        "start_label": record.get("start_label"),
        "end_label": record.get("end_label"),
        "start_date": record.get("start_date"),
        "end_date": record.get("end_date"),
        "start_year": record.get("start_year"),
        "end_year": record.get("end_year"),
        "years_covered": record.get("years_covered", []),
        "pdf_url": pdf_url,
        "landing_page": LANDING_PAGE,
        "local_file": str(local_file.relative_to(PROJECT_ROOT)),
        "bytes": len(pdf_bytes),
        "sha256": sha256_bytes(pdf_bytes),
        "page_count": page_count,
        "extracted_page_limit": max_pages,
        "text_chars": len(text),
        "preface": extract_preface(text),
        "topic_counts": topic_counts(text),
        "text": text,
    }


def build_psc_report_document_index(
    limit: int = 1,
    max_mb: float = 60.0,
    max_pages_per_document: int = 120,
    max_chars_per_document: int = 45_000,
    volumes: list[int] | None = None,
    delay_seconds: float = 0.05,
    force: bool = False,
) -> dict[str, Any]:
    if INDEX_PATH.exists() and not force:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))

    metadata = load_psc_metadata()
    records = selected_records(metadata, volumes or [], limit)
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
        pdf_url = str(record.get("pdf_url") or "")
        if not pdf_url or len(documents) >= limit or downloaded_bytes >= max_bytes:
            continue
        try:
            response = session.get(pdf_url, timeout=120)
            response.raise_for_status()
            pdf_bytes = response.content
            content_type = response.headers.get("content-type", "")
            if "pdf" not in content_type.lower() and not pdf_bytes.startswith(b"%PDF"):
                raise ValueError(f"Response does not look like a PDF: {content_type}")
            if downloaded_bytes + len(pdf_bytes) > max_bytes:
                errors.append(
                    {
                        "volume": str(record.get("volume") or ""),
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
            errors.append({"volume": str(record.get("volume") or ""), "url": pdf_url, "error": str(exc)})
        if delay_seconds > 0:
            time.sleep(delay_seconds)

    document_summaries = [
        {
            "title": document.get("title"),
            "volume": document.get("volume"),
            "volume_label": document.get("volume_label"),
            "start_label": document.get("start_label"),
            "end_label": document.get("end_label"),
            "pdf_url": document.get("pdf_url"),
            "bytes": document.get("bytes"),
            "page_count": document.get("page_count"),
            "extracted_page_limit": document.get("extracted_page_limit"),
            "text_chars": document.get("text_chars"),
            "preface_chars": len(document.get("preface") or ""),
            "topic_counts": document.get("topic_counts", {}),
        }
        for document in documents
    ]
    payload = {
        "generated_at_utc": utc_now(),
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "source": SOURCE_NAME,
        "source_url": LANDING_PAGE,
        "source_metadata_index": str(PSC_METADATA_INDEX_PATH.relative_to(PROJECT_ROOT)),
        "index_path": str(INDEX_PATH.relative_to(PROJECT_ROOT)),
        "candidate_pdf_count": sum(1 for record in metadata.get("records", []) if record.get("pdf_url")),
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
            "Downloaded PSC PDFs and extracted text are local-only and ignored by Git.",
            "The default build is intentionally capped to one recent report PDF because current volumes can be about 45 MB each.",
            "Answers provide plain-English orientation and search snippets with official PDF links.",
            "This is not legal advice, rate-case analysis, or a substitute for the official report wording.",
        ],
        "documents": documents,
    }
    write_json(INDEX_PATH, payload)
    write_json(REPORT_PATH, {key: value for key, value in payload.items() if key != "documents"})
    return payload


class PscReportDocumentIndex:
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

    def latest_document(self) -> dict[str, Any] | None:
        docs = self.documents()
        return docs[0] if docs else None

    def find_document(self, question: str) -> dict[str, Any] | None:
        volume = requested_volume(question)
        if volume is not None:
            for document in self.documents():
                if int(document.get("volume") or 0) == volume:
                    return document
            return None
        years = requested_years(question)
        if years:
            year = years[-1]
            for document in self.documents():
                if year in document.get("years_covered", []):
                    return document
            return None
        return self.latest_document()

    def citation(self, document: dict[str, Any] | None = None, matched_rows: int = 0) -> list[dict[str, Any]]:
        payload = self.payload()
        if document:
            source_files = [
                {
                    "category": "psc_report_document",
                    "category_label": document.get("volume_label") or document.get("title") or "PSC report PDF",
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
                    "category": "psc_report_document",
                    "category_label": "Missouri PSC reports",
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
                "category": "Utilities",
                "kind": "selected report PDF text",
                "lookup_table": "psc_report_document_index",
                "year": document.get("end_year") if document else None,
                "year_range": (
                    f"{document.get('start_year')}-{document.get('end_year')}"
                    if document and document.get("start_year") and document.get("end_year")
                    else None
                ),
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
                "The selected PSC report document text index has not been built yet. Run "
                "`python scripts/build_psc_report_document_index.py --limit 1 --max-mb 60 --force` "
                "to enable capped plain-English PDF explanations."
            ),
            "retrieved_context_id": "psc_report_document_index:missing",
            "retrieved_source": "psc_report_document_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "The PSC document route exists, but the local ignored PDF text index is missing.",
            "citations": [],
            "source_rows": [],
        }

    def summary_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        examples = "; ".join(
            f"{item.get('volume_label')} {item.get('title')}" for item in payload.get("document_summaries", [])[:3]
        )
        return {
            "question": question,
            "answer": (
                "The selected PSC report document text layer indexes capped text from official Public Service Commission report PDFs. "
                f"It currently has {payload.get('document_count', 0):,} PDF(s), {payload.get('downloaded_mb', 0)} MB downloaded locally, "
                f"and up to {payload.get('max_pages_per_document', 0):,} pages / {payload.get('max_chars_per_document', 0):,} characters extracted per document. "
                f"Indexed example: {examples}. It is for plain-English orientation and snippet search, not legal or rate-case advice."
            ),
            "retrieved_context_id": "psc_report_document_index:summary",
            "retrieved_source": "psc_report_document_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the capped local PSC report document text index.",
            "citations": self.citation(matched_rows=payload.get("document_count", 0)),
            "source_rows": [],
        }

    def explain_answer(self, question: str, document: dict[str, Any]) -> dict[str, Any]:
        preface = document.get("preface") or "The extracted text did not include a preface in the capped window."
        top_topics = ", ".join(f"{key} ({value})" for key, value in list(document.get("topic_counts", {}).items())[:5])
        return {
            "question": question,
            "answer": (
                f"{document.get('volume_label')} is `{document.get('title')}` and covers "
                f"{document.get('start_label')} through {document.get('end_label')}. Plain-English orientation: this is an official PSC report volume "
                "containing selected Commission reports and orders from that period. "
                f"Extracted preface context: {preface[:500]}. "
                f"Top terms in the capped extraction include: {top_topics or 'no tracked utility terms found'}. "
                f"Official PDF: {document.get('pdf_url')}. Read the PDF for the full regulatory wording."
            ),
            "retrieved_context_id": f"psc_report_document_index:explain:{document.get('volume')}",
            "retrieved_source": "psc_report_document_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Plain-English orientation from capped local extraction of the official PSC report PDF.",
            "citations": self.citation(document=document, matched_rows=1),
            "source_rows": [
                {
                    "source_file": document.get("pdf_url"),
                    "values": {
                        "volume_label": document.get("volume_label"),
                        "title": document.get("title"),
                        "covered_period": f"{document.get('start_label')} - {document.get('end_label')}",
                        "preface_excerpt": (document.get("preface") or "")[:260],
                        "top_terms": top_topics,
                    },
                }
            ],
        }

    def search_answer(self, question: str, document: dict[str, Any], terms: list[str]) -> dict[str, Any]:
        snippets = snippets_for_terms(document.get("text", ""), terms)
        if not snippets:
            return self.missing_answer(
                question,
                f"The capped PSC PDF text extraction did not find those terms in {document.get('volume_label')}. "
                "Try a broader term such as electric, gas, water, consumer, rate, or order.",
                document=document,
            )
        rendered = " | ".join(snippets)
        display_terms = ", ".join(terms[:4])
        return {
            "question": question,
            "answer": (
                f"I found {len(snippets)} capped text snippet(s) for {display_terms} in {document.get('volume_label')} "
                f"({document.get('start_label')} through {document.get('end_label')}). Snippets: {rendered}. "
                f"Official PDF: {document.get('pdf_url')}."
            ),
            "retrieved_context_id": f"psc_report_document_index:search:{document.get('volume')}",
            "retrieved_source": "psc_report_document_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Search snippets from capped local extraction of the official PSC report PDF.",
            "citations": self.citation(document=document, matched_rows=len(snippets)),
            "source_rows": [
                {
                    "source_file": document.get("pdf_url"),
                    "values": {
                        "volume_label": document.get("volume_label"),
                        "title": document.get("title"),
                        "matched_terms": ", ".join(terms),
                        "snippets": " | ".join(snippets),
                    },
                }
            ],
        }

    def missing_answer(self, question: str, message: str | None = None, document: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "question": question,
            "answer": message
            or (
                "I have a capped PSC report document text index, but that volume/year is not in the selected local PDF set. "
                "Try `What PSC report document text is indexed?` or `Explain PSC report volume 33 in simple terms.`"
            ),
            "retrieved_context_id": "psc_report_document_index:no_match",
            "retrieved_source": "psc_report_document_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Answered from PSC document coverage metadata because no selected PDF text matched.",
            "citations": self.citation(document=document),
            "source_rows": [],
        }

    def answer(self, question: str) -> dict[str, Any] | None:
        if not self.available():
            return self.unavailable_answer(question)
        lowered = question.lower()
        if any(term in lowered for term in ["indexed", "coverage", "what data", "document text", "pdf text"]):
            return self.summary_answer(question)
        document = self.find_document(question)
        if document is None:
            return self.missing_answer(question)
        terms = requested_search_terms(question)
        if terms and any(term in lowered for term in ["find", "search", "mention", "mentions", "snippet", "inside"]):
            return self.search_answer(question, document, terms)
        return self.explain_answer(question, document)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--max-mb", type=float, default=60.0)
    parser.add_argument("--max-pages-per-document", type=int, default=120)
    parser.add_argument("--max-chars-per-document", type=int, default=45_000)
    parser.add_argument("--volume", type=int, action="append", default=[])
    parser.add_argument("--delay-seconds", type=float, default=0.05)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    payload = build_psc_report_document_index(
        limit=args.limit,
        max_mb=args.max_mb,
        max_pages_per_document=args.max_pages_per_document,
        max_chars_per_document=args.max_chars_per_document,
        volumes=args.volume,
        delay_seconds=args.delay_seconds,
        force=args.force,
    )
    print(json.dumps({key: value for key, value in payload.items() if key != "documents"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
