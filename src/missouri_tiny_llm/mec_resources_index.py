"""Build and query Missouri Ethics Commission public-resource metadata."""

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
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw_public" / "mec_resources"
INDEX_PATH = RAW_DIR / "mec_resources_index.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "mec_resources_index_report.json"
SOURCE_NAME = "Missouri Ethics Commission public records metadata"


@dataclass(frozen=True)
class MecPage:
    key: str
    label: str
    url: str
    default_topic: str


PAGES: tuple[MecPage, ...] = (
    MecPage("home", "MEC home", "https://mec.mo.gov/", "overview"),
    MecPage("campaign_home", "MEC Campaign Finance", "https://mec.mo.gov/MEC/Campaign_Finance/Home.aspx", "campaign finance"),
    MecPage("campaign_searches", "MEC Campaign Finance Searches", "https://mec.mo.gov/MEC/Campaign_Finance/Searches.aspx", "campaign finance searches"),
    MecPage("campaign_forms", "MEC Campaign Finance Forms", "https://mec.mo.gov/MEC/Campaign_Finance/Forms.aspx", "campaign finance forms"),
    MecPage("lobbying_home", "MEC Lobbying", "https://mec.mo.gov/MEC/Lobbying/Home.aspx", "lobbying"),
    MecPage("lobbying_searches", "MEC Lobbying Searches", "https://mec.mo.gov/MEC/Lobbying/Searches.aspx", "lobbying searches"),
    MecPage("commission_business", "MEC Commission Business", "https://mec.mo.gov/MEC/Commission_Business/Home.aspx", "commission business"),
    MecPage("pfd_home", "MEC Personal Financial Disclosure", "https://mec.mo.gov/MEC/PFD/Home.aspx", "financial disclosure/PFD"),
    MecPage("education_home", "MEC Resources and Training", "https://mec.mo.gov/MEC/Educational_Resources/Home.aspx", "training/resources"),
    MecPage("candidate_central", "MEC Candidate Central", "https://mec.mo.gov/MEC/Candidate_Central/Home.aspx", "candidate resources"),
    MecPage("conflict_interest", "MEC Conflict of Interest", "https://mec.mo.gov/MEC/Conflict_of_Interest/Home.aspx", "conflict of interest"),
)

ANCHOR_PATTERN = re.compile(r"<a\s+[^>]*href=['\"]([^'\"]+)['\"][^>]*>(.*?)</a>", re.I | re.S)
YEAR_PATTERN = re.compile(r"\b(20\d{2}|19\d{2})\b")

URL_LABEL_OVERRIDES = {
    "/MEC/Campaign_Finance/CF_SearchCommNew.aspx": "New Committee Registrations",
    "/MEC/Campaign_Finance/CFSearch.aspx": "Candidate or Committee Name",
    "/MEC/Campaign_Finance/CF12_SearchElection.aspx": "Candidates by Election",
    "/MEC/Campaign_Finance/CF_SearchDirExp.aspx": "Committee Expenditures for Candidates",
    "/MEC/Campaign_Finance/CF12_BallotSearch.aspx": "Ballot Measures by Election",
    "/MEC/Campaign_Finance/CF_SearchPOCD4_B.aspx": "Committee Expenditures for Ballot Measures",
    "/MEC/Campaign_Finance/CF12_ContrExpend.aspx": "Committee Contributions & Expenditures",
    "/MEC/Campaign_Finance/CF_SearchLrgContr.aspx": "Contributions Over $5,000",
    "/MEC/Campaign_Finance/CF14_nonCommExp.aspx": "Non-Committee Expenditures",
    "/MEC/Campaign_Finance/LLCSearch.aspx": "LLC Registration Search",
    "/MEC/Lobbying/LobbyistSearch.aspx": "Lobbyist Search",
    "/MEC/Lobbying/PrincipalSearch.aspx": "Principal Search",
    "/MEC/Lobbying/PrincipalActivity.aspx": "Principal Activity Reports",
    "/MEC/Lobbying/LobbyistActivity.aspx": "Lobbyist Activity Reports",
    "/MEC/Lobbying/LobPrinReportData.aspx": "Lobbyist Principal Report Data",
    "/MEC/Lobbying/LobExpSearch.aspx": "Lobbyist Expenditure Search",
    "/MEC/Lobbying/BusinessRelationshipActivity.aspx": "Business Relationship Activity",
    "/MEC/Lobbying/Lob_SearchLob.aspx": "Lobbyist Name Search",
    "/MEC/Lobbying/Lob_SearchPrin.aspx": "Principal Name Search",
    "/MEC/Lobbying/LB14_PubOff.aspx": "Public Official Report Search",
    "/MEC/Lobbying/LB14_PrinExpSrch.aspx": "Principal Expenditure Search",
    "/MEC/Lobbying/Lob_ExpSrch.aspx": "Lobbyist Expenditure Report Search",
    "/MEC/Commission_Business/Compliance_CASearch.aspx": "Commission Actions Search",
    "/MEC/Commission_Business/OpinionsSearch.aspx": "Advisory Opinions Search",
    "/MEC/Commission_Business/Sunshine.aspx": "Sunshine Request",
    "/MEC/Commission_Business/CommMeetings.aspx": "Commission Meetings",
    "/MEC/PFD/OSTSearches.aspx": "Higher Ed Out-of-State Travel Report Search",
}

