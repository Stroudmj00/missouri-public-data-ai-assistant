"""Manifest-driven local evidence registry backed by SQLite FTS5."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_MANIFEST_PATH = PROJECT_ROOT / "configs" / "evidence_sources.yaml"
EVIDENCE_INDEX_PATH = PROJECT_ROOT / "data" / "raw_public" / "evidence" / "evidence.sqlite"
EVIDENCE_INDEX_REPORT_PATH = PROJECT_ROOT / "reports" / "evidence_index_report.json"

STOPWORDS = {
    "about",
    "according",
    "after",
    "also",
    "answer",
    "before",
    "being",
    "boone",
    "building",
    "could",
    "county",
    "does",
    "give",
    "have",
    "into",
    "missouri",
    "public",
    "question",
    "record",
    "records",
    "report",
    "reports",
    "should",
    "source",
    "sources",
    "state",
    "supposed",
    "that",
    "their",
    "there",
    "these",
    "they",
    "this",
    "through",
    "what",
    "when",
    "where",
    "which",
    "with",
    "would",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", value.lower()).strip("_")


def load_manifest(path: Path = EVIDENCE_MANIFEST_PATH) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Evidence manifest not found: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def resolve_project_path(value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def get_path_value(payload: Any, dotted_path: str | None) -> Any:
    if not dotted_path:
        return payload
    value = payload
    for part in dotted_path.split("."):
        if isinstance(value, dict):
            value = value.get(part)
        else:
            return None
    return value


def safe_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True)


def apply_allowed_and_suppressed_fields(record: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    allowed = set(source.get("allowed_fields") or [])
    suppressed = set(source.get("suppressed_fields") or [])
    if allowed:
        output = {key: record.get(key) for key in allowed if key in record}
    else:
        output = dict(record)
    for key in suppressed:
        output.pop(key, None)
    return output


def stringify_field_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, ensure_ascii=True)
    return str(value)


def build_citation(source: dict[str, Any], record: dict[str, Any], source_url: str | None) -> dict[str, Any]:
    citation = dict(source.get("citation") or {})
    citation.setdefault("dataset", source.get("title") or source.get("source_key"))
    citation.setdefault("category", source.get("domain") or "Public data")
    citation.setdefault("kind", source.get("evidence_type") or source.get("document_type") or "evidence")
    citation.setdefault("lookup_table", "generalized_evidence_index")
    files = citation.get("source_files")
    if not files:
        file_name = record.get("local_file") or record.get("file_name") or source_url or source.get("local_index_path")
        files = [
            {
                "category": source.get("domain"),
                "category_label": source.get("title") or source.get("source_key"),
                "file_name": str(file_name or source.get("source_key")),
                "source_url": source_url,
                "row_count": record.get("record_count"),
                "bytes": record.get("bytes"),
                "sha256": record.get("sha256"),
            }
        ]
    citation["source_files"] = files
    citation["source_file_count"] = len(files)
    citation.setdefault("matched_rows", 1)
    return citation


def chunk_text(text: str, max_chars: int, overlap: int) -> list[str]:
    text = clean_text(text)
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        if end < len(text):
            boundary = max(text.rfind(". ", start, end), text.rfind("; ", start, end))
            if boundary > start + max_chars // 2:
                end = boundary + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(0, end - overlap)
    return chunks


def evidence_id_for(source_key: str, title: str, text: str, values: dict[str, Any], chunk_index: int) -> str:
    digest = hashlib.sha256(
        safe_json(
            {
                "source_key": source_key,
                "title": title,
                "text": text,
                "values": values,
                "chunk_index": chunk_index,
            }
        ).encode("utf-8")
    ).hexdigest()
    return digest[:24]


def inline_records(source: dict[str, Any]) -> Iterable[dict[str, Any]]:
    values = dict(source.get("values") or {})
    text = clean_text(source.get("text"))
    if not text:
        return []
    return [
        {
            "source_key": source["source_key"],
            "domain": source.get("domain"),
            "title": source.get("title"),
            "text": text,
            "source_url": source.get("source_url"),
            "source_date": source.get("source_date"),
            "evidence_type": source.get("evidence_type") or source.get("document_type"),
            "risk_tags": list(source.get("risk_tags") or []),
            "citation": build_citation(source, values, source.get("source_url")),
            "values": apply_allowed_and_suppressed_fields(values, source),
        }
    ]


def json_document_records(source: dict[str, Any]) -> Iterable[dict[str, Any]]:
    path = resolve_project_path(source.get("local_index_path"))
    if path is None or not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = get_path_value(payload, source.get("records_path"))
    if not isinstance(records, list):
        return []
    output: list[dict[str, Any]] = []
    text_fields = list(source.get("text_fields") or [])
    for record in records:
        if not isinstance(record, dict):
            continue
        title = clean_text(record.get(source.get("title_field") or "title") or source.get("title") or source["source_key"])
        text_parts = [
            stringify_field_value(source.get("title") or source.get("source_key")),
            stringify_field_value(source.get("domain")),
            stringify_field_value(source.get("evidence_type") or source.get("document_type")),
            *[stringify_field_value(record.get(field)) for field in text_fields],
        ]
        text = clean_text(" ".join(part for part in text_parts if part))
        if not text:
            continue
        source_url = clean_text(record.get(source.get("source_url_field") or "source_url") or source.get("source_url"))
        source_date = clean_text(record.get(source.get("source_date_field") or "source_date") or source.get("source_date"))
        values = apply_allowed_and_suppressed_fields(record, source)
        output.append(
            {
                "source_key": source["source_key"],
                "domain": source.get("domain"),
                "title": title,
                "text": text,
                "source_url": source_url,
                "source_date": source_date,
                "evidence_type": source.get("evidence_type") or source.get("document_type"),
                "risk_tags": list(source.get("risk_tags") or []),
                "citation": build_citation(source, record, source_url),
                "values": values,
            }
        )
    return output


def text_file_records(source: dict[str, Any]) -> Iterable[dict[str, Any]]:
    path = resolve_project_path(source.get("local_path"))
    if path is None or not path.exists():
        return []
    text = clean_text(path.read_text(encoding="utf-8", errors="ignore"))
    if not text:
        return []
    record = {"file_name": str(path.relative_to(PROJECT_ROOT)), "bytes": path.stat().st_size}
    return [
        {
            "source_key": source["source_key"],
            "domain": source.get("domain"),
            "title": source.get("title") or path.name,
            "text": text,
            "source_url": source.get("source_url"),
            "source_date": source.get("source_date"),
            "evidence_type": source.get("evidence_type") or source.get("document_type") or "text file",
            "risk_tags": list(source.get("risk_tags") or []),
            "citation": build_citation(source, record, source.get("source_url")),
            "values": apply_allowed_and_suppressed_fields(record, source),
        }
    ]


def iter_manifest_records(manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for source in manifest.get("source_families", []):
        source_key = source.get("source_key")
        source_type = source.get("source_type")
        try:
            if source_type == "inline_text":
                source_records = list(inline_records(source))
            elif source_type == "json_documents":
                source_records = list(json_document_records(source))
            elif source_type in {"text_file", "html_file"}:
                source_records = list(text_file_records(source))
            else:
                skipped.append({"source_key": source_key, "reason": f"unsupported source_type {source_type!r}"})
                continue
            if not source_records:
                skipped.append({"source_key": source_key, "reason": "no local records found"})
            records.extend(source_records)
        except Exception as exc:  # noqa: BLE001 - report and continue other configured sources.
            skipped.append({"source_key": source_key, "reason": str(exc)})
    return records, skipped


def connect(path: Path = EVIDENCE_INDEX_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        DROP TABLE IF EXISTS evidence_records;
        DROP TABLE IF EXISTS evidence_fts;

        CREATE TABLE evidence_records (
            evidence_id TEXT PRIMARY KEY,
            source_key TEXT NOT NULL,
            domain TEXT,
            title TEXT,
            text TEXT NOT NULL,
            source_url TEXT,
            source_date TEXT,
            evidence_type TEXT,
            risk_tags TEXT,
            citation TEXT,
            values_json TEXT
        );

        CREATE VIRTUAL TABLE evidence_fts USING fts5(
            title,
            text,
            content='evidence_records',
            content_rowid='rowid'
        );
        """
    )


