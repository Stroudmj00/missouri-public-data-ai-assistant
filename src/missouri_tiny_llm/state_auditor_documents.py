"""Capped text extraction for selected Missouri State Auditor report PDFs."""

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

from missouri_tiny_llm.state_auditor_index import INDEX_PATH as AUDITOR_INDEX_PATH
from missouri_tiny_llm.state_auditor_index import LANDING_PAGE, SEARCH_URL


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw_public" / "state_auditor"
DOCUMENT_DIR = RAW_DIR / "documents"
INDEX_PATH = RAW_DIR / "state_auditor_documents_index.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "state_auditor_document_index_report.json"
SOURCE_NAME = "Missouri State Auditor selected report PDFs"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def report_digits(value: Any) -> str:
    return re.sub(r"[^0-9]", "", str(value or ""))


def local_pdf_name(record: dict[str, Any], url: str) -> str:
    number = report_digits(record.get("report_number") or record.get("report_number_display"))
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(url.split("?", 1)[0]).stem)[:80]
    return f"{number or 'auditor_report'}_{stem}.pdf"


def load_auditor_payload() -> dict[str, Any]:
    if not AUDITOR_INDEX_PATH.exists():
        raise FileNotFoundError(
            f"Auditor metadata index not found at {AUDITOR_INDEX_PATH}. "
            "Run scripts/build_state_auditor_index.py first."
        )
    return json.loads(AUDITOR_INDEX_PATH.read_text(encoding="utf-8"))


def selected_records(payload: dict[str, Any], report_numbers: list[str], limit: int) -> list[dict[str, Any]]:
    records = [record for record in payload.get("records", []) if record.get("pdf_url")]
    if not report_numbers:
        return records[:limit]

    requested = {report_digits(number) for number in report_numbers}
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        digits = report_digits(record.get("report_number") or record.get("report_number_display"))
        if digits in requested and digits not in seen:
            selected.append(record)
            seen.add(digits)
    for record in records:
        if len(selected) >= limit:
            break
        digits = report_digits(record.get("report_number") or record.get("report_number_display"))
        if digits not in seen:
            selected.append(record)
            seen.add(digits)
    return selected[:limit]


def extract_pdf_text(pdf_bytes: bytes, max_chars: int) -> tuple[str, int]:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    page_text: list[str] = []
    for page in reader.pages:
        if sum(len(item) for item in page_text) >= max_chars:
            break
        page_text.append(page.extract_text() or "")
    return clean_text("\n".join(page_text))[:max_chars], len(reader.pages)


