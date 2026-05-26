"""Coordinator for exact local answers plus generalized evidence search."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Callable

from missouri_public_data_ai.evidence_index import EvidenceIndex, clean_text


GUARDRAIL_MODELS = {"public_data_boundary", "unsupported_scope_guardrail", "retrieval_guardrail"}
NON_PUBLIC_MODELS = {"general_chat"}


def truncate(value: str, max_chars: int = 700) -> str:
    text = clean_text(value)
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0].strip() + "..."


def first_source_url(citations: list[dict[str, Any]]) -> str | None:
    for citation in citations:
        for source_file in citation.get("source_files", []) or []:
            source_url = source_file.get("source_url") or source_file.get("file_name")
            if source_url:
                return str(source_url)
    return None


def citation_title(citations: list[dict[str, Any]], fallback: str) -> str:
    for citation in citations:
        dataset = citation.get("dataset")
        category = citation.get("category")
        if dataset and category:
            return f"{dataset} - {category}"
        if dataset:
            return str(dataset)
        if category:
            return str(category)
    return fallback


def hit_from_result(result: dict[str, Any]) -> dict[str, Any] | None:
    citations = list(result.get("citations") or [])
    answer = clean_text(result.get("answer"))
    if not citations or not answer:
        return None
    source = str(result.get("retrieved_source") or result.get("source") or result.get("retrieved_context_id") or "")
    source_family = str(result.get("source_family") or source or "Missouri public data")
    evidence_type = str(result.get("evidence_type") or "local evidence answer")
    source_url = first_source_url(citations)
    payload = {
        "source": source,
        "answer": answer,
        "citations": citations,
    }
    return {
        "hit_id": hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:24],
        "source_key": source or "direct_tool_result",
        "domain": source_family,
        "title": citation_title(citations, source_family),
        "snippet": truncate(answer),
        "source_url": source_url,
        "source_date": None,
        "evidence_type": evidence_type,
        "risk_tags": [],
        "citation": citations[0],
        "source_rows": list(result.get("source_rows") or [])[:5],
        "confidence": float(result.get("routing_confidence", result.get("retrieval_score", 0.0)) or 0.0),
        "limitations": list(result.get("limitations") or []),
    }


def evidence_bundle_id(question: str, hits: list[dict[str, Any]]) -> str:
    payload = {"question": question, "hits": [hit.get("hit_id") for hit in hits]}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def raw_evidence_summary(hits: list[dict[str, Any]]) -> str:
    if not hits:
        return "No cited local evidence was available."
    lines = []
    for index, hit in enumerate(hits, start=1):
        title = hit.get("title") or hit.get("source_key")
        snippet = truncate(str(hit.get("snippet") or ""), 360)
        lines.append(f"{index}. {title}: {snippet}")
    return "\n".join(lines)


def wants_multi_source(question: str) -> bool:
    lowered = question.lower()
    if any(term in lowered for term in ["briefing", "compare", "comparison", "pulls", "using"]):
        return True
    source_terms = [
        "unemployment",
        "taxable sales",
        "public health",
        "vital",
        "labor",
        "tax",
        "contract",
        "auditor",
        "psc",
        "agriculture",
    ]
    matched_count = 0
    for term in source_terms:
        if " " in term:
            matched = term in lowered
        else:
            matched = bool(re.search(rf"\b{re.escape(term)}\b", lowered))
        if matched:
            matched_count += 1
    return matched_count >= 2


def county_phrase(question: str) -> str | None:
    match = re.search(r"\b([A-Z][A-Za-z.' -]{1,40}?)\s+County\b", question)
    if not match:
        return None
    return f"{match.group(1).strip()} County"


def is_public_data_result(result: dict[str, Any]) -> bool:
    model = str(result.get("model") or "")
    if model in GUARDRAIL_MODELS or model in NON_PUBLIC_MODELS:
        return False
    if result.get("citations"):
        return True
    source = str(result.get("retrieved_source") or result.get("source") or "")
    return bool(source and source not in {"public_data_boundary", "unsupported_scope_guardrail"})


def is_positive_adapter_result(result: dict[str, Any]) -> bool:
    context_id = str(result.get("retrieved_context_id") or result.get("source") or "").lower()
    answer = str(result.get("answer") or "").lower()
    if "no_match" in context_id or "index_missing" in context_id:
        return False
    miss_phrases = [
        "could not match",
        "did not match",
        "i have indexed",
        "try asking",
        "no row matched",
        "no indexed",
    ]
    if any(phrase in answer for phrase in miss_phrases):
        return False
    return bool(result.get("citations"))


class EvidenceCoordinator:
    def __init__(self, engine: Any, evidence_index: EvidenceIndex | None = None) -> None:
        self.engine = engine
        self.evidence_index = evidence_index or EvidenceIndex()

    def exact_adapters(self, question: str) -> list[Callable[[str], dict[str, Any] | None]]:
        engine = self.engine
        lowered = question.lower()
        candidates: list[tuple[list[str], Callable[[str], dict[str, Any] | None]]] = [
            (["agriculture", "agricultural", "hay", "joplin", "cattle", "grain", "market report"], engine.ag_market_report_document_index.answer),
            (["agriculture", "agricultural", "hay", "joplin", "cattle", "grain", "market report"], engine.ag_market_news_index.answer),
            (["feed", "sample", "agriculture", "protein"], engine.data_mo_agriculture_index.answer),
            (["psc", "utility", "electric", "gas", "water", "sewer"], engine.psc_report_document_index.answer),
            (["psc", "utility", "electric", "gas", "water", "sewer"], engine.psc_reports_index.answer),
            (["audit", "auditor", "recommendation"], engine.state_auditor_document_index.answer),
            (["audit", "auditor", "recommendation"], engine.state_auditor_index.answer),
            (["taxable sales", "sales tax", "dor", "tax"], engine.dor_reports_index.answer),
            (["unemployment", "labor force", "labor", "meric"], engine.meric_labor_index.answer),
            (["vital", "birth", "births", "death", "deaths", "natural increase", "public health"], engine.dhss_vital_stats_index.answer),
            (["public health", "dhss", "brfss", "mophims"], engine.dhss_health_sources_index.answer),
            (["public health", "health data"], engine.data_mo_health_index.answer),
            (["data.mo.gov", "open data catalog"], engine.data_mo_catalog_index.answer),
            (["public data", "source discovery", "sources connected"], engine.public_source_index.answer),
        ]
        return [adapter for terms, adapter in candidates if any(term in lowered for term in terms)]

    def search_exact_adapters(self, question: str, limit: int = 4) -> list[dict[str, Any]]:
        hits: list[dict[str, Any]] = []
        for adapter in self.exact_adapters(question):
            for adapter_question in self.adapter_questions(adapter, question):
                try:
                    result = adapter(adapter_question)
                except Exception:  # noqa: BLE001 - an adapter miss should not block generalized evidence.
                    continue
                if not result or not is_positive_adapter_result(result):
                    continue
                hit = hit_from_result(self.engine.with_routing_metadata(adapter_question, result))
                if hit is not None:
                    hits.append(hit)
                    break
            if len(hits) >= limit:
                break
        return hits

    def adapter_questions(self, adapter: Callable[[str], dict[str, Any] | None], question: str) -> list[str]:
        county = county_phrase(question)
        if not county:
            return [question]
        lowered = question.lower()
        engine = self.engine
        queries = [question]
        if adapter.__self__ is engine.dor_reports_index and "taxable sales" in lowered:
            queries.insert(0, f"What were {county} taxable sales in 2025?")
        if adapter.__self__ is engine.meric_labor_index and any(term in lowered for term in ["unemployment", "labor"]):
            queries.insert(0, f"What is {county} unemployment rate in March 2026?")
        if adapter.__self__ is engine.dhss_vital_stats_index and any(
            term in lowered for term in ["vital", "birth", "death", "public health"]
        ):
            queries.insert(0, f"How many births and deaths were in {county} in 2023?")
        deduped: list[str] = []
        for query in queries:
            if query not in deduped:
                deduped.append(query)
        return deduped

    def search(self, question: str, current_result: dict[str, Any] | None = None, max_hits: int = 5) -> list[dict[str, Any]]:
        hits: list[dict[str, Any]] = []
        if current_result and is_public_data_result(current_result):
            direct_hit = hit_from_result(current_result)
            if direct_hit is not None:
                hits.append(direct_hit)
        if wants_multi_source(question):
            hits.extend(self.search_exact_adapters(question, limit=max_hits))
        hits.extend(self.evidence_index.search(question, limit=max_hits))

        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for hit in hits:
            key = "|".join(
                [
                    str(hit.get("source_key") or ""),
                    str(hit.get("source_url") or ""),
                    re.sub(r"\s+", " ", str(hit.get("snippet") or "").lower())[:160],
                ]
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(hit)
            if len(deduped) >= max_hits:
                break
        return deduped

    def enrich_result(self, question: str, result: dict[str, Any]) -> dict[str, Any]:
        if result.get("evidence_hits") is not None and result.get("raw_evidence_summary") is not None:
            return result
        if str(result.get("model") or "") in GUARDRAIL_MODELS:
            return {
                **result,
                "evidence_hits": [],
                "evidence_bundle_id": evidence_bundle_id(question, []),
                "raw_evidence_summary": "Guardrail response preserved before evidence retrieval or provider synthesis.",
            }
        if not is_public_data_result(result):
            return {
                **result,
                "evidence_hits": [],
                "evidence_bundle_id": evidence_bundle_id(question, []),
                "raw_evidence_summary": "No public-data evidence bundle was needed for this deterministic general-chat answer.",
            }
        hits = self.search(question, current_result=result, max_hits=5)
        return {
            **result,
            "evidence_hits": hits,
            "evidence_bundle_id": evidence_bundle_id(question, hits),
            "raw_evidence_summary": raw_evidence_summary(hits),
        }

    def generic_answer(self, question: str) -> dict[str, Any] | None:
        hits = self.search(question, current_result=None, max_hits=5)
        if not hits:
            return None
        top = hits[0]
        citations = [hit.get("citation") for hit in hits if hit.get("citation")]
        source_rows: list[dict[str, Any]] = []
        for hit in hits:
            source_rows.extend(list(hit.get("source_rows") or [])[:2])
        if len(hits) == 1:
            answer = (
                f"From {top.get('title')}: {top.get('snippet')} "
                "I can only answer this from the cited local evidence shown with the result."
            )
        else:
            answer = (
                "The generalized evidence layer found these cited local evidence hits:\n"
                f"{raw_evidence_summary(hits)}\n"
                "I can only answer from the cited local evidence shown with the result."
            )
        result = {
            "question": question,
            "answer": answer,
            "retrieved_context_id": f"generalized_evidence:{top.get('hit_id')}",
            "retrieved_source": "generalized_evidence_index",
            "retrieval_score": top.get("confidence", 0.0),
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Answered through the generalized SQLite FTS evidence index.",
            "citations": citations[:5],
            "source_rows": source_rows[:5],
            "evidence_hits": hits,
            "evidence_bundle_id": evidence_bundle_id(question, hits),
            "raw_evidence_summary": raw_evidence_summary(hits),
        }
        return self.engine.with_routing_metadata(question, result)