def build_evidence_index(
    manifest_path: Path = EVIDENCE_MANIFEST_PATH,
    index_path: Path = EVIDENCE_INDEX_PATH,
    report_path: Path = EVIDENCE_INDEX_REPORT_PATH,
    force: bool = False,
) -> dict[str, Any]:
    if index_path.exists() and not force:
        return json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {"index_path": str(index_path)}

    manifest = load_manifest(manifest_path)
    index_config = manifest.get("index", {})
    max_chars = int(index_config.get("chunk_chars") or 1400)
    overlap = int(index_config.get("chunk_overlap") or 180)
    records, skipped = iter_manifest_records(manifest)

    connection = connect(index_path)
    create_schema(connection)
    source_counts: Counter[str] = Counter()
    domain_counts: Counter[str] = Counter()
    inserted = 0
    for record in records:
        chunks = chunk_text(record["text"], max_chars=max_chars, overlap=overlap)
        for chunk_index, chunk in enumerate(chunks):
            values = dict(record.get("values") or {})
            values["chunk_index"] = chunk_index
            evidence_id = evidence_id_for(record["source_key"], record.get("title") or "", chunk, values, chunk_index)
            cursor = connection.execute(
                """
                INSERT OR REPLACE INTO evidence_records (
                    evidence_id, source_key, domain, title, text, source_url, source_date,
                    evidence_type, risk_tags, citation, values_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence_id,
                    record.get("source_key"),
                    record.get("domain"),
                    record.get("title"),
                    chunk,
                    record.get("source_url"),
                    record.get("source_date"),
                    record.get("evidence_type"),
                    safe_json(record.get("risk_tags") or []),
                    safe_json(record.get("citation") or {}),
                    safe_json(values),
                ),
            )
            rowid = cursor.lastrowid
            connection.execute(
                "INSERT OR REPLACE INTO evidence_fts(rowid, title, text) VALUES (?, ?, ?)",
                (rowid, record.get("title"), chunk),
            )
            source_counts[str(record.get("source_key"))] += 1
            domain_counts[str(record.get("domain"))] += 1
            inserted += 1
    connection.commit()
    connection.close()

    report = {
        "generated_at_utc": utc_now(),
        "manifest_path": str(manifest_path.relative_to(PROJECT_ROOT)),
        "index_path": str(index_path.relative_to(PROJECT_ROOT)),
        "source_family_count": len(manifest.get("source_families", [])),
        "record_count": inserted,
        "source_counts": dict(sorted(source_counts.items())),
        "domain_counts": dict(sorted(domain_counts.items())),
        "skipped_sources": skipped,
        "notes": [
            "The SQLite evidence index is local-only and ignored by Git.",
            "The tracked manifest defines ordinary public-data evidence sources without adding Python routes.",
            "Deep Answer receives evidence hits from this common layer and falls back to local evidence if unavailable.",
        ],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def ensure_evidence_index() -> None:
    if not EVIDENCE_INDEX_PATH.exists() and EVIDENCE_MANIFEST_PATH.exists():
        build_evidence_index(force=True)


def fts_query(question: str) -> str:
    terms = []
    for token in re.findall(r"[A-Za-z0-9]{3,}", question.lower()):
        if token in STOPWORDS:
            continue
        if token not in terms:
            terms.append(token)
    if not terms:
        return ""
    return " OR ".join(f"{term}*" for term in terms[:12])


def extract_match_snippet(text: str, question: str, max_chars: int = 520) -> str:
    text = clean_text(text)
    terms = [term for term in re.findall(r"[A-Za-z0-9]{4,}", question.lower()) if term not in STOPWORDS]
    lowered = text.lower()
    position = 0
    for term in terms:
        found = lowered.find(term)
        if found >= 0:
            position = found
            break
    start = max(0, position - max_chars // 3)
    end = min(len(text), start + max_chars)
    if start > 0:
        left = text.find(" ", start)
        if left > 0 and left < position:
            start = left + 1
    snippet = text[start:end].strip()
    if end < len(text):
        snippet = snippet.rsplit(" ", 1)[0].strip() + "..."
    return snippet


class EvidenceIndex:
    def __init__(self, path: Path = EVIDENCE_INDEX_PATH) -> None:
        self.path = path

    def available(self) -> bool:
        return self.path.exists() and self.path.stat().st_size > 0

    def search(self, question: str, limit: int = 5) -> list[dict[str, Any]]:
        ensure_evidence_index()
        if not self.available():
            return []
        query = fts_query(question)
        if not query:
            return []
        try:
            connection = connect(self.path)
            rows = connection.execute(
                """
                SELECT
                    evidence_records.rowid AS rowid,
                    evidence_records.*,
                    bm25(evidence_fts) AS rank
                FROM evidence_fts
                JOIN evidence_records ON evidence_records.rowid = evidence_fts.rowid
                WHERE evidence_fts MATCH ?
                ORDER BY rank ASC
                LIMIT ?
                """,
                (query, limit),
            ).fetchall()
            connection.close()
        except sqlite3.OperationalError:
            return []
        hits: list[dict[str, Any]] = []
        for row in rows:
            citation = json.loads(row["citation"] or "{}")
            values = json.loads(row["values_json"] or "{}")
            risk_tags = json.loads(row["risk_tags"] or "[]")
            hits.append(
                {
                    "hit_id": row["evidence_id"],
                    "source_key": row["source_key"],
                    "domain": row["domain"],
                    "title": row["title"],
                    "snippet": extract_match_snippet(row["text"], question),
                    "source_url": row["source_url"],
                    "source_date": row["source_date"],
                    "evidence_type": row["evidence_type"],
                    "risk_tags": risk_tags,
                    "citation": citation,
                    "values": values,
                    "source_rows": [{"source_file": row["source_url"] or row["source_key"], "values": values}],
                    "confidence": max(0.1, min(0.92, 0.78 - float(row["rank"]) / 20 if row["rank"] is not None else 0.55)),
                    "limitations": ["FTS hit from the generalized evidence index; verify against the cited source for operational use."],
                }
            )
        return hits


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    report = build_evidence_index(force=args.force)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
