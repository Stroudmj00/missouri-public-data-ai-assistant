"""Provider layer for evidence-grounded deep answers."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Protocol


PROJECT_NAME = "Missouri Public Data AI Assistant"
DEFAULT_VERTEX_MODEL = "gemini-3-flash-preview"
DEFAULT_THINKING_LEVEL = "MEDIUM"


EVIDENCE_TOOLS = [
    {
        "name": "search_public_records",
        "description": "Search indexed Missouri public-data sources and return compact matching evidence.",
    },
    {
        "name": "exact_record_lookup",
        "description": "Return exact public-record or aggregate facts when a local index supports the question.",
    },
    {
        "name": "source_family_search",
        "description": "Rank relevant Missouri source families and explain the evidence type available.",
    },
    {
        "name": "compare_records",
        "description": "Compare cited public records or aggregate rows already returned by local indexes.",
    },
    {
        "name": "aggregate_public_records",
        "description": "Use indexed aggregate rows for rankings, top lists, counts, and trend-style summaries.",
    },
]


class DeepAnswerProvider(Protocol):
    name: str
    model_id: str

    def is_available(self) -> bool:
        """Return whether the provider can make a live synthesis call."""

    def generate(self, question: str, evidence_bundle: dict[str, Any]) -> dict[str, Any]:
        """Generate a grounded answer from the supplied evidence bundle."""


@dataclass
class UnavailableDeepAnswerProvider:
    """Provider used by tests and offline runs to exercise fallback behavior."""

    reason: str = "Vertex AI credentials are not configured."
    name: str = "vertex_gemini"
    model_id: str = DEFAULT_VERTEX_MODEL

    def is_available(self) -> bool:
        return False

    def generate(self, question: str, evidence_bundle: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError(self.reason)


@dataclass
class FakeDeepAnswerProvider:
    """Deterministic provider for tests that should not require cloud credentials."""

    name: str = "fake_deep_answer"
    model_id: str = "fake-gemini"
    available: bool = True

    def is_available(self) -> bool:
        return self.available

    def generate(self, question: str, evidence_bundle: dict[str, Any]) -> dict[str, Any]:
        if not self.available:
            raise RuntimeError("Fake provider intentionally unavailable.")
        direct = evidence_bundle.get("direct_tool_result", {})
        raw_answer = str(direct.get("answer") or "").strip()
        family = str(direct.get("source_family") or "Missouri public data")
        evidence_hits = list(evidence_bundle.get("evidence_hits") or [])
        raw_summary = str(evidence_bundle.get("raw_evidence_summary") or "").strip()
        if raw_answer and evidence_hits:
            answer = f"Deep answer from {family} using {len(evidence_hits)} evidence hit(s): {raw_answer}"
        elif raw_summary:
            answer = f"Deep answer from {family}: {raw_summary}"
        elif raw_answer:
            answer = f"Deep answer from {family}: {raw_answer}"
        else:
            answer = "Deep answer unavailable because the local tools returned no supported evidence."
        return {
            "answer": answer,
            "confidence": evidence_bundle.get("routing_confidence", 0.0),
            "limitations": evidence_bundle.get("limitations", []),
            "provider_metadata": {"fake": True},
        }


@dataclass
class VertexGeminiProvider:
    """Vertex AI Gemini provider.

    The Google Gen AI SDK is intentionally imported lazily so default tests can
    run without Google Cloud dependencies or credentials.
    """

    model_id: str = DEFAULT_VERTEX_MODEL
    thinking_level: str = DEFAULT_THINKING_LEVEL
    name: str = "vertex_gemini"

    def __post_init__(self) -> None:
        self.model_id = os.getenv("MISSOURI_DEEP_ANSWER_MODEL", self.model_id)
        self.thinking_level = os.getenv("MISSOURI_VERTEX_THINKING_LEVEL", self.thinking_level).upper()

    def is_available(self) -> bool:
        return bool(os.getenv("GOOGLE_CLOUD_PROJECT") and os.getenv("GOOGLE_CLOUD_LOCATION"))

    def generate(self, question: str, evidence_bundle: dict[str, Any]) -> dict[str, Any]:
        if not self.is_available():
            raise RuntimeError("GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION are required for Vertex AI.")
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise RuntimeError("Install google-genai to use Vertex AI deep answers.") from exc

        project = os.environ["GOOGLE_CLOUD_PROJECT"]
        location = os.environ["GOOGLE_CLOUD_LOCATION"]
        client = genai.Client(vertexai=True, project=project, location=location)
        prompt = build_vertex_prompt(question, evidence_bundle)
        thinking_level = getattr(types.ThinkingLevel, self.thinking_level, types.ThinkingLevel.MEDIUM)
        response = client.models.generate_content(
            model=self.model_id,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
                system_instruction=(
                    "You are Missouri Public Data AI Assistant. Answer only from the supplied "
                    "Missouri public-data evidence. Preserve names, years, dollars, counts, URLs, "
                    "and stated limits exactly. Refuse unsupported claims."
                ),
                thinking_config=types.ThinkingConfig(thinking_level=thinking_level),
            ),
        )
        answer = str(getattr(response, "text", "") or "").strip()
        if not answer:
            raise RuntimeError("Vertex AI returned an empty answer.")
        return {
            "answer": answer,
            "confidence": evidence_bundle.get("routing_confidence", 0.0),
            "limitations": evidence_bundle.get("limitations", []),
            "provider_metadata": {
                "project": project,
                "location": location,
                "thinking_level": self.thinking_level,
            },
        }


def create_default_provider() -> DeepAnswerProvider:
    provider_name = os.getenv("MISSOURI_DEEP_ANSWER_PROVIDER", "vertex").lower()
    if provider_name in {"off", "none", "unavailable"}:
        return UnavailableDeepAnswerProvider()
    if provider_name == "fake":
        return FakeDeepAnswerProvider()
    return VertexGeminiProvider()


def compact_citations(citations: list[dict[str, Any]], limit: int = 4) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for citation in citations[:limit]:
        files = []
        for source_file in citation.get("source_files", [])[:4]:
            files.append(
                {
                    "label": source_file.get("category_label") or source_file.get("category"),
                    "file_name": source_file.get("file_name"),
                    "source_url": source_file.get("source_url"),
                    "row_count": source_file.get("row_count"),
                }
            )
        compact.append(
            {
                "dataset": citation.get("dataset"),
                "category": citation.get("category"),
                "kind": citation.get("kind") or citation.get("lookup_table"),
                "year": citation.get("year"),
                "year_range": citation.get("year_range"),
                "matched_rows": citation.get("matched_rows"),
                "source_files": files,
            }
        )
    return compact


def compact_source_rows(source_rows: list[dict[str, Any]], limit: int = 3) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for row in source_rows[:limit]:
        values = row.get("values")
        if isinstance(values, dict):
            value_preview = {
                str(key): values[key]
                for key in list(values)[:8]
                if key not in {"address", "phone", "fax", "email", "contact_name", "administrator_name"}
            }
        else:
            value_preview = values
        compact.append(
            {
                "source_file": row.get("source_file"),
                "values": value_preview,
            }
        )
    return compact


def compact_evidence_hits(evidence_hits: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for hit in evidence_hits[:limit]:
        compact.append(
            {
                "hit_id": hit.get("hit_id"),
                "source_key": hit.get("source_key"),
                "domain": hit.get("domain"),
                "title": hit.get("title"),
                "snippet": hit.get("snippet"),
                "source_url": hit.get("source_url"),
                "source_date": hit.get("source_date"),
                "evidence_type": hit.get("evidence_type"),
                "confidence": hit.get("confidence"),
                "citation": hit.get("citation"),
                "source_rows": compact_source_rows(list(hit.get("source_rows") or []), limit=2),
                "limitations": hit.get("limitations", []),
            }
        )
    return compact


def evidence_tool_for_result(result: dict[str, Any]) -> str:
    model = str(result.get("model") or "")
    source = str(result.get("retrieved_source") or result.get("source") or result.get("retrieved_context_id") or "")
    evidence_type = str(result.get("evidence_type") or "")
    answer = str(result.get("answer") or "").lower()
    if source == "generalized_evidence_index":
        return "search_public_records"
    if model in {"public_data_boundary", "unsupported_scope_guardrail", "retrieval_guardrail"}:
        return "source_family_search"
    if "compare" in answer or "change from" in answer or "difference" in answer:
        return "compare_records"
    if "ranking" in answer or "highest" in answer or "top " in answer:
        return "aggregate_public_records"
    if "source discovery" in evidence_type or "source" in source:
        return "source_family_search"
    if model == "deterministic_public_lookup":
        return "exact_record_lookup"
    return "search_public_records"


def build_evidence_bundle(question: str, result: dict[str, Any]) -> dict[str, Any]:
    tool_name = evidence_tool_for_result(result)
    route_candidates = result.get("route_candidates", [])
    evidence_hits = compact_evidence_hits(list(result.get("evidence_hits") or []))
    limitations = []
    if result.get("guardrail_reason"):
        limitations.append(f"Guardrail reason: {result['guardrail_reason']}")
    if not result.get("citations") and not evidence_hits:
        limitations.append("No public-data citation was attached to this result.")
    if result.get("raw_evidence_summary"):
        limitations.extend(str(item) for item in result.get("limitations") or [])
    return {
        "assistant_name": PROJECT_NAME,
        "question": question,
        "available_evidence_tools": EVIDENCE_TOOLS,
        "tool_calls": [
            {
                "tool": tool_name,
                "status": "completed",
                "source": result.get("retrieved_source") or result.get("source") or result.get("retrieved_context_id"),
                "source_family": result.get("source_family"),
                "evidence_type": result.get("evidence_type"),
                "retrieval_path": result.get("retrieval_path"),
            }
        ],
        "direct_tool_result": {
            "answer": result.get("answer"),
            "source_family": result.get("source_family"),
            "evidence_type": result.get("evidence_type"),
            "retrieval_path": result.get("retrieval_path"),
            "routing_confidence": result.get("routing_confidence"),
        },
        "routing_confidence": result.get("routing_confidence", 0.0),
        "route_candidates": route_candidates[:5],
        "citations": compact_citations(list(result.get("citations") or [])),
        "source_rows": compact_source_rows(list(result.get("source_rows") or [])),
        "evidence_hits": evidence_hits,
        "evidence_bundle_id": result.get("evidence_bundle_id"),
        "raw_evidence_summary": result.get("raw_evidence_summary"),
        "limitations": limitations,
    }


def build_vertex_prompt(question: str, evidence_bundle: dict[str, Any]) -> str:
    return (
        "Answer the user as Missouri Public Data AI Assistant.\n"
        "Use only the supplied local evidence-tool output. Do not use model memory for public facts.\n"
        "Include a concise answer, cite the relevant public source names or URLs when present, and state limits.\n\n"
        f"User question:\n{question}\n\n"
        "Evidence bundle JSON:\n"
        f"{json.dumps(evidence_bundle, indent=2, sort_keys=True)}"
    )
