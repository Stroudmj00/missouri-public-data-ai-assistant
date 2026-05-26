"""Build and query selected Missouri DNR impaired-waters listing rows."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from pypdf import PdfReader


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw_public" / "dnr_impaired_waters"
DOCUMENT_DIR = RAW_DIR / "documents"
INDEX_PATH = RAW_DIR / "dnr_impaired_waters_index.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "dnr_impaired_waters_index_report.json"
SOURCE_NAME = "Missouri DNR 2024-2026 Proposed 303(d) Impaired Waters"
LANDING_PAGE = "https://dnr.mo.gov/water/hows-water/impaired"
DEFAULT_LIST_PDF = (
    "https://dnr.mo.gov/sites/dnr/files/vfc/2025/12/main/"
    "1%20-%202024-2026-proposed-303d-list-for-cwc-approval-20260114-wpp.pdf"
)

COUNTIES = {
    "ADAIR",
    "ANDREW",
    "ATCHISON",
    "AUDRAIN",
    "BARRY",
    "BARTON",
    "BATES",
    "BENTON",
    "BOLLINGER",
    "BOONE",
    "BUCHANAN",
    "BUTLER",
    "CALDWELL",
    "CALLAWAY",
    "CAMDEN",
    "CAPE GIRARDEAU",
    "CARROLL",
    "CARTER",
    "CASS",
    "CEDAR",
    "CHARITON",
    "CHRISTIAN",
    "CLARK",
    "CLAY",
    "CLINTON",
    "COLE",
    "COOPER",
    "CRAWFORD",
    "DADE",
    "DALLAS",
    "DAVIESS",
    "DEKALB",
    "DENT",
    "DOUGLAS",
    "DUNKLIN",
    "FRANKLIN",
    "GASCONADE",
    "GENTRY",
    "GREENE",
    "GRUNDY",
    "HARRISON",
    "HENRY",
    "HICKORY",
    "HOLT",
    "HOWARD",
    "HOWELL",
    "IRON",
    "JACKSON",
    "JASPER",
    "JEFFERSON",
    "JOHNSON",
    "KNOX",
    "LACLEDE",
    "LAFAYETTE",
    "LAWRENCE",
    "LEWIS",
    "LINCOLN",
    "LINN",
    "LIVINGSTON",
    "MCDONALD",
    "MACON",
    "MADISON",
    "MARIES",
    "MARION",
    "MERCER",
    "MILLER",
    "MISSISSIPPI",
    "MONITEAU",
    "MONROE",
    "MONTGOMERY",
    "MORGAN",
    "NEW MADRID",
    "NEWTON",
    "NODAWAY",
    "OREGON",
    "OSAGE",
    "OZARK",
    "PEMISCOT",
    "PERRY",
    "PETTIS",
    "PHELPS",
    "PIKE",
    "PLATTE",
    "POLK",
    "PULASKI",
    "PUTNAM",
    "RALLS",
    "RANDOLPH",
    "RAY",
    "REYNOLDS",
    "RIPLEY",
    "SALINE",
    "SCHUYLER",
    "SCOTLAND",
    "SCOTT",
    "SHANNON",
    "SHELBY",
    "ST. CHARLES",
    "ST. CLAIR",
    "ST. FRANCOIS",
    "ST. LOUIS",
    "ST. LOUIS CITY",
    "STE. GENEVIEVE",
    "STODDARD",
    "STONE",
    "SULLIVAN",
    "TANEY",
    "TEXAS",
    "VERNON",
    "WARREN",
    "WASHINGTON",
    "WAYNE",
    "WEBSTER",
    "WORTH",
    "WRIGHT",
}

POLLUTANTS = [
    "Aquatic Macroinvertebrate Bioassessments/ Unknown",
    "Nutrient/Eutrophication Biol. Indicators",
    "Mercury in Fish Tissue",
    "Oxygen, Dissolved",
    "Escherichia coli",
    "Chlorophyll-a",
    "Nitrogen, Total",
    "Sulfate + Chloride",
    "Ammonia, Total",
    "Cadmium",
    "Chloride",
    "Dioxin",
    "Lead",
    "Zinc",
    "pH",
]

GENERIC_QUERY_TOKENS = {
    "303D",
    "ABOUT",
    "COUNT",
    "COUNTY",
    "DATA",
    "DNR",
    "FOR",
    "HOW",
    "IMPAIRED",
    "INDEXED",
    "LIST",
    "LISTED",
    "LISTINGS",
    "MANY",
    "MISSOURI",
    "POLLUTANT",
    "POLLUTANTS",
    "TMDL",
    "WATER",
    "WATERS",
    "WHAT",
    "WHICH",
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
    text = text.replace("co li", "coli")
    text = text.replace("A tmospheric", "Atmospheric").replace("Atm ospheric", "Atmospheric")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_key(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", " ", str(value or "").upper()).strip()


def fetch_text(url: str) -> str:
    response = requests.get(url, timeout=30, headers={"User-Agent": "missouri-public-data-ai-assistant/1.0"})
    response.raise_for_status()
    return response.text


def latest_pdf_url(source_html: str) -> str:
    candidates: list[tuple[str, str]] = []
    for href, label in re.findall(r"<a\s+[^>]*href=['\"]([^'\"]+)['\"][^>]*>(.*?)</a>", source_html, flags=re.I | re.S):
        label_text = clean_text(re.sub(r"<[^>]+>", " ", label)).lower()
        full_url = urljoin(LANDING_PAGE, href)
        if "303" in label_text and "listed waters" in label_text and "2024-2026" in label_text:
            candidates.append((label_text, full_url))
    return candidates[0][1] if candidates else DEFAULT_LIST_PDF


def extract_pdf_text(pdf_bytes: bytes, max_pages: int, max_chars: int) -> tuple[str, int]:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    parts: list[str] = []
    for page in reader.pages[:max_pages]:
        if sum(len(part) for part in parts) >= max_chars:
            break
        parts.append(page.extract_text() or "")
    return "\n".join(parts)[:max_chars], len(reader.pages)


def row_chunks(text: str) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    for raw_line in text.splitlines():
        line = clean_text(raw_line)
        if not line:
            continue
        if re.match(r"^\d+\s+(?:19|20)\d{2}\s+", line):
            if current:
                chunks.append(clean_text(" ".join(current)))
            current = [line]
            continue
        if current and not line.startswith(("Row #", "Priority", "Schedule")):
            current.append(line)
    if current:
        chunks.append(clean_text(" ".join(current)))
    return chunks


def county_from_pre_huc(value: str) -> str | None:
    words = clean_text(value).split()
    for start in range(len(words) - 1, -1, -1):
        candidate = " ".join(words[start:])
        parts = candidate.upper().split("/")
        if all(part in COUNTIES for part in parts):
            return candidate
    return None


def parse_county(row_text: str) -> str | None:
    match = re.search(r"(.+?)\s+(\d{8})\b", row_text)
    if not match:
        return None
    return county_from_pre_huc(match.group(1))


def parse_pollutant(row_text: str) -> str | None:
    normalized = clean_text(row_text).lower()
    for pollutant in POLLUTANTS:
        if pollutant.lower() in normalized:
            return pollutant
    return None


def parse_priority(row_text: str) -> tuple[str | None, str | None]:
    match = re.search(r"\b([HML])\s*(20\d{2})?(?:\s+Impaired AU Size|\s*$)", row_text)
    if not match:
        return None, None
    return match.group(1), match.group(2)


def parse_row(row_text: str) -> dict[str, Any] | None:
    text = clean_text(row_text)
    match = re.match(
        r"^(?P<row_number>\d+)\s+(?P<year>\d{4})\s+(?P<auid>\S+)\s+"
        r"(?P<name>.+?)\s+(?P<wbid>\d{3,4}\.\d{2}|GEN|UL)\s+"
        r"(?P<class>P|P1|P2|C|L1|L2|L3|UL|US)\s+(?P<entire>[YN])\s+"
        r"(?P<size>\d+(?:\.\d+)?)\s+(?P<units>Miles|Acres)\s+(?P<tail>.+)$",
        text,
    )
    if not match:
        return None
    county = parse_county(text)
    priority, schedule_year = parse_priority(text)
    huc_match = re.search(r"\b(\d{8})\b", text)
    pollutant = parse_pollutant(text)
    county_parts = [part.strip() for part in (county or "").split("/") if part.strip()]
    return {
        "row_number": int(match.group("row_number")),
        "listing_year": int(match.group("year")),
        "auid": match.group("auid"),
        "assessment_unit_name": clean_text(match.group("name")),
        "assessment_unit_name_norm": normalize_key(match.group("name")),
        "wbid": match.group("wbid"),
        "water_class": match.group("class"),
        "entire_water_body_impaired": match.group("entire"),
        "au_size": float(match.group("size")),
        "units": match.group("units"),
        "pollutant": pollutant,
        "county": county,
        "county_parts": county_parts,
        "county_norms": [normalize_key(part) for part in county_parts],
        "huc8": huc_match.group(1) if huc_match else None,
        "tmdl_priority": priority,
        "tmdl_schedule_year": schedule_year,
        "raw_text": text[:900],
    }


def build_dnr_impaired_waters_index(
    force: bool = False,
    max_mb: float = 40.0,
    max_pages: int = 10,
    max_chars: int = 180_000,
) -> dict[str, Any]:
    if INDEX_PATH.exists() and REPORT_PATH.exists() and not force:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))

    start = time.perf_counter()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    DOCUMENT_DIR.mkdir(parents=True, exist_ok=True)

    try:
        source_html = fetch_text(LANDING_PAGE)
        pdf_url = latest_pdf_url(source_html)
    except requests.RequestException:
        pdf_url = DEFAULT_LIST_PDF
    response = requests.get(pdf_url, timeout=60, headers={"User-Agent": "missouri-public-data-ai-assistant/1.0"})
    response.raise_for_status()
    pdf_bytes = response.content
    downloaded_mb = round(len(pdf_bytes) / (1024 * 1024), 3)
    if downloaded_mb > max_mb:
        raise RuntimeError(f"Refusing to download {downloaded_mb} MB DNR impaired-waters PDF above {max_mb} MB cap")
    pdf_path = DOCUMENT_DIR / "dnr_2024_2026_proposed_303d_list.pdf"
    pdf_path.write_bytes(pdf_bytes)

    text, page_count = extract_pdf_text(pdf_bytes, max_pages=max_pages, max_chars=max_chars)
    records = [record for chunk in row_chunks(text) if (record := parse_row(chunk))]
    county_counts: Counter[str] = Counter()
    for record in records:
        for county in record["county_parts"]:
            county_counts[county] += 1
    pollutant_counts = Counter(record["pollutant"] for record in records if record.get("pollutant"))
    priority_counts = Counter(record["tmdl_priority"] for record in records if record.get("tmdl_priority"))

    payload = {
        "source": SOURCE_NAME,
        "source_url": LANDING_PAGE,
        "document_label": "2024-2026 Proposed Section 303(d) Listed Waters for CWC Approval",
        "document_status": "proposed_for_clean_water_commission_approval",
        "pdf_url": pdf_url,
        "local_file": str(pdf_path.relative_to(PROJECT_ROOT)),
        "generated_at_utc": utc_now(),
        "downloaded_mb": downloaded_mb,
        "bytes": len(pdf_bytes),
        "sha256": sha256_bytes(pdf_bytes),
        "page_count": page_count,
        "extracted_page_limit": max_pages,
        "record_count": len(records),
        "county_counts": dict(county_counts.most_common()),
        "pollutant_counts": dict(pollutant_counts.most_common()),
        "priority_counts": dict(priority_counts.most_common()),
        "records": records,
        "notes": [
            "This parser indexes selected rows from the public DNR 2024-2026 proposed 303(d) listed-waters PDF.",
            "It is a listing/source lookup, not a real-time water-quality, recreation, health, permit, or TMDL-advice system.",
            "The source document is labeled proposed for Clean Water Commission approval; answers preserve that status label.",
        ],
    }

    write_json(INDEX_PATH, payload)
    report = {
        "source": payload["source"],
        "source_url": payload["source_url"],
        "pdf_url": payload["pdf_url"],
        "document_label": payload["document_label"],
        "document_status": payload["document_status"],
        "generated_at_utc": payload["generated_at_utc"],
        "elapsed_seconds": round(time.perf_counter() - start, 2),
        "downloaded_mb": payload["downloaded_mb"],
        "record_count": payload["record_count"],
        "top_counties": dict(county_counts.most_common(10)),
        "top_pollutants": dict(pollutant_counts.most_common(10)),
        "priority_counts": dict(priority_counts.most_common()),
        "notes": payload["notes"],
    }
    write_json(REPORT_PATH, report)
    return payload


def contains_any(question: str, terms: list[str]) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in terms)


def question_tokens(question: str) -> set[str]:
    return {token for token in normalize_key(question).split() if token and token not in GENERIC_QUERY_TOKENS}


def requested_county(question: str) -> str | None:
    norm = normalize_key(question)
    for county in sorted(COUNTIES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(county)}\b", norm):
            return county.title().replace("Mcdonald", "McDonald").replace("Dekalb", "DeKalb")
    return None


def display_county(value: str) -> str:
    label = clean_text(value)
    if not label:
        return "selected county"
    if "county" in label.lower() or "city" in label.lower():
        return label
    return f"{label} County"


class DnrImpairedWatersIndex:
    def __init__(self, path: Path = INDEX_PATH) -> None:
        self.path = path
        self._payload: dict[str, Any] | None = None

    def exists(self) -> bool:
        return self.path.exists()

    def payload(self) -> dict[str, Any]:
        if self._payload is None:
            if not self.path.exists():
                return {}
            self._payload = json.loads(self.path.read_text(encoding="utf-8"))
        return self._payload

    def records(self) -> list[dict[str, Any]]:
        return self.payload().get("records", [])

    def citation(self, matched_rows: int = 0) -> list[dict[str, Any]]:
        payload = self.payload()
        source_files = [
            {
                "category": "dnr_impaired_waters",
                "category_label": payload.get("document_label", "DNR impaired waters list"),
                "file_name": payload.get("pdf_url", DEFAULT_LIST_PDF),
                "source_url": payload.get("pdf_url", DEFAULT_LIST_PDF),
                "row_count": payload.get("record_count"),
                "bytes": payload.get("bytes"),
                "sha256": payload.get("sha256"),
            },
            {
                "category": "dnr_impaired_waters",
                "category_label": "DNR Impaired Waters page",
                "file_name": payload.get("source_url", LANDING_PAGE),
                "source_url": payload.get("source_url", LANDING_PAGE),
                "row_count": None,
                "bytes": None,
                "sha256": None,
            },
        ]
        return [
            {
                "dataset": payload.get("source", SOURCE_NAME),
                "category": "Environment",
                "kind": "DNR 303(d) impaired-waters rows",
                "lookup_table": "dnr_impaired_waters_index",
                "year": 2026,
                "year_range": "2024-2026 proposed",
                "source_files": source_files,
                "source_file_count": len(source_files),
                "source_rows": payload.get("record_count"),
                "matched_rows": matched_rows,
            }
        ]

    def unavailable_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "The selected DNR impaired-waters index has not been built yet. Run "
                "`python scripts/build_dnr_impaired_waters_index.py --force` to enable 303(d) listing lookup."
            ),
            "retrieved_context_id": "dnr_impaired_waters_index:missing",
            "retrieved_source": "dnr_impaired_waters_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "The DNR impaired-waters route exists, but the local ignored index is missing.",
            "citations": [],
            "source_rows": [],
        }

    def source_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "source_file": self.payload().get("pdf_url", DEFAULT_LIST_PDF),
                "source_row_number": row.get("row_number"),
                "values": {
                    "assessment_unit_name": row.get("assessment_unit_name"),
                    "county": row.get("county"),
                    "pollutant": row.get("pollutant"),
                    "listing_year": row.get("listing_year"),
                    "tmdl_priority": row.get("tmdl_priority"),
                    "tmdl_schedule_year": row.get("tmdl_schedule_year"),
                    "au_size": row.get("au_size"),
                    "units": row.get("units"),
                },
            }
            for row in rows[:5]
        ]

    def summary_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        sorted_counties = sorted(payload.get("county_counts", {}).items(), key=lambda item: item[1], reverse=True)
        sorted_pollutants = sorted(payload.get("pollutant_counts", {}).items(), key=lambda item: item[1], reverse=True)
        top_counties = "; ".join(f"{county}: {count}" for county, count in sorted_counties[:5])
        top_pollutants = "; ".join(
            f"{pollutant}: {count}" for pollutant, count in sorted_pollutants[:5]
        )
        priority_counts = "; ".join(
            f"{priority}: {count}" for priority, count in payload.get("priority_counts", {}).items()
        )
        return {
            "question": question,
            "answer": (
                f"The selected DNR impaired-waters layer indexes {payload.get('record_count', 0):,} row(s) from the "
                f"{payload.get('document_label')} PDF. Document status: {payload.get('document_status')}. "
                f"Top indexed counties: {top_counties}. Top indexed pollutants: {top_pollutants}. "
                f"Parsed TMDL priority counts: {priority_counts}."
            ),
            "retrieved_context_id": "dnr_impaired_waters_index:summary",
            "retrieved_source": "dnr_impaired_waters_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from capped local extraction of the official DNR impaired-waters PDF.",
            "citations": self.citation(matched_rows=payload.get("record_count", 0)),
            "source_rows": [],
        }

    def county_answer(self, question: str, county: str) -> dict[str, Any]:
        county_norm = normalize_key(county)
        rows = [row for row in self.records() if county_norm in row.get("county_norms", [])]
        pollutant_counts = Counter(row["pollutant"] for row in rows if row.get("pollutant"))
        examples = "; ".join(
            f"{row.get('assessment_unit_name')} ({row.get('pollutant')}, priority {row.get('tmdl_priority') or 'not parsed'})"
            for row in rows[:5]
        )
        pollutants = "; ".join(f"{key}: {value}" for key, value in pollutant_counts.most_common(6))
        return {
            "question": question,
            "answer": (
                f"The selected DNR 2024-2026 proposed 303(d) list has {len(rows):,} indexed impaired-water listing row(s) "
                f"touching {display_county(county)}. Top pollutants in those rows: {pollutants}. Example rows: {examples}."
            ),
            "retrieved_context_id": f"dnr_impaired_waters_index:county:{county_norm}",
            "retrieved_source": "dnr_impaired_waters_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "County counts are computed from parsed county labels in the selected DNR impaired-waters PDF.",
            "citations": self.citation(matched_rows=len(rows)),
            "source_rows": self.source_rows(rows),
        }

    def high_priority_answer(self, question: str) -> dict[str, Any]:
        rows = [row for row in self.records() if row.get("tmdl_priority") == "H"]
        examples = "; ".join(
            f"{row.get('assessment_unit_name')} in {row.get('county')} ({row.get('pollutant')}, schedule {row.get('tmdl_schedule_year') or 'not parsed'})"
            for row in rows[:5]
        )
        return {
            "question": question,
            "answer": (
                f"The selected DNR impaired-waters parser found {len(rows):,} high-priority TMDL row(s). "
                f"Examples: {examples}."
            ),
            "retrieved_context_id": "dnr_impaired_waters_index:tmdl_priority:H",
            "retrieved_source": "dnr_impaired_waters_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "High-priority rows are parsed from the TMDL priority fields in the selected DNR PDF.",
            "citations": self.citation(matched_rows=len(rows)),
            "source_rows": self.source_rows(rows),
        }

    def waterbody_answer(self, question: str) -> dict[str, Any] | None:
        tokens = question_tokens(question)
        candidates: list[dict[str, Any]] = []
        question_norm = normalize_key(question)
        for row in self.records():
            name_norm = row.get("assessment_unit_name_norm", "")
            name_tokens = set(name_norm.split())
            if name_norm and name_norm in question_norm:
                candidates.append(row)
            elif len(name_tokens & tokens) >= min(2, len(name_tokens)) and name_tokens & tokens:
                candidates.append(row)
        if not candidates:
            return None
        candidates.sort(key=lambda row: (row.get("assessment_unit_name_norm", ""), row.get("row_number", 0)))
        name = candidates[0].get("assessment_unit_name")
        rendered = "; ".join(
            f"{row.get('assessment_unit_name')} / {row.get('county')} / {row.get('pollutant')} / priority {row.get('tmdl_priority') or 'not parsed'}"
            for row in candidates[:5]
        )
        return {
            "question": question,
            "answer": (
                f"I found {len(candidates):,} selected DNR 303(d) impaired-water listing row(s) matching {name}: {rendered}."
            ),
            "retrieved_context_id": f"dnr_impaired_waters_index:waterbody:{normalize_key(name)}",
            "retrieved_source": "dnr_impaired_waters_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Waterbody matching uses parsed assessment-unit names from the selected DNR impaired-waters PDF.",
            "citations": self.citation(matched_rows=len(candidates)),
            "source_rows": self.source_rows(candidates),
        }

    def advice_guardrail(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "I can summarize indexed DNR impaired-waters listing rows, but I cannot say whether water is safe for "
                "swimming, fishing, drinking, or recreation today. Ask for a listed waterbody, county count, pollutant, "
                "or TMDL-priority row from the selected 303(d) source."
            ),
            "retrieved_context_id": "dnr_impaired_waters_index:advice_guardrail",
            "retrieved_source": "dnr_impaired_waters_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "unsupported_scope_guardrail",
            "source_note": "The DNR impaired-waters layer is not real-time water-quality or safety advice.",
            "citations": self.citation(),
            "source_rows": [],
        }

    def answer(self, question: str) -> dict[str, Any] | None:
        if not self.exists():
            return self.unavailable_answer(question)
        lowered = question.lower()
        if contains_any(lowered, ["safe to swim", "safe for swimming", "safe to drink", "can i swim", "can i fish"]):
            return self.advice_guardrail(question)
        if contains_any(lowered, ["what data", "indexed", "parsed", "summary", "coverage"]):
            return self.summary_answer(question)
        if "high priority" in lowered or "high-priority" in lowered:
            return self.high_priority_answer(question)
        county = requested_county(question)
        if county:
            return self.county_answer(question, county)
        waterbody = self.waterbody_answer(question)
        if waterbody is not None:
            return waterbody
        return self.summary_answer(question)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build selected Missouri DNR impaired-waters index")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--max-mb", type=float, default=40.0)
    parser.add_argument("--max-pages", type=int, default=10)
    parser.add_argument("--max-chars", type=int, default=180_000)
    args = parser.parse_args()
    payload = build_dnr_impaired_waters_index(
        force=args.force,
        max_mb=args.max_mb,
        max_pages=args.max_pages,
        max_chars=args.max_chars,
    )
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