KEEP_PATTERN = re.compile(
    r"campaign|committee|contribution|expenditure|ballot|candidate|lobby|principal|legislative|"
    r"commission|case|action|opinion|advisory|complaint|sunshine|financial disclosure|pfd|"
    r"conflict of interest|ethics|nepotism|personal financial|annual report|training|webinar|"
    r"tutorial|resource|search|form|filing|deadline|calendar|llc|chapter|csr|statute|rule|pdf|"
    r"report|registration|register|paid for by|statement of limited activity",
    re.I,
)
SKIP_PATTERN = re.compile(
    r"^(skip|home$|contact|accessibility|privacy|employment|facebook|x - formerly twitter|twitter|youtube|search$|governor|mo\.gov|find an agency|online services|internet explorer|google chrome|mozilla firefox)$",
    re.I,
)

GENERIC_QUERY_TOKENS = {
    "ABOUT",
    "AND",
    "ARE",
    "CAN",
    "CONNECTED",
    "DATA",
    "ETHICS",
    "FOR",
    "GIVE",
    "INDEX",
    "INDEXED",
    "LINK",
    "LINKS",
    "MEC",
    "ME",
    "MISSOURI",
    "PUBLIC",
    "RECORD",
    "RECORDS",
    "REPORT",
    "REPORTS",
    "RESOURCE",
    "RESOURCES",
    "SEARCH",
    "SHOW",
    "SOURCE",
    "SOURCES",
    "THE",
    "WHAT",
    "WHERE",
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
    cleaned = re.sub(r"[^A-Z0-9/$.-]+", " ", clean_text(value).upper())
    return re.sub(r"\s+", " ", cleaned).strip()


def query_tokens(value: Any) -> set[str]:
    return {
        token.strip("$.,")
        for token in normalize_text(value).replace("/", " ").replace("-", " ").split()
        if len(token.strip("$,")) > 2 and token.strip("$.,") not in GENERIC_QUERY_TOKENS
    }


def label_override(url: str) -> str | None:
    path = urlparse(url).path
    for suffix, label in URL_LABEL_OVERRIDES.items():
        if path.endswith(suffix):
            return label
    if "/AnnualReport/" in url:
        year = url.rstrip("/").split("/")[-1]
        if year.isdigit():
            return f"MEC Annual Report {year}"
    return None


def normalized_label(raw_label: str, url: str) -> str:
    override = label_override(url)
    cleaned = clean_text(raw_label)
    if override and (not cleaned or normalize_text(cleaned) in {"", "SEARCH", "FORM", "FORMS"}):
        return override
    if cleaned and not normalize_text(cleaned):
        return ""
    return cleaned or override or ""


def year_label(label: str, url: str) -> str | None:
    matches = YEAR_PATTERN.findall(f"{label} {url}")
    return matches[-1] if matches else None


def resource_type(url: str, label: str) -> str:
    lowered = f"{url} {label}".lower()
    path = urlparse(url).path.lower()
    if "/annualreport/" in lowered:
        return "annual_report"
    if path.endswith(".pdf"):
        if "fillable" in lowered or "form" in lowered:
            return "form_pdf"
        return "pdf"
    if "/mec/campaign_finance/cf" in lowered or any(
        term in lowered for term in ["search", "casearch", "opinionssearch", "ostsearches", "activity", "reportdata"]
    ):
        return "search_page"
    if any(term in lowered for term in ["registration", "register", "filer", "e-filer", "co.aspx", "attestation"]):
        return "filing_page"
    if any(term in lowered for term in ["chapter=105", "chapter=130", "csr", "statute", "rule"]):
        return "law_link"
    if any(term in lowered for term in ["training", "webinar", "tutorial"]):
        return "training_resource"
    if "mec.mo.gov" in urlparse(url).netloc:
        return "mec_page"
    return "external_page"


def infer_topic(page: MecPage, label: str, url: str) -> str:
    lowered = f"{page.default_topic} {label} {url}".lower()
    if "/annualreport/" in lowered or "annual report" in lowered:
        return "annual reports"
    if "lobby" in lowered or "principal" in lowered or "legislative action" in lowered:
        return "lobbying"
    if "financial disclosure" in lowered or "personal financial" in lowered or "/pfd/" in lowered or "pfd" in lowered:
        return "financial disclosure/PFD"
    if "advisory opinion" in lowered or "opinionssearch" in lowered:
        return "advisory opinions"
    if "commission action" in lowered or "commission case" in lowered or "compliance_casearch" in lowered:
        return "commission actions/cases"
    if "complaint" in lowered or "enforcement" in lowered:
        return "complaints/enforcement"
    if "conflict of interest" in lowered or "nepotism" in lowered:
        return "conflict of interest"
    if "training" in lowered or "webinar" in lowered or "tutorial" in lowered or "educational_resources" in lowered:
        return "training/resources"
    if "chapter=105" in lowered or "chapter=130" in lowered or "csr" in lowered or "statute" in lowered or "rule" in lowered:
        return "law/rules"
    if "campaign" in lowered or "committee" in lowered or "contribution" in lowered or "expenditure" in lowered or "ballot" in lowered or "llc" in lowered:
        if "search" in lowered or "cf_" in lowered or "cf12" in lowered or "cf14" in lowered:
            return "campaign finance searches"
        if "form" in lowered or ".pdf" in lowered or "packet" in lowered:
            return "campaign finance forms"
        return "campaign finance"
    if "candidate central" in lowered or "candidate" in lowered:
        return "candidate resources"
    if "sunshine" in lowered or "meeting" in lowered or "commission business" in lowered:
        return "commission business"
    return page.default_topic


def is_relevant_link(label: str, absolute_url: str) -> bool:
    if not label or SKIP_PATTERN.search(label):
        return False
    if absolute_url.startswith(("mailto:", "tel:", "javascript:")):
        return False
    parsed = urlparse(absolute_url)
    if parsed.scheme not in {"http", "https"}:
        return False
    return bool(KEEP_PATTERN.search(f"{label} {absolute_url}"))


def parse_page_links(page: MecPage, page_text: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for href, raw_label in ANCHOR_PATTERN.findall(page_text):
        absolute = urljoin(page.url, html.unescape(href)).split("#", 1)[0]
        label = normalized_label(raw_label, absolute)
        if not is_relevant_link(label, absolute):
            continue
        key = (label, absolute)
        if key in seen:
            continue
        seen.add(key)
        records.append(
            {
                "resource_id": hashlib.sha1(f"{page.key}:{label}:{absolute}".encode("utf-8")).hexdigest()[:16],
                "label": label,
                "url": absolute,
                "topic": infer_topic(page, label, absolute),
                "resource_type": resource_type(absolute, label),
                "year_label": year_label(label, absolute),
                "page_key": page.key,
                "page_label": page.label,
                "source_page": page.url,
                "source_host": urlparse(absolute).netloc,
            }
        )
    return records


def top_counts(counter: Counter[str], limit: int = 12) -> list[dict[str, Any]]:
    return [
        {"label": label, "count": count}
        for label, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:limit]
        if label
    ]


def build_mec_resources_index(force: bool = False, delay_seconds: float = 0.03) -> dict[str, Any]:
    if INDEX_PATH.exists() and not force:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (compatible; MissouriPublicDataChat/1.0; +https://github.com/Stroudmj00/missouri-tiny-llm-case-study)",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        }
    )
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    records: list[dict[str, Any]] = []
    pages: list[dict[str, Any]] = []
    seen_global: set[tuple[str, str]] = set()

    for page in PAGES:
        response = session.get(page.url, timeout=60)
        response.raise_for_status()
        text = response.text
        local_page = RAW_DIR / f"{page.key}.html"
        local_page.write_text(text, encoding="utf-8")
        parsed = parse_page_links(page, text)
        deduped: list[dict[str, Any]] = []
        for record in parsed:
            dedupe_key = (record["label"], record["url"])
            if dedupe_key in seen_global:
                continue
            seen_global.add(dedupe_key)
            deduped.append(record)
        records.extend(deduped)
        pages.append(
            {
                "key": page.key,
                "label": page.label,
                "url": page.url,
                "local_file": str(local_page.relative_to(PROJECT_ROOT)),
                "bytes": len(text.encode("utf-8", errors="replace")),
                "sha256": sha256_text(text),
                "resource_count": len(deduped),
            }
        )
        if delay_seconds:
            time.sleep(delay_seconds)

    topics = Counter(record["topic"] for record in records)
    resource_types = Counter(record["resource_type"] for record in records)
    pages_counter = Counter(record["page_label"] for record in records)
    payload = {
        "generated_at_utc": utc_now(),
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "source": SOURCE_NAME,
        "index_path": str(INDEX_PATH.relative_to(PROJECT_ROOT)),
        "page_count": len(pages),
        "record_count": len(records),
        "topic_count": len(topics),
        "resource_type_counts": dict(sorted(resource_types.items())),
        "top_topics": top_counts(topics),
        "top_pages": top_counts(pages_counter),
        "pages": pages,
        "notes": [
            "This index stores Missouri Ethics Commission public-resource metadata and source links only.",
            "It does not download campaign-finance filings, lobbyist filings, complaints, or commission-action result rows.",
            "Entity-level campaign-finance, lobbying, complaint, or enforcement values still require dedicated search adapters with exact matching and careful citation context.",
        ],
        "records": records,
    }
    write_json(INDEX_PATH, payload)
    write_json(REPORT_PATH, {key: value for key, value in payload.items() if key != "records"})
    return payload


def topic_terms(question: str) -> set[str]:
    lowered = question.lower()
    terms: set[str] = set()
    if any(term in lowered for term in ["campaign", "committee", "contribution", "expenditure", "ballot", "$5,000", "5000", "llc"]):
        terms.add("campaign finance searches" if "search" in lowered or "link" in lowered else "campaign finance")
    if any(term in lowered for term in ["lobby", "lobbyist", "principal", "legislative action"]):
        terms.add("lobbying")
    if any(term in lowered for term in ["financial disclosure", "personal financial", "pfd", "out-of-state travel"]):
        terms.add("financial disclosure/PFD")
    if any(term in lowered for term in ["commission action", "commission case", "enforcement"]):
        terms.add("commission actions/cases")
    if "advisory" in lowered or "opinion" in lowered:
        terms.add("advisory opinions")
    if "complaint" in lowered:
        terms.add("complaints/enforcement")
    if any(term in lowered for term in ["training", "webinar", "tutorial"]):
        terms.add("training/resources")
    if any(term in lowered for term in ["annual report", "annual reports", "2025 report", "2024 report"]):
        terms.add("annual reports")
    if any(term in lowered for term in ["law", "rule", "statute", "chapter 105", "chapter 130", "csr"]):
        terms.add("law/rules")
    if "candidate" in lowered:
        terms.add("candidate resources")
    return terms


def resource_type_terms(question: str) -> set[str]:
    lowered = question.lower()
    terms: set[str] = set()
    if any(term in lowered for term in ["search", "searches", "lookup", "links"]):
        terms.add("search_page")
    if "report" in lowered and any(term in lowered for term in ["lobby", "campaign", "committee", "commission", "pfd"]):
        terms.add("search_page")
    if any(term in lowered for term in ["form", "forms", "packet"]):
        terms.update({"form_pdf", "pdf"})
    if "annual report" in lowered or "annual reports" in lowered:
        terms.add("annual_report")
    if any(term in lowered for term in ["training", "webinar", "tutorial"]):
        terms.add("training_resource")
    if any(term in lowered for term in ["law", "rule", "statute", "chapter", "csr"]):
        terms.add("law_link")
    return terms


def asks_for_summary(question: str) -> bool:
    lowered = question.lower()
    return any(
        term in lowered
        for term in ["indexed", "available", "coverage", "connected", "what data", "what resources", "what links", "what mec", "what reports"]
    )


class MecResourcesIndex:
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
                "category": "Ethics and campaign finance",
                "kind": "MEC public-resource metadata",
                "lookup_table": "mec_resources_index",
                "year": None,
                "year_range": None,
                "source_files": [
                    {
                        "category": page.get("key"),
                        "category_label": page.get("label"),
                        "file_name": page.get("url"),
                        "row_count": page.get("resource_count"),
                        "bytes": page.get("bytes"),
                        "sha256": page.get("sha256"),
                    }
                    for page in payload.get("pages", [])
                ],
                "source_file_count": payload.get("page_count"),
                "source_rows": payload.get("record_count"),
                "matched_rows": matched_rows,
            }
        ]

    def unavailable_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "The MEC public-resource metadata index has not been built yet. Run "
                "`python scripts/build_mec_resources_index.py --force` to index official MEC campaign-finance, lobbying, and ethics resource links."
            ),
            "retrieved_context_id": "mec_resources_index:missing",
            "retrieved_source": "mec_resources_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "The MEC route exists, but the local ignored index is missing.",
            "citations": [],
            "source_rows": [],
        }

    def summary_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        topics = "; ".join(f"{item['label']}: {item['count']}" for item in payload.get("top_topics", [])[:8])
        resource_types = "; ".join(f"{key}: {value}" for key, value in payload.get("resource_type_counts", {}).items())
        return {
            "question": question,
            "answer": (
                "The MEC public-records resource metadata layer indexes official Missouri Ethics Commission public links from "
                f"{payload.get('page_count', 0)} source page(s). It contains {payload.get('record_count', 0):,} resource link(s). "
                f"Top topics: {topics}. Resource types: {resource_types}. "
                "It can return cited links for campaign finance, Committee Contributions & Expenditures, lobbying, personal financial disclosure, commission actions, advisory opinions, forms, training, and annual reports. "
                "It does not parse individual filing result rows or draw conclusions about political-finance entities yet."
            ),
            "retrieved_context_id": "mec_resources_index:summary",
            "retrieved_source": "mec_resources_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local MEC public-resource metadata index.",
            "citations": self.citation(matched_rows=payload.get("record_count", 0)),
            "source_rows": [],
        }

    def topic_summary_answer(self, question: str, topics: set[str]) -> dict[str, Any]:
        rows = [record for record in self.records() if record.get("topic") in topics]
        if not rows:
            return self.summary_answer(question)
        topic_counts = Counter(str(row.get("topic", "")) for row in rows)
        type_counts = Counter(str(row.get("resource_type", "")) for row in rows)
        topic_text = "; ".join(f"{label}: {count}" for label, count in sorted(topic_counts.items()))
        type_text = "; ".join(f"{label}: {count}" for label, count in sorted(type_counts.items()))
        examples = "; ".join(
            f"{row['label']} ({row['resource_type']}): {row['url']}"
            for row in sorted(rows, key=lambda item: (str(item.get("topic")), str(item.get("label"))))[:6]
        )
        return {
            "question": question,
            "answer": (
                f"The MEC public-records resource metadata layer has {len(rows):,} indexed link(s) for this topic request. "
                f"Topic counts: {topic_text}. Resource types: {type_text}. Examples: {examples}. "
                "These are source links and resource metadata, not parsed filing-result values."
            ),
            "retrieved_context_id": "mec_resources_index:topic_summary",
            "retrieved_source": "mec_resources_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local MEC public-resource metadata index.",
            "citations": self.citation(matched_rows=len(rows)),
            "source_rows": [],
        }

    def rows_for_question(self, question: str) -> list[dict[str, Any]]:
        records = self.records()
        wanted_topics = topic_terms(question)
        if wanted_topics:
            topic_filtered = [record for record in records if record.get("topic") in wanted_topics]
            if topic_filtered:
                records = topic_filtered
        wanted_types = resource_type_terms(question)
        if wanted_types:
            type_filtered = [record for record in records if record.get("resource_type") in wanted_types]
            if type_filtered:
                records = type_filtered
        wanted_years = {year for year in re.findall(r"\b(?:20\d{2}|19\d{2})\b", question)}
        if wanted_years:
            year_filtered = [
                record
                for record in records
                if record.get("year_label") in wanted_years or any(year in str(record.get("label", "")) for year in wanted_years)
            ]
            if year_filtered:
                records = year_filtered

        q_tokens = query_tokens(question)
        if q_tokens:
            scored: list[tuple[int, dict[str, Any]]] = []
            question_norm = normalize_text(question)
            for record in records:
                blob = " ".join(str(record.get(key, "")) for key in ["label", "topic", "page_label", "resource_type", "year_label"])
                tokens = query_tokens(blob)
                score = len(q_tokens & tokens)
                label_norm = normalize_text(record.get("label", ""))
                url_lowered = str(record.get("url", "")).lower()
                if label_norm and label_norm in question_norm:
                    score += 25
                if "CONTRIBUTIONS" in question_norm and "EXPENDITURES" in question_norm and "contr" in url_lowered:
                    score += 12
                if "5000" in question_norm and "lrgcontr" in url_lowered:
                    score += 12
                if "LOBBY" in question_norm and "lobbying" in url_lowered:
                    score += 8
                if "ANNUAL" in question_norm and record.get("resource_type") == "annual_report":
                    score += 8
                if "SEARCH" in question_norm and record.get("resource_type") == "search_page":
                    score += 6
                if score:
                    scored.append((score, record))
            if scored:
                ranked = sorted(scored, key=lambda item: (-item[0], item[1]["label"], item[1]["url"]))
                best = ranked[0][0]
                records = [record for score, record in ranked if score >= max(1, best - 2)]
        return records

    def rows_answer(self, question: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
        if not rows:
            return self.missing_answer(question)
        matched_count = len(rows)
        preview = rows[:12]
        source_preview = rows[:5]
        rendered = "; ".join(
            f"{row['label']} ({row['topic']}, {row['resource_type']}): {row['url']}"
            for row in preview
        )
        return {
            "question": question,
            "answer": f"Showing {len(preview)} of {matched_count} matching MEC public-records resource metadata row(s): {rendered}.",
            "retrieved_context_id": "mec_resources_index:match",
            "retrieved_source": "mec_resources_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local MEC public-resource metadata index.",
            "citations": self.citation(matched_rows=matched_count),
            "source_rows": [{"source_file": row["source_page"], "values": row} for row in source_preview],
        }

    def missing_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "I have indexed MEC public-resource metadata, but this question did not match a supported topic, resource label, or year. "
                "Try `What MEC resources are indexed?`, `Give me the MEC campaign finance search links`, "
                "`Where are MEC lobbying reports?`, or `Give me the MEC annual report for 2025`."
            ),
            "retrieved_context_id": "mec_resources_index:no_match",
            "retrieved_source": "mec_resources_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Answered from MEC public-resource coverage metadata because no exact resource row matched.",
            "citations": self.citation(),
            "source_rows": [],
        }

    def answer(self, question: str) -> dict[str, Any] | None:
        if not self.available():
            return self.unavailable_answer(question)
        terms = topic_terms(question)
        if asks_for_summary(question) and terms:
            return self.topic_summary_answer(question, terms)
        if asks_for_summary(question) and not terms:
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
    parser.add_argument("--delay-seconds", type=float, default=0.03)
    args = parser.parse_args()
    payload = build_mec_resources_index(force=args.force, delay_seconds=args.delay_seconds)
    print(json.dumps({key: value for key, value in payload.items() if key != "records"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
