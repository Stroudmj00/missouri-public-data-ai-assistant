"""Local extraction for public Missouri contract documents.

This module keeps downloaded documents and extracted text under data/raw_public,
which is ignored by Git. The default limits are intentionally conservative.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from pypdf import PdfReader

from missouri_public_data_ai.contract_lookup import CONTRACT_INDEX_PATH
from missouri_public_data_ai.evidence_index import EVIDENCE_MANIFEST_PATH, load_manifest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_RAW_DIR = PROJECT_ROOT / "data" / "raw_public" / "contracts"
DOCUMENT_DIR = CONTRACT_RAW_DIR / "documents"
CONTRACT_DOCUMENT_INDEX_PATH = CONTRACT_RAW_DIR / "missouri_contract_documents_index.json"
REPORTS_DIR = PROJECT_ROOT / "reports"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize_text(value: Any) -> str:
    text = clean_text(str(value or "")).lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def document_filename(contract_number: str, url: str) -> str:
    suffix = Path(url.split("?", 1)[0]).suffix.lower() or ".pdf"
    safe_contract = re.sub(r"[^A-Z0-9_-]+", "_", contract_number.upper())
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(url.split("?", 1)[0]).stem)[:80]
    return f"{safe_contract}_{stem}{suffix}"


def load_contract_payload() -> dict[str, Any]:
    if not CONTRACT_INDEX_PATH.exists():
        raise FileNotFoundError(
            f"Contract metadata index not found at {CONTRACT_INDEX_PATH}. "
            "Run scripts/build_contract_index.py first."
        )
    return json.loads(CONTRACT_INDEX_PATH.read_text(encoding="utf-8"))


def selected_public_contract_documents() -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    if not EVIDENCE_MANIFEST_PATH.exists():
        return documents
    manifest = load_manifest(EVIDENCE_MANIFEST_PATH)
    for source in manifest.get("source_families", []):
        if source.get("domain") != "contracts" or source.get("source_type") != "inline_text":
            continue
        values = dict(source.get("values") or {})
        if not values.get("contract_number") or not source.get("text"):
            continue
        copied = {
            **values,
            "text": str(source.get("text") or ""),
            "url": values.get("url") or source.get("source_url"),
            "detail_url": values.get("detail_url") or source.get("source_url"),
            "label": values.get("label") or source.get("title"),
            "source_scope": values.get("source_scope") or source.get("evidence_type"),
        }
        copied["text_chars"] = len(str(copied.get("text") or ""))
        copied.setdefault("bytes", None)
        copied.setdefault("local_file", None)
        documents.append(copied)
    return documents


def iter_pdf_documents(contracts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen_urls: set[str] = set()
    documents: list[dict[str, Any]] = []
    for contract in contracts:
        for document in contract.get("document_links", []):
            url = document.get("url", "")
            if not url.lower().endswith(".pdf") or url in seen_urls:
                continue
            seen_urls.add(url)
            documents.append(
                {
                    "contract_number": contract.get("contract_number", ""),
                    "description": contract.get("description", ""),
                    "contractor": contract.get("contractor", ""),
                    "contract_period": contract.get("contract_period", ""),
                    "detail_url": contract.get("detail_url", ""),
                    "label": document.get("label", "PDF document"),
                    "url": url,
                }
            )
    return documents


def extract_pdf_text(pdf_bytes: bytes, max_chars: int) -> tuple[str, int]:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    page_text: list[str] = []
    for page in reader.pages:
        if sum(len(item) for item in page_text) >= max_chars:
            break
        page_text.append(page.extract_text() or "")
    text = clean_text("\n".join(page_text))
    return text[:max_chars], len(reader.pages)


def build_contract_document_index(
    limit: int = 50,
    max_mb: float = 25.0,
    max_chars_per_document: int = 12_000,
    delay_seconds: float = 0.05,
    force: bool = False,
) -> dict[str, Any]:
    if CONTRACT_DOCUMENT_INDEX_PATH.exists() and not force:
        return json.loads(CONTRACT_DOCUMENT_INDEX_PATH.read_text(encoding="utf-8"))

    payload = load_contract_payload()
    candidates = iter_pdf_documents(list(payload.get("contracts", [])))
    session = requests.Session()
    max_bytes = int(max_mb * 1024 * 1024)
    downloaded_bytes = 0
    documents: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    start = time.perf_counter()

    for candidate in candidates:
        if len(documents) >= limit or downloaded_bytes >= max_bytes:
            break
        try:
            response = session.get(candidate["url"], timeout=60)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            pdf_bytes = response.content
            if "pdf" not in content_type.lower() and not pdf_bytes.startswith(b"%PDF"):
                raise ValueError(f"Response does not look like a PDF: {content_type}")
            if downloaded_bytes + len(pdf_bytes) > max_bytes:
                break
            local_name = document_filename(candidate["contract_number"], candidate["url"])
            local_path = DOCUMENT_DIR / local_name
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_bytes(pdf_bytes)
            text, page_count = extract_pdf_text(pdf_bytes, max_chars_per_document)
            documents.append(
                {
                    **candidate,
                    "local_file": str(local_path.relative_to(PROJECT_ROOT)),
                    "bytes": len(pdf_bytes),
                    "page_count": page_count,
                    "text_chars": len(text),
                    "text": text,
                }
            )
            downloaded_bytes += len(pdf_bytes)
        except Exception as exc:  # noqa: BLE001 - continue indexing other public documents.
            errors.append({"url": candidate["url"], "contract_number": candidate["contract_number"], "error": str(exc)})
        if delay_seconds > 0:
            time.sleep(delay_seconds)

    output = {
        "generated_at_utc": utc_now(),
        "source_contract_index": str(CONTRACT_INDEX_PATH.relative_to(PROJECT_ROOT)),
        "candidate_pdf_count": len(candidates),
        "document_count": len(documents),
        "downloaded_bytes": downloaded_bytes,
        "downloaded_mb": round(downloaded_bytes / 1024 / 1024, 3),
        "limit": limit,
        "max_mb": max_mb,
        "max_chars_per_document": max_chars_per_document,
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "error_count": len(errors),
        "errors": errors,
        "documents": documents,
        "notes": [
            "Downloaded PDFs and extracted text are local-only and ignored by Git.",
            "The index is intentionally capped so it can be built without overwhelming a laptop.",
            "Document explanations should cite the contract metadata and document URL.",
        ],
    }
    write_json(CONTRACT_DOCUMENT_INDEX_PATH, output)
    write_json(
        REPORTS_DIR / "contract_document_index_report.json",
        {key: value for key, value in output.items() if key not in {"documents"}},
    )
    return output


class ContractDocumentIndex:
    def __init__(self, path: Path = CONTRACT_DOCUMENT_INDEX_PATH) -> None:
        self.path = path
        self._payload: dict[str, Any] | None = None

    def available(self) -> bool:
        return self.path.exists() and self.path.stat().st_size > 0

    def payload(self) -> dict[str, Any]:
        if self._payload is None:
            self._payload = json.loads(self.path.read_text(encoding="utf-8")) if self.available() else {}
        return self._payload

    def summary(self) -> dict[str, Any]:
        payload = self.payload()
        selected = selected_public_contract_documents()
        examples = []
        for document in [*payload.get("documents", []), *selected][:5]:
            examples.append(
                {
                    "contract_number": document.get("contract_number"),
                    "description": document.get("description"),
                    "contractor": document.get("contractor"),
                    "label": document.get("label"),
                    "url": document.get("url"),
                    "page_count": document.get("page_count"),
                    "text_chars": document.get("text_chars"),
                }
            )
        return {
            "available": self.available(),
            "candidate_pdf_count": payload.get("candidate_pdf_count", 0),
            "document_count": payload.get("document_count", 0),
            "downloaded_mb": payload.get("downloaded_mb", 0),
            "max_chars_per_document": payload.get("max_chars_per_document", 0),
            "selected_document_count": len(selected),
            "generated_at_utc": payload.get("generated_at_utc"),
            "examples": examples,
        }

    def documents(self) -> list[dict[str, Any]]:
        payload_documents = list(self.payload().get("documents", []))
        seen_urls = {str(document.get("url") or "") for document in payload_documents}
        selected = [
            document for document in selected_public_contract_documents() if str(document.get("url") or "") not in seen_urls
        ]
        return [*payload_documents, *selected]

    def find_by_contract_number(self, contract_number: str) -> dict[str, Any] | None:
        target = contract_number.upper()
        for document in self.documents():
            if str(document.get("contract_number", "")).upper() == target:
                return document
        return None

    def search_documents(self, question: str, limit: int = 5) -> list[dict[str, Any]]:
        question_norm = normalize_text(question)
        tokens = {
            token
            for token in question_norm.split()
            if len(token) >= 4
            and token
            not in {
                "contract",
                "contracts",
                "document",
                "documents",
                "text",
                "does",
                "they",
                "supposed",
                "required",
                "provide",
                "about",
                "with",
                "from",
                "that",
                "this",
            }
        }
        ranked: list[tuple[int, dict[str, Any]]] = []
        for document in self.documents():
            haystack = normalize_text(
                " ".join(
                    [
                        str(document.get("contract_number") or ""),
                        str(document.get("description") or ""),
                        str(document.get("contractor") or ""),
                        str(document.get("label") or ""),
                        str(document.get("text") or ""),
                    ]
                )
            )
            haystack_tokens = set(haystack.split())
            overlap = len(tokens & haystack_tokens)
            phrase_bonus = 0
            for phrase in ["fletcher daniels", "janitorial services", "break room", "kitchenette"]:
                if phrase in question_norm and phrase in haystack:
                    phrase_bonus += 3
            if overlap == 0 and phrase_bonus == 0:
                continue
            ranked.append((overlap * 10 + phrase_bonus, document))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [document for _, document in ranked[:limit]]

    def snippets_for_document(
        self,
        document: dict[str, Any],
        terms: list[str],
        max_snippets: int = 3,
        context_chars: int = 260,
    ) -> list[str]:
        if not document or not document.get("text"):
            return []
        text = clean_text(str(document.get("text") or ""))
        lowered = text.lower()
        seen: set[str] = set()
        snippets: list[str] = []
        normalized_terms = [normalize_text(term) for term in terms if normalize_text(term)]
        for term in normalized_terms:
            term_pattern = re.escape(term).replace(r"\ ", r"\s+")
            match = re.search(term_pattern, lowered)
            if not match:
                continue
            start = max(0, match.start() - context_chars // 2)
            end = min(len(text), match.end() + context_chars)
            left_boundary = max(text.rfind(". ", 0, start), text.rfind("\n", 0, start))
            right_boundary = text.find(". ", end)
            if left_boundary != -1:
                start = left_boundary + 1
            elif start > 0:
                next_space = text.find(" ", start)
                if next_space != -1 and next_space < match.start():
                    start = next_space + 1
            if right_boundary != -1:
                end = min(len(text), right_boundary + 1)
            snippet = clean_text(text[start:end])
            if len(snippet) > context_chars * 2:
                snippet = snippet[: context_chars * 2].rsplit(" ", 1)[0].strip() + "..."
            key = normalize_text(snippet)
            if snippet and key not in seen:
                seen.add(key)
                snippets.append(snippet)
            if len(snippets) >= max_snippets:
                break
        return snippets

    def search_snippets(
        self,
        contract_number: str,
        terms: list[str],
        max_snippets: int = 3,
        context_chars: int = 260,
    ) -> list[str]:
        document = self.find_by_contract_number(contract_number)
        return self.snippets_for_document(document or {}, terms, max_snippets=max_snippets, context_chars=context_chars)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--max-mb", type=float, default=25.0)
    parser.add_argument("--max-chars-per-document", type=int, default=12_000)
    parser.add_argument("--delay-seconds", type=float, default=0.05)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    payload = build_contract_document_index(
        limit=args.limit,
        max_mb=args.max_mb,
        max_chars_per_document=args.max_chars_per_document,
        delay_seconds=args.delay_seconds,
        force=args.force,
    )
    print(json.dumps({key: value for key, value in payload.items() if key != "documents"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