def recommendation_summary(text: str) -> str:
    match = re.search(
        r"RECOMMENDATION SUMMARY\s+(.*?)(?:ANNUAL FINANCIAL REPORT|TABLE OF CONTENTS|INTRODUCTORY SECTION|APPENDIX)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return ""
    summary = clean_text(match.group(1))
    summary = re.split(
        r"\b(?:Management Advisory Report|Schedule of Findings|INTRODUCTORY SECTION|FINANCIAL SECTION)\b",
        summary,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    return summary[:1400].strip(" .")


def keyword_snippets(text: str, limit: int = 4) -> list[str]:
    snippets: list[str] = []
    patterns = [
        r"[^.]{0,80}\bbank reconciliations?\b[^.]{0,220}\.",
        r"[^.]{0,80}\bbudget(?:ary)? controls?\b[^.]{0,220}\.",
        r"[^.]{0,80}\bfederal awards?\b[^.]{0,220}\.",
        r"[^.]{0,80}\brecommend(?:ation|ations|ed)?\b[^.]{0,220}\.",
        r"[^.]{0,80}\binternal controls?\b[^.]{0,220}\.",
        r"[^.]{0,80}\bmaterial weakness(?:es)?\b[^.]{0,220}\.",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            snippet = clean_text(match.group(0))
            if snippet and snippet not in snippets:
                snippets.append(snippet)
            if len(snippets) >= limit:
                return snippets
    return snippets


def plain_takeaway(document: dict[str, Any]) -> str:
    source_text = clean_text(
        " ".join([*(document.get("snippets") or []), document.get("recommendation_summary") or ""])
    )
    lowered = source_text.lower()
    issues: list[str] = []
    if "bank reconciliation" in lowered:
        issues.append("monthly bank reconciliations")
    if "budget" in lowered:
        issues.append("budget controls and spending-limit procedures")
    if "federal award" in lowered or "sefa" in lowered:
        issues.append("federal awards reporting")
    if "internal control" in lowered:
        issues.append("internal controls")

    if issues:
        if len(issues) == 1:
            issue_text = issues[0]
        else:
            issue_text = ", ".join(issues[:-1]) + f", and {issues[-1]}"
        return f"The extracted recommendation text points to {issue_text}."
    if source_text:
        return source_text[:360].strip()
    return "The capped local extraction did not find a recommendation summary in the first extracted text window."


def normalize_document(record: dict[str, Any], pdf_url: str, local_file: Path, pdf_bytes: bytes, text: str, page_count: int) -> dict[str, Any]:
    summary = recommendation_summary(text)
    snippets = keyword_snippets(summary or text)
    return {
        "report_number": record.get("report_number"),
        "report_number_display": record.get("report_number_display"),
        "title": record.get("title"),
        "release_date": record.get("release_date"),
        "release_year": record.get("release_year"),
        "topics": record.get("topics", []),
        "view_report_url": record.get("view_report_url"),
        "pdf_url": pdf_url,
        "local_file": str(local_file.relative_to(PROJECT_ROOT)),
        "bytes": len(pdf_bytes),
        "sha256": sha256_bytes(pdf_bytes),
        "page_count": page_count,
        "text_chars": len(text),
        "recommendation_summary": summary,
        "snippets": snippets,
        "text": text,
    }


def build_state_auditor_document_index(
    limit: int = 10,
    max_mb: float = 25.0,
    max_chars_per_document: int = 18_000,
    report_numbers: list[str] | None = None,
    delay_seconds: float = 0.05,
    force: bool = False,
) -> dict[str, Any]:
    if INDEX_PATH.exists() and not force:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))

    metadata = load_auditor_payload()
    records = selected_records(metadata, report_numbers or [], limit)
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (compatible; MissouriPublicDataChat/1.0; +https://github.com/Stroudmj00/missouri-tiny-llm-case-study)",
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
        if not pdf_url:
            continue
        if len(documents) >= limit or downloaded_bytes >= max_bytes:
            break
        try:
            response = session.get(pdf_url, timeout=90)
            response.raise_for_status()
            pdf_bytes = response.content
            content_type = response.headers.get("content-type", "")
            if "pdf" not in content_type.lower() and not pdf_bytes.startswith(b"%PDF"):
                raise ValueError(f"Response does not look like a PDF: {content_type}")
            if downloaded_bytes + len(pdf_bytes) > max_bytes:
                break
            local_file = DOCUMENT_DIR / local_pdf_name(record, pdf_url)
            local_file.parent.mkdir(parents=True, exist_ok=True)
            local_file.write_bytes(pdf_bytes)
            text, page_count = extract_pdf_text(pdf_bytes, max_chars_per_document)
            documents.append(normalize_document(record, pdf_url, local_file, pdf_bytes, text, page_count))
            downloaded_bytes += len(pdf_bytes)
        except Exception as exc:  # noqa: BLE001 - continue indexing other public PDFs.
            errors.append(
                {
                    "report_number": str(record.get("report_number_display") or record.get("report_number") or ""),
                    "url": pdf_url,
                    "error": str(exc),
                }
            )
        if delay_seconds > 0:
            time.sleep(delay_seconds)

    document_summaries = [
        {
            "report_number": item.get("report_number"),
            "report_number_display": item.get("report_number_display"),
            "title": item.get("title"),
            "release_date": item.get("release_date"),
            "pdf_url": item.get("pdf_url"),
            "bytes": item.get("bytes"),
            "page_count": item.get("page_count"),
            "text_chars": item.get("text_chars"),
            "recommendation_summary_chars": len(item.get("recommendation_summary") or ""),
            "snippet_count": len(item.get("snippets") or []),
        }
        for item in documents
    ]
    payload = {
        "generated_at_utc": utc_now(),
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "source": SOURCE_NAME,
        "source_url": LANDING_PAGE,
        "source_metadata_index": str(AUDITOR_INDEX_PATH.relative_to(PROJECT_ROOT)),
        "index_path": str(INDEX_PATH.relative_to(PROJECT_ROOT)),
        "candidate_pdf_count": sum(1 for record in metadata.get("records", []) if record.get("pdf_url")),
        "document_count": len(documents),
        "downloaded_bytes": downloaded_bytes,
        "downloaded_mb": round(downloaded_bytes / 1024 / 1024, 3),
        "limit": limit,
        "max_mb": max_mb,
        "max_chars_per_document": max_chars_per_document,
        "error_count": len(errors),
        "errors": errors,
        "document_summaries": document_summaries,
        "notes": [
            "Downloaded Auditor PDFs and extracted text are local-only and ignored by Git.",
            "The index is intentionally capped so it can be built without overwhelming a laptop.",
            "Answers summarize extracted recommendation snippets and must link to the official report/PDF.",
            "This is not a legal or audit-opinion substitute.",
        ],
        "documents": documents,
    }
    write_json(INDEX_PATH, payload)
    write_json(REPORT_PATH, {key: value for key, value in payload.items() if key != "documents"})
    return payload


class StateAuditorDocumentIndex:
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

    def find_by_report_number(self, question: str) -> dict[str, Any] | None:
        compact = report_digits(question)
        for document in self.documents():
            number = report_digits(document.get("report_number") or document.get("report_number_display"))
            if number and number in compact:
                return document
        return None

    def citation(self, document: dict[str, Any] | None = None, matched_rows: int = 0) -> list[dict[str, Any]]:
        payload = self.payload()
        source_files: list[dict[str, Any]] = []
        if document:
            source_files.append(
                {
                    "category": "state_auditor_document",
                    "category_label": document.get("report_number_display") or document.get("title") or "Auditor report PDF",
                    "file_name": document.get("pdf_url"),
                    "source_url": document.get("pdf_url"),
                    "row_count": 1,
                    "bytes": document.get("bytes"),
                    "sha256": document.get("sha256"),
                }
            )
        else:
            source_files.append(
                {
                    "category": "state_auditor_document",
                    "category_label": "Missouri State Auditor reports",
                    "file_name": payload.get("source_url", LANDING_PAGE),
                    "source_url": payload.get("source_url", LANDING_PAGE),
                    "row_count": payload.get("document_count"),
                    "bytes": payload.get("downloaded_bytes"),
                    "sha256": None,
                }
            )
        return [
            {
                "dataset": payload.get("source", SOURCE_NAME),
                "category": "Audits and accountability",
                "kind": "selected report PDF text",
                "lookup_table": "state_auditor_document_index",
                "year": document.get("release_year") if document else None,
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
                "The selected Missouri State Auditor document text index has not been built yet. Run "
                "`python scripts/build_state_auditor_document_index.py --limit 10 --max-mb 25 --force` "
                "to enable capped PDF-text explanations."
            ),
            "retrieved_context_id": "state_auditor_document_index:missing",
            "retrieved_source": "state_auditor_document_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "The Auditor document route exists, but the local ignored PDF text index is missing.",
            "citations": [],
            "source_rows": [],
        }

    def summary_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        reports = "; ".join(
            f"{item.get('report_number_display')} {item.get('title')}"
            for item in payload.get("document_summaries", [])[:5]
        )
        return {
            "question": question,
            "answer": (
                "The selected Missouri State Auditor document text layer indexes capped text from official report PDFs. "
                f"It currently has {payload.get('document_count', 0):,} PDF(s), "
                f"{payload.get('downloaded_mb', 0)} MB downloaded locally, and up to "
                f"{payload.get('max_chars_per_document', 0):,} extracted characters per document. "
                f"Indexed examples: {reports}. It is for plain-English orientation, not a legal or audit-opinion substitute."
            ),
            "retrieved_context_id": "state_auditor_document_index:summary",
            "retrieved_source": "state_auditor_document_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the capped local Missouri State Auditor document text index.",
            "citations": self.citation(matched_rows=payload.get("document_count", 0)),
            "source_rows": [],
        }

    def explain_answer(self, question: str, document: dict[str, Any]) -> dict[str, Any]:
        topics = ", ".join(document.get("topics", [])) or "audit report"
        snippets = document.get("snippets") or []
        takeaway = plain_takeaway(document)
        return {
            "question": question,
            "answer": (
                f"Auditor report {document.get('report_number_display')} is `{document.get('title')}`, released "
                f"{document.get('release_date') or 'date not listed'}. Plain-English orientation: this is a {topics} report. "
                f"{takeaway} "
                f"The local PDF text index extracted {document.get('text_chars', 0):,} characters from "
                f"{document.get('page_count', '?')} page(s). Read the official PDF for the full audit wording."
            ),
            "retrieved_context_id": f"state_auditor_document_index:explain:{document.get('report_number')}",
            "retrieved_source": "state_auditor_document_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Plain-English orientation from capped local extraction of the official Auditor PDF.",
            "citations": self.citation(document=document, matched_rows=1),
            "source_rows": [
                {
                    "source_file": document.get("pdf_url"),
                    "values": {
                        "report_number": document.get("report_number_display"),
                        "title": document.get("title"),
                        "release_date": document.get("release_date"),
                        "recommendation_summary": document.get("recommendation_summary"),
                        "snippets": snippets,
                    },
                }
            ],
        }

    def missing_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "I have a capped Auditor document text index, but that report was not in the selected local PDF set. "
                "Try `What Auditor document text is indexed?` or `Explain Auditor report 2026-044 in simple terms.`"
            ),
            "retrieved_context_id": "state_auditor_document_index:no_match",
            "retrieved_source": "state_auditor_document_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Answered from Auditor document coverage metadata because no selected PDF matched.",
            "citations": self.citation(),
            "source_rows": [],
        }

    def answer(self, question: str) -> dict[str, Any] | None:
        if not self.available():
            return self.unavailable_answer(question)
        lowered = question.lower()
        if any(term in lowered for term in ["indexed", "coverage", "what data", "document text", "pdf text"]):
            return self.summary_answer(question)
        document = self.find_by_report_number(question)
        if document is not None:
            return self.explain_answer(question, document)
        return self.missing_answer(question)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--max-mb", type=float, default=25.0)
    parser.add_argument("--max-chars-per-document", type=int, default=18_000)
    parser.add_argument("--report-number", action="append", default=[])
    parser.add_argument("--delay-seconds", type=float, default=0.05)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    payload = build_state_auditor_document_index(
        limit=args.limit,
        max_mb=args.max_mb,
        max_chars_per_document=args.max_chars_per_document,
        report_numbers=args.report_number,
        delay_seconds=args.delay_seconds,
        force=args.force,
    )
    print(json.dumps({key: value for key, value in payload.items() if key != "documents"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
