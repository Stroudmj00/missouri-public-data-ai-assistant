"""Build and query selected Missouri Secretary of State election returns."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from pypdf import PdfReader


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw_public" / "sos_elections"
INDEX_PATH = RAW_DIR / "sos_elections_index.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "sos_elections_index_report.json"
SOS_RESULTS_PAGE = "https://www.sos.mo.gov/elections/s_default/results"
SOS_ELECTIONS_PAGE = "https://www.sos.mo.gov/elections/s_default"
PARTIES = (
    "Republican",
    "Democratic",
    "Libertarian",
    "Constitution",
    "Nonpartisan",
    "Non-Partisan",
    "Better",
    "Green",
    "Write-in",
)
GENERIC_QUESTION_TOKENS = {
    "a",
    "about",
    "and",
    "ballot",
    "candidate",
    "candidates",
    "cast",
    "data",
    "did",
    "election",
    "for",
    "general",
    "get",
    "got",
    "how",
    "in",
    "indexed",
    "is",
    "many",
    "missouri",
    "mo",
    "of",
    "primary",
    "receive",
    "received",
    "results",
    "return",
    "returns",
    "sos",
    "state",
    "the",
    "total",
    "vote",
    "votes",
    "was",
    "were",
    "what",
    "which",
    "who",
    "win",
    "winner",
    "won",
}


@dataclass(frozen=True)
class ElectionPdfSpec:
    key: str
    label: str
    election_type: str
    year: int
    election_date: str
    url: str

    @property
    def file_name(self) -> str:
        return self.url.rsplit("/", 1)[-1]


ELECTION_PDFS: tuple[ElectionPdfSpec, ...] = (
    ElectionPdfSpec(
        key="2024_general",
        label="2024 General Election",
        election_type="general",
        year=2024,
        election_date="2024-11-05",
        url="https://www.sos.mo.gov/CMSImages/ElectionResultsStatistics/2024GeneralElection.pdf",
    ),
    ElectionPdfSpec(
        key="2024_primary",
        label="2024 Primary Election",
        election_type="primary",
        year=2024,
        election_date="2024-08-06",
        url="https://www.sos.mo.gov/CMSImages/ElectionResultsStatistics/2024PrimaryElection.pdf",
    ),
    ElectionPdfSpec(
        key="2022_general",
        label="2022 General Election",
        election_type="general",
        year=2022,
        election_date="2022-11-08",
        url="https://www.sos.mo.gov/CMSImages/ElectionResultsStatistics/2022GeneralElection.pdf",
    ),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_text(value: Any) -> str:
    text = clean_text(value).lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_key(value: Any) -> str:
    return normalize_text(value).replace(" ", "_")


def token_set(value: Any) -> set[str]:
    return {token for token in normalize_text(value).split() if token and token not in GENERIC_QUESTION_TOKENS}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pdf_is_valid(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 4 and path.read_bytes()[:4] == b"%PDF"


def download_with_powershell(url: str, path: Path) -> None:
    executable = shutil.which("pwsh") or shutil.which("powershell")
    if executable is None:
        raise RuntimeError("PowerShell is not available for SOS PDF fallback download")
    command = (
        "$ProgressPreference='SilentlyContinue'; "
        "Invoke-WebRequest -UseBasicParsing -Uri $args[0] -OutFile $args[1] -TimeoutSec 90"
    )
    subprocess.run([executable, "-NoProfile", "-Command", command, url, str(path)], check=True)


def download_pdf(session: requests.Session, spec: ElectionPdfSpec, force: bool = False) -> Path:
    path = RAW_DIR / spec.file_name
    if pdf_is_valid(path) and not force:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        response = session.get(spec.url, timeout=90)
        if response.status_code == 200 and response.content[:4] == b"%PDF":
            path.write_bytes(response.content)
        else:
            download_with_powershell(spec.url, path)
    except Exception:
        download_with_powershell(spec.url, path)
    if not pdf_is_valid(path):
        raise RuntimeError(f"Downloaded SOS election file is not a PDF: {spec.url}")
    return path


def split_party(body: str) -> tuple[str, str]:
    for party in sorted(PARTIES, key=len, reverse=True):
        prefix = f"{party} "
        suffix = f" {party}"
        if body.startswith(prefix):
            return body[len(prefix) :].strip(), party
        if body.endswith(suffix):
            return body[: -len(suffix)].strip(), party
    return body.strip(), ""


def parse_election_pdf(path: Path, spec: ElectionPdfSpec) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    reader = PdfReader(str(path))
    header_re = re.compile(r"^(?P<office>.+?)\s+\((?P<reported>\d+)\s+of\s+(?P<total>\d+)\s+Precincts Reported\)$")
    row_re = re.compile(r"^(?P<body>.+?)\s+(?P<votes>[\d,]+)\s+(?P<pct>\d+(?:\.\d+)?)%$")
    contests: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        for raw_line in text.splitlines():
            line = clean_text(raw_line)
            if not line:
                continue
            header = header_re.match(line)
            if header:
                office = clean_text(header.group("office"))
                contest_id = f"{spec.key}:{normalize_key(office)}"
                current = {
                    "contest_id": contest_id,
                    "election_key": spec.key,
                    "election_label": spec.label,
                    "election_type": spec.election_type,
                    "year": spec.year,
                    "election_date": spec.election_date,
                    "office": office,
                    "office_norm": normalize_text(office),
                    "precincts_reported": int(header.group("reported")),
                    "precincts_total": int(header.group("total")),
                    "total_votes": None,
                    "source_url": spec.url,
                    "source_file": spec.file_name,
                    "source_page": page_number,
                }
                contests.append(current)
                continue
            if current is None:
                continue
            if line.startswith("Total Votes"):
                vote_match = re.search(r"([\d,]+)", line)
                if vote_match:
                    current["total_votes"] = int(vote_match.group(1).replace(",", ""))
                continue
            if line.startswith("Party Total"):
                continue
            row = row_re.match(line)
            if not row:
                continue
            body = clean_text(row.group("body"))
            candidate_name, party = split_party(body)
            if not candidate_name or candidate_name.lower().startswith("office/candidate"):
                continue
            candidate = {
                "record_type": "candidate_result",
                "contest_id": current["contest_id"],
                "election_key": spec.key,
                "election_label": spec.label,
                "election_type": spec.election_type,
                "year": spec.year,
                "election_date": spec.election_date,
                "office": current["office"],
                "office_norm": current["office_norm"],
                "candidate": candidate_name,
                "candidate_norm": normalize_text(candidate_name),
                "party": party,
                "votes": int(row.group("votes").replace(",", "")),
                "percent": float(row.group("pct")),
                "source_url": spec.url,
                "source_file": spec.file_name,
                "source_page": page_number,
            }
            candidates.append(candidate)

    return contests, candidates, len(reader.pages)


def build_sos_elections_index(force: bool = False) -> dict[str, Any]:
    if INDEX_PATH.exists() and not force:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (compatible; MissouriPublicDataChat/1.0; +https://github.com/Stroudmj00/missouri-tiny-llm-case-study)",
            "Accept": "application/pdf,*/*;q=0.8",
        }
    )
    start = time.perf_counter()
    contests: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    source_files: list[dict[str, Any]] = []
    for spec in ELECTION_PDFS:
        path = download_pdf(session, spec, force=force)
        parsed_contests, parsed_candidates, pages = parse_election_pdf(path, spec)
        contests.extend(parsed_contests)
        candidates.extend(parsed_candidates)
        source_files.append(
            {
                "key": spec.key,
                "label": spec.label,
                "election_type": spec.election_type,
                "year": spec.year,
                "election_date": spec.election_date,
                "url": spec.url,
                "file_name": spec.file_name,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "pages": pages,
                "contest_count": len(parsed_contests),
                "candidate_row_count": len(parsed_candidates),
            }
        )

    year_counts = Counter(str(row["year"]) for row in candidates)
    office_counts = Counter(row["office"] for row in candidates)
    payload = {
        "generated_at_utc": utc_now(),
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "source": "Missouri Secretary of State official election returns",
        "source_url": SOS_RESULTS_PAGE,
        "landing_page": SOS_ELECTIONS_PAGE,
        "index_path": str(INDEX_PATH.relative_to(PROJECT_ROOT)),
        "source_file_count": len(source_files),
        "source_files": source_files,
        "bytes": sum(item["bytes"] for item in source_files),
        "contest_count": len(contests),
        "candidate_row_count": len(candidates),
        "year_counts": dict(sorted(year_counts.items(), reverse=True)),
        "top_offices_by_row_count": dict(office_counts.most_common(12)),
        "sanitization_note": (
            "This index stores statewide official election-return contest and candidate result rows from selected SOS PDFs. "
            "It does not include voter files, precinct-level files, or county result tables."
        ),
        "contests": contests,
        "candidate_records": candidates,
    }
    write_json(INDEX_PATH, payload)
    write_json(
        REPORT_PATH,
        {
            "generated_at_utc": payload["generated_at_utc"],
            "elapsed_seconds": payload["elapsed_seconds"],
            "source": payload["source"],
            "source_url": payload["source_url"],
            "landing_page": payload["landing_page"],
            "index_path": payload["index_path"],
            "source_file_count": payload["source_file_count"],
            "source_files": payload["source_files"],
            "bytes": payload["bytes"],
            "contest_count": payload["contest_count"],
            "candidate_row_count": payload["candidate_row_count"],
            "year_counts": payload["year_counts"],
            "top_offices_by_row_count": payload["top_offices_by_row_count"],
            "sample_contests": contests[:10],
            "sample_candidate_records": candidates[:10],
            "sanitization_note": payload["sanitization_note"],
        },
    )
    return payload


def requested_years(question: str) -> list[int]:
    return sorted({int(match) for match in re.findall(r"\b(20\d{2}|19\d{2})\b", question)})


def requested_election_type(question: str) -> str | None:
    lowered = question.lower()
    if "primary" in lowered:
        return "primary"
    if "general" in lowered:
        return "general"
    return None


def requested_party(question: str) -> str | None:
    lowered = question.lower()
    for party in PARTIES:
        if party.lower().replace("-", " ") in lowered.replace("-", " "):
            return party
    return None


def office_alias(question: str) -> str | None:
    lowered = question.lower()
    if "lieutenant governor" in lowered:
        return "Lieutenant Governor"
    if "secretary of state" in lowered:
        return "Secretary of State"
    if "attorney general" in lowered:
        return "Attorney General"
    if "state treasurer" in lowered or "treasurer" in lowered:
        return "State Treasurer"
    if "president" in lowered:
        return "U.S. President and Vice President"
    if "u.s. senator" in lowered or "us senator" in lowered or "u. s. senator" in lowered:
        return "U.S. Senator"
    if "senate" in lowered and "state" not in lowered:
        return "U.S. Senator"
    if "governor" in lowered:
        return "Governor"
    return None


def contest_filter(records: list[dict[str, Any]], question: str) -> list[dict[str, Any]]:
    years = requested_years(question)
    election_type = requested_election_type(question)
    office = office_alias(question)
    rows = records
    if years:
        rows = [row for row in rows if row.get("year") in years]
    if election_type:
        rows = [row for row in rows if row.get("election_type") == election_type]
    if office:
        office_norm = normalize_text(office)
        rows = [row for row in rows if row.get("office_norm") == office_norm]
    return rows


def candidate_score(row: dict[str, Any], question_tokens: set[str]) -> int:
    candidate_tokens = token_set(row.get("candidate", ""))
    return len(candidate_tokens & question_tokens)


class SosElectionsIndex:
    def __init__(self, path: Path = INDEX_PATH) -> None:
        self.path = path
        self._payload: dict[str, Any] | None = None

    def available(self) -> bool:
        return self.path.exists() and self.path.stat().st_size > 0

    def payload(self) -> dict[str, Any]:
        if self._payload is None:
            self._payload = json.loads(self.path.read_text(encoding="utf-8")) if self.available() else {}
        return self._payload

    def contests(self) -> list[dict[str, Any]]:
        return list(self.payload().get("contests", []))

    def candidate_records(self) -> list[dict[str, Any]]:
        return list(self.payload().get("candidate_records", []))

    def citation(self, matched_rows: int = 0, source_url: str | None = None) -> list[dict[str, Any]]:
        payload = self.payload()
        source_files = []
        for source in payload.get("source_files", []):
            if source_url and source.get("url") != source_url:
                continue
            source_files.append(
                {
                    "category": "sos_elections",
                    "category_label": source.get("label", "SOS election returns"),
                    "file_name": source.get("url"),
                    "row_count": source.get("candidate_row_count"),
                    "bytes": source.get("bytes"),
                    "sha256": source.get("sha256"),
                }
            )
        if not source_files:
            source_files = [
                {
                    "category": "sos_elections",
                    "category_label": "Missouri Secretary of State election results",
                    "file_name": payload.get("source_url", SOS_RESULTS_PAGE),
                    "row_count": payload.get("candidate_row_count"),
                    "bytes": payload.get("bytes"),
                    "sha256": None,
                }
            ]
        return [
            {
                "dataset": payload.get("source", "Missouri Secretary of State official election returns"),
                "category": "Elections",
                "kind": "official election-return rows",
                "lookup_table": "sos_elections_index",
                "year": None,
                "year_range": ", ".join(sorted(payload.get("year_counts", {}).keys())),
                "source_files": source_files,
                "source_file_count": len(source_files),
                "source_rows": payload.get("candidate_row_count"),
                "matched_rows": matched_rows,
            }
        ]

    def unavailable_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "The SOS election-return index has not been built yet. Run "
                "`python scripts/build_sos_elections_index.py --force` to download selected official election-return PDFs "
                "and build exact winner/vote lookups."
            ),
            "retrieved_context_id": "sos_elections_index:missing",
            "retrieved_source": "sos_elections_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "The SOS election route exists, but the local ignored index is missing.",
            "citations": [],
            "source_rows": [],
        }

    def summary_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        file_labels = "; ".join(item["label"] for item in payload.get("source_files", []))
        return {
            "question": question,
            "answer": (
                "The SOS election exact lookup layer indexes selected Missouri Secretary of State official election-return PDFs. "
                f"It currently covers {payload.get('source_file_count', 0)} official election-return PDF(s): {file_labels}. "
                f"The parser extracted {payload.get('contest_count', 0):,} contests and "
                f"{payload.get('candidate_row_count', 0):,} candidate/ballot result row(s). It can answer selected statewide "
                "winner, candidate vote, percentage, total-vote, and primary party-winner questions. "
                "It does not include voter files, precinct-level files, or county result tables."
            ),
            "retrieved_context_id": "sos_elections_index:summary",
            "retrieved_source": "sos_elections_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": payload.get("sanitization_note"),
            "citations": self.citation(matched_rows=payload.get("candidate_row_count", 0)),
            "source_rows": [],
        }

    def winner_answer(self, question: str) -> dict[str, Any] | None:
        rows = contest_filter(self.candidate_records(), question)
        if not rows:
            return None
        party = requested_party(question)
        if party:
            rows = [row for row in rows if row.get("party") == party]
        if not rows:
            return None
        winner = max(rows, key=lambda row: int(row["votes"]))
        scope = f"{party} " if party else ""
        return {
            "question": question,
            "answer": (
                f"In the indexed {winner['election_label']} official returns, {winner['candidate']} won the "
                f"{scope}{winner['office']} contest with {winner['votes']:,} votes ({winner['percent']:.1f}%)."
            ),
            "retrieved_context_id": f"sos_elections_index:winner:{winner['contest_id']}:{normalize_key(party or 'all')}",
            "retrieved_source": "sos_elections_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": self.payload().get("sanitization_note"),
            "citations": self.citation(matched_rows=len(rows), source_url=winner.get("source_url")),
            "source_rows": [{"source_file": winner["source_file"], "values": winner}],
        }

    def total_votes_answer(self, question: str) -> dict[str, Any] | None:
        rows = contest_filter(self.contests(), question)
        rows = [row for row in rows if row.get("total_votes") is not None]
        if not rows:
            return None
        row = rows[0]
        return {
            "question": question,
            "answer": (
                f"The indexed {row['election_label']} official returns list {row['total_votes']:,} total votes "
                f"for {row['office']}."
            ),
            "retrieved_context_id": f"sos_elections_index:total_votes:{row['contest_id']}",
            "retrieved_source": "sos_elections_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": self.payload().get("sanitization_note"),
            "citations": self.citation(matched_rows=1, source_url=row.get("source_url")),
            "source_rows": [{"source_file": row["source_file"], "values": row}],
        }

    def candidate_answer(self, question: str) -> dict[str, Any] | None:
        rows = contest_filter(self.candidate_records(), question)
        question_tokens = token_set(question)
        scored = [(candidate_score(row, question_tokens), row) for row in rows]
        scored = [item for item in scored if item[0] > 0]
        if not scored:
            return None
        scored.sort(key=lambda item: (item[0], item[1]["votes"]), reverse=True)
        row = scored[0][1]
        return {
            "question": question,
            "answer": (
                f"In the indexed {row['election_label']} official returns, {row['candidate']} received "
                f"{row['votes']:,} votes ({row['percent']:.1f}%) for {row['office']}."
            ),
            "retrieved_context_id": f"sos_elections_index:candidate:{row['contest_id']}:{normalize_key(row['candidate'])}",
            "retrieved_source": "sos_elections_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": self.payload().get("sanitization_note"),
            "citations": self.citation(matched_rows=1, source_url=row.get("source_url")),
            "source_rows": [{"source_file": row["source_file"], "values": row}],
        }

    def missing_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "I have indexed selected SOS official election-return PDFs, but this question did not match a supported "
                "year, election type, office, candidate, winner, or total-vote pattern. Try `What SOS election data is indexed?`, "
                "`Who won the 2024 Missouri governor election?`, or `How many votes did Donald Trump receive in the 2024 general election?`"
            ),
            "retrieved_context_id": "sos_elections_index:no_match",
            "retrieved_source": "sos_elections_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Answered from SOS election coverage metadata because no exact row matched.",
            "citations": self.citation(),
            "source_rows": [],
        }

    def answer(self, question: str) -> dict[str, Any] | None:
        if not self.available():
            return self.unavailable_answer(question)
        lowered = question.lower()
        if re.search(r"\b(sos|secretary\s+of\s+state|election)\b.*\b(indexed|lookup|exact|data)\b", lowered):
            return self.summary_answer(question)
        if any(term in lowered for term in ["total vote", "total votes", "votes cast"]):
            result = self.total_votes_answer(question)
            if result is not None:
                return result
        if any(term in lowered for term in ["who won", "winner", "won the", "highest vote", "most votes"]):
            result = self.winner_answer(question)
            if result is not None:
                return result
        if any(term in lowered for term in ["how many votes", "receive", "received", "get", "got"]):
            result = self.candidate_answer(question)
            if result is not None:
                return result
        return self.missing_answer(question)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    payload = build_sos_elections_index(force=args.force)
    print(json.dumps({key: value for key, value in payload.items() if key not in {"contests", "candidate_records"}}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
