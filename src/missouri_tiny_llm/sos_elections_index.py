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


@dataclass(frozen=True)
class CandidateColumn:
    candidate: str
    party: str


@dataclass(frozen=True)
class CountyContestSpec:
    office: str
    page_start: int
    page_end: int
    candidate_columns: tuple[CandidateColumn, ...]
    includes_total_column: bool = False


@dataclass(frozen=True)
class CountyResultsPdfSpec:
    key: str
    label: str
    election_type: str
    year: int
    election_date: str
    url: str
    contests: tuple[CountyContestSpec, ...]

    @property
    def file_name(self) -> str:
        return self.url.rsplit("/", 1)[-1]


@dataclass(frozen=True)
class TurnoutPdfSpec:
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

COUNTY_RESULTS_PDFS: tuple[CountyResultsPdfSpec, ...] = (
    CountyResultsPdfSpec(
        key="2024_general_county_results",
        label="2024 General Election county results",
        election_type="general",
        year=2024,
        election_date="2024-11-05",
        url="https://www.sos.mo.gov/CMSImages/ElectionResultsStatistics/ActualResults-November52024.pdf",
        contests=(
            CountyContestSpec(
                office="U.S. President and Vice President",
                page_start=1,
                page_end=4,
                candidate_columns=(
                    CandidateColumn("Donald J. Trump, JD Vance", "Republican"),
                    CandidateColumn("Kamala D. Harris, Tim Walz", "Democratic"),
                    CandidateColumn("Chase Oliver, Mike ter Maat", "Libertarian"),
                    CandidateColumn("Jill Stein, Rudolph Ware", "Green"),
                    CandidateColumn("Peter Sonski, Lauren Onak", "Write-in"),
                    CandidateColumn("Claudia De La Cruz, Karina Garcia", "Write-in"),
                    CandidateColumn("Shiva Ayyadurai, Crystal Ellis", "Write-in"),
                ),
            ),
            CountyContestSpec(
                office="Governor",
                page_start=13,
                page_end=16,
                candidate_columns=(
                    CandidateColumn("Mike Kehoe", "Republican"),
                    CandidateColumn("Crystal Quade", "Democratic"),
                    CandidateColumn("Bill Slantz", "Libertarian"),
                    CandidateColumn("Paul Lehmann", "Green"),
                    CandidateColumn("Theo (Ted) Brown Sr", "Write-in"),
                ),
                includes_total_column=True,
            ),
        ),
    ),
)

TURNOUT_PDFS: tuple[TurnoutPdfSpec, ...] = (
    TurnoutPdfSpec(
        key="2024_general_turnout",
        label="2024 General Election voter turnout",
        election_type="general",
        year=2024,
        election_date="2024-11-05",
        url="https://www.sos.mo.gov/CMSImages/ElectionResultsStatistics/Nov2024OfficialVoterTurnout.pdf",
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


def download_pdf(session: requests.Session, spec: ElectionPdfSpec | CountyResultsPdfSpec | TurnoutPdfSpec, force: bool = False) -> Path:
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


def parse_int_token(token: str) -> int:
    return int(token.replace(",", ""))


def parse_named_int_row(line: str, value_count: int) -> tuple[str, list[int]] | None:
    tokens = line.split()
    if len(tokens) < value_count + 1:
        return None
    value_tokens = tokens[-value_count:]
    if not all(re.fullmatch(r"\d[\d,]*", token) for token in value_tokens):
        return None
    name = clean_text(" ".join(tokens[:-value_count]))
    if not name or name.lower() in {"county", "total votes"}:
        return None
    return name, [parse_int_token(token) for token in value_tokens]


def parse_turnout_row(line: str) -> tuple[str, list[int], float] | None:
    tokens = line.split()
    if len(tokens) == 5 and all(re.fullmatch(r"\d[\d,]*", token) for token in tokens[:4]) and re.fullmatch(
        r"\d+(?:\.\d+)?%", tokens[4]
    ):
        return "Statewide", [parse_int_token(token) for token in tokens[:4]], float(tokens[4].rstrip("%"))
    if len(tokens) < 6:
        return None
    if not all(re.fullmatch(r"\d[\d,]*", token) for token in tokens[-5:-1]):
        return None
    if not re.fullmatch(r"\d+(?:\.\d+)?%", tokens[-1]):
        return None
    name = clean_text(" ".join(tokens[:-5]))
    if not name or name.lower() in {"county", "voters", "active voters", "inactive voters", "actual voters"}:
        return None
    return name, [parse_int_token(token) for token in tokens[-5:-1]], float(tokens[-1].rstrip("%"))


def parse_county_results_pdf(path: Path, spec: CountyResultsPdfSpec) -> tuple[list[dict[str, Any]], int]:
    reader = PdfReader(str(path))
    records: list[dict[str, Any]] = []
    for contest in spec.contests:
        contest_id = f"{spec.key}:{normalize_key(contest.office)}"
        value_count = len(contest.candidate_columns) + int(contest.includes_total_column)
        for page_number in range(contest.page_start, min(contest.page_end, len(reader.pages)) + 1):
            text = reader.pages[page_number - 1].extract_text() or ""
            for raw_line in text.splitlines():
                parsed = parse_named_int_row(clean_text(raw_line), value_count=value_count)
                if parsed is None:
                    continue
                jurisdiction, values = parsed
                if jurisdiction.lower() in {"missouri office of secretary of state", "official results"}:
                    continue
                county_total_votes = values[-1] if contest.includes_total_column else None
                candidate_values = values[: len(contest.candidate_columns)]
                county_label = "Statewide" if jurisdiction == "Total" else jurisdiction
                for column, votes in zip(contest.candidate_columns, candidate_values):
                    records.append(
                        {
                            "record_type": "county_candidate_result",
                            "contest_id": contest_id,
                            "election_key": spec.key,
                            "election_label": spec.label,
                            "election_type": spec.election_type,
                            "year": spec.year,
                            "election_date": spec.election_date,
                            "office": contest.office,
                            "office_norm": normalize_text(contest.office),
                            "county_or_jurisdiction": county_label,
                            "county_norm": normalize_text(county_label),
                            "candidate": column.candidate,
                            "candidate_norm": normalize_text(column.candidate),
                            "party": column.party,
                            "votes": votes,
                            "county_total_votes": county_total_votes,
                            "source_url": spec.url,
                            "source_file": spec.file_name,
                            "source_page": page_number,
                        }
                    )
    return records, len(reader.pages)


def parse_turnout_pdf(path: Path, spec: TurnoutPdfSpec) -> tuple[list[dict[str, Any]], int]:
    reader = PdfReader(str(path))
    records: list[dict[str, Any]] = []
    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        for raw_line in text.splitlines():
            parsed = parse_turnout_row(clean_text(raw_line))
            if parsed is None:
                continue
            jurisdiction, values, turnout_percent = parsed
            registered_voters, active_voters, inactive_voters, actual_voters = values
            records.append(
                {
                    "record_type": "voter_turnout",
                    "election_key": spec.key,
                    "election_label": spec.label,
                    "election_type": spec.election_type,
                    "year": spec.year,
                    "election_date": spec.election_date,
                    "county_or_jurisdiction": jurisdiction,
                    "county_norm": normalize_text(jurisdiction),
                    "registered_voters": registered_voters,
                    "active_voters": active_voters,
                    "inactive_voters": inactive_voters,
                    "actual_voters": actual_voters,
                    "turnout_percent": turnout_percent,
                    "source_url": spec.url,
                    "source_file": spec.file_name,
                    "source_page": page_number,
                }
            )
    return records, len(reader.pages)


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
    county_results: list[dict[str, Any]] = []
    turnout_records: list[dict[str, Any]] = []
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
    for spec in COUNTY_RESULTS_PDFS:
        path = download_pdf(session, spec, force=force)
        parsed_county_results, pages = parse_county_results_pdf(path, spec)
        county_results.extend(parsed_county_results)
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
                "county_result_row_count": len(parsed_county_results),
                "selected_county_contests": [contest.office for contest in spec.contests],
            }
        )
    for spec in TURNOUT_PDFS:
        path = download_pdf(session, spec, force=force)
        parsed_turnout_records, pages = parse_turnout_pdf(path, spec)
        turnout_records.extend(parsed_turnout_records)
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
                "turnout_row_count": len(parsed_turnout_records),
            }
        )

    year_counts = Counter(str(row["year"]) for row in candidates)
    office_counts = Counter(row["office"] for row in candidates)
    county_result_counts = Counter(row["office"] for row in county_results)
    turnout_year_counts = Counter(str(row["year"]) for row in turnout_records)
    total_row_count = len(candidates) + len(county_results) + len(turnout_records)
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
        "county_result_row_count": len(county_results),
        "turnout_row_count": len(turnout_records),
        "total_indexed_row_count": total_row_count,
        "year_counts": dict(sorted(year_counts.items(), reverse=True)),
        "turnout_year_counts": dict(sorted(turnout_year_counts.items(), reverse=True)),
        "top_offices_by_row_count": dict(office_counts.most_common(12)),
        "county_result_offices_by_row_count": dict(county_result_counts.most_common(12)),
        "sanitization_note": (
            "This index stores selected official SOS statewide return rows, selected 2024 county result rows, and "
            "2024 county/jurisdiction voter-turnout aggregates. It does not include voter files or precinct-level files."
        ),
        "contests": contests,
        "candidate_records": candidates,
        "county_result_records": county_results,
        "turnout_records": turnout_records,
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
            "county_result_row_count": payload["county_result_row_count"],
            "turnout_row_count": payload["turnout_row_count"],
            "total_indexed_row_count": payload["total_indexed_row_count"],
            "year_counts": payload["year_counts"],
            "turnout_year_counts": payload["turnout_year_counts"],
            "top_offices_by_row_count": payload["top_offices_by_row_count"],
            "county_result_offices_by_row_count": payload["county_result_offices_by_row_count"],
            "sample_contests": contests[:10],
            "sample_candidate_records": candidates[:10],
            "sample_county_result_records": county_results[:10],
            "sample_turnout_records": turnout_records[:10],
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

    def county_result_records(self) -> list[dict[str, Any]]:
        return list(self.payload().get("county_result_records", []))

    def turnout_records(self) -> list[dict[str, Any]]:
        return list(self.payload().get("turnout_records", []))

    def total_indexed_rows(self) -> int:
        payload = self.payload()
        return int(
            payload.get(
                "total_indexed_row_count",
                payload.get("candidate_row_count", 0)
                + payload.get("county_result_row_count", 0)
                + payload.get("turnout_row_count", 0),
            )
        )

    def requested_jurisdiction(self, question: str) -> str | None:
        question_norm = normalize_text(question)
        jurisdictions = {
            row.get("county_or_jurisdiction", "")
            for row in [*self.county_result_records(), *self.turnout_records()]
            if row.get("county_or_jurisdiction")
        }
        for jurisdiction in sorted(jurisdictions, key=len, reverse=True):
            jurisdiction_norm = normalize_text(jurisdiction)
            if not jurisdiction_norm:
                continue
            if jurisdiction_norm == "statewide" and "statewide" in question_norm:
                return jurisdiction
            if jurisdiction_norm in question_norm:
                return jurisdiction
        return None

    def citation(self, matched_rows: int = 0, source_url: str | None = None) -> list[dict[str, Any]]:
        payload = self.payload()
        source_files = []
        for source in payload.get("source_files", []):
            if source_url and source.get("url") != source_url:
                continue
            row_count = (
                int(source.get("candidate_row_count") or 0)
                + int(source.get("county_result_row_count") or 0)
                + int(source.get("turnout_row_count") or 0)
            )
            source_files.append(
                {
                    "category": "sos_elections",
                    "category_label": source.get("label", "SOS election returns"),
                    "file_name": source.get("url"),
                    "row_count": row_count,
                    "year": source.get("year"),
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
                    "row_count": self.total_indexed_rows(),
                    "year": None,
                    "bytes": payload.get("bytes"),
                    "sha256": None,
                }
            ]
        citation_year = source_files[0].get("year") if source_url and len(source_files) == 1 else None
        return [
            {
                "dataset": payload.get("source", "Missouri Secretary of State official election returns"),
                "category": "Elections",
                "kind": "official election-return and turnout rows",
                "lookup_table": "sos_elections_index",
                "year": citation_year,
                "year_range": None if citation_year else ", ".join(sorted(payload.get("year_counts", {}).keys())),
                "source_files": source_files,
                "source_file_count": len(source_files),
                "source_rows": self.total_indexed_rows(),
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
        statewide_labels = "; ".join(item["label"] for item in payload.get("source_files", []) if item.get("candidate_row_count"))
        county_labels = "; ".join(
            item["label"]
            for item in payload.get("source_files", [])
            if item.get("county_result_row_count") or item.get("turnout_row_count")
        )
        return {
            "question": question,
            "answer": (
                "The SOS election exact lookup layer indexes selected Missouri Secretary of State official election-return PDFs. "
                f"It currently covers 3 official statewide election-return PDF(s): {statewide_labels}. "
                f"It also covers selected 2024 county/turnout PDF(s): {county_labels}. "
                f"The parser extracted {payload.get('contest_count', 0):,} contests and "
                f"{payload.get('candidate_row_count', 0):,} statewide candidate/ballot row(s), "
                f"{payload.get('county_result_row_count', 0):,} selected county candidate row(s), and "
                f"{payload.get('turnout_row_count', 0):,} voter-turnout row(s). It can answer selected statewide "
                "winner, candidate vote, percentage, total-vote, primary party-winner, county winner/vote, and "
                "county turnout questions. It does not include voter files or precinct-level files."
            ),
            "retrieved_context_id": "sos_elections_index:summary",
            "retrieved_source": "sos_elections_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": payload.get("sanitization_note"),
            "citations": self.citation(matched_rows=self.total_indexed_rows()),
            "source_rows": [],
        }

    def turnout_answer(self, question: str) -> dict[str, Any] | None:
        rows = contest_filter(self.turnout_records(), question)
        jurisdiction = self.requested_jurisdiction(question)
        if jurisdiction:
            rows = [row for row in rows if row.get("county_or_jurisdiction") == jurisdiction]
        elif any(term in normalize_text(question) for term in ["statewide", "missouri"]):
            rows = [row for row in rows if row.get("county_or_jurisdiction") == "Statewide"]
        else:
            return None
        if not rows:
            return None
        row = rows[0]
        return {
            "question": question,
            "answer": (
                f"In the official {row['election_label']} report, {row['county_or_jurisdiction']} had "
                f"{row['registered_voters']:,} registered voters, {row['actual_voters']:,} actual voters, and "
                f"{row['turnout_percent']:.2f}% voter turnout."
            ),
            "retrieved_context_id": f"sos_elections_index:turnout:{row['election_key']}:{normalize_key(row['county_or_jurisdiction'])}",
            "retrieved_source": "sos_elections_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": self.payload().get("sanitization_note"),
            "citations": self.citation(matched_rows=1, source_url=row.get("source_url")),
            "source_rows": [{"source_file": row["source_file"], "values": row}],
        }

    def turnout_rank_answer(self, question: str) -> dict[str, Any] | None:
        rows = [row for row in contest_filter(self.turnout_records(), question) if row.get("county_or_jurisdiction") != "Statewide"]
        if not rows:
            return None
        lowered = question.lower()
        reverse = not any(term in lowered for term in ["lowest", "least", "smallest"])
        if "registered" in lowered:
            field = "registered_voters"
            field_label = "registered voters"
        elif "actual" in lowered or "ballots" in lowered:
            field = "actual_voters"
            field_label = "actual voters"
        elif "inactive" in lowered:
            field = "inactive_voters"
            field_label = "inactive voters"
        elif "active" in lowered:
            field = "active_voters"
            field_label = "active voters"
        else:
            field = "turnout_percent"
            field_label = "voter turnout"
        row = sorted(rows, key=lambda item: float(item[field]), reverse=reverse)[0]
        rank_word = "highest" if reverse else "lowest"
        value = f"{row[field]:.2f}%" if field == "turnout_percent" else f"{row[field]:,}"
        return {
            "question": question,
            "answer": (
                f"In the official {row['election_label']} report, {row['county_or_jurisdiction']} had the "
                f"{rank_word} indexed county/jurisdiction {field_label} value at {value} "
                f"({row['actual_voters']:,} actual voters out of {row['registered_voters']:,} registered voters)."
            ),
            "retrieved_context_id": f"sos_elections_index:turnout_rank:{row['election_key']}:{rank_word}",
            "retrieved_source": "sos_elections_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": self.payload().get("sanitization_note"),
            "citations": self.citation(matched_rows=len(rows), source_url=row.get("source_url")),
            "source_rows": [{"source_file": row["source_file"], "values": row}],
        }

    def county_winner_answer(self, question: str) -> dict[str, Any] | None:
        if office_alias(question) is None:
            return None
        jurisdiction = self.requested_jurisdiction(question)
        if not jurisdiction:
            return None
        rows = contest_filter(self.county_result_records(), question)
        rows = [row for row in rows if row.get("county_or_jurisdiction") == jurisdiction]
        party = requested_party(question)
        if party:
            rows = [row for row in rows if row.get("party") == party]
        if not rows:
            return None
        winner = max(rows, key=lambda row: int(row["votes"]))
        total_clause = (
            f" out of {winner['county_total_votes']:,} county votes"
            if winner.get("county_total_votes") is not None
            else ""
        )
        return {
            "question": question,
            "answer": (
                f"In the official {winner['election_label']}, {winner['candidate']} won "
                f"{winner['county_or_jurisdiction']} for {winner['office']} with {winner['votes']:,} votes{total_clause}."
            ),
            "retrieved_context_id": (
                f"sos_elections_index:county_winner:{winner['contest_id']}:"
                f"{normalize_key(winner['county_or_jurisdiction'])}:{normalize_key(party or 'all')}"
            ),
            "retrieved_source": "sos_elections_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": self.payload().get("sanitization_note"),
            "citations": self.citation(matched_rows=len(rows), source_url=winner.get("source_url")),
            "source_rows": [{"source_file": winner["source_file"], "values": winner}],
        }

    def county_candidate_answer(self, question: str) -> dict[str, Any] | None:
        jurisdiction = self.requested_jurisdiction(question)
        if not jurisdiction:
            return None
        rows = contest_filter(self.county_result_records(), question)
        rows = [row for row in rows if row.get("county_or_jurisdiction") == jurisdiction]
        question_tokens = token_set(question)
        scored = [(candidate_score(row, question_tokens), row) for row in rows]
        scored = [item for item in scored if item[0] > 0]
        if not scored:
            return None
        scored.sort(key=lambda item: (item[0], item[1]["votes"]), reverse=True)
        row = scored[0][1]
        total_clause = f" out of {row['county_total_votes']:,} county votes" if row.get("county_total_votes") is not None else ""
        return {
            "question": question,
            "answer": (
                f"In the official {row['election_label']}, {row['candidate']} received "
                f"{row['votes']:,} votes in {row['county_or_jurisdiction']} for {row['office']}{total_clause}."
            ),
            "retrieved_context_id": (
                f"sos_elections_index:county_candidate:{row['contest_id']}:"
                f"{normalize_key(row['county_or_jurisdiction'])}:{normalize_key(row['candidate'])}"
            ),
            "retrieved_source": "sos_elections_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": self.payload().get("sanitization_note"),
            "citations": self.citation(matched_rows=1, source_url=row.get("source_url")),
            "source_rows": [{"source_file": row["source_file"], "values": row}],
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
                "year, election type, office, county/jurisdiction, candidate, winner, turnout, or total-vote pattern. "
                "Try `What SOS election data is indexed?`, `Who won Boone County for governor in 2024?`, "
                "`What was Boone County voter turnout in 2024?`, or "
                "`How many votes did Donald Trump receive in the 2024 general election?`"
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
        if "turnout" in lowered or "registered voters" in lowered or "actual voters" in lowered:
            if any(term in lowered for term in ["highest", "lowest", "least", "most", "smallest", "largest"]):
                result = self.turnout_rank_answer(question)
                if result is not None:
                    return result
            result = self.turnout_answer(question)
            if result is not None:
                return result
        if any(term in lowered for term in ["total vote", "total votes", "votes cast"]):
            result = self.total_votes_answer(question)
            if result is not None:
                return result
        if any(term in lowered for term in ["who won", "winner", "won the", "highest vote", "most votes"]):
            result = self.county_winner_answer(question)
            if result is not None:
                return result
            result = self.winner_answer(question)
            if result is not None:
                return result
        if any(term in lowered for term in ["how many votes", "receive", "received", "get", "got"]):
            result = self.county_candidate_answer(question)
            if result is not None:
                return result
            result = self.candidate_answer(question)
            if result is not None:
                return result
        return self.missing_answer(question)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    payload = build_sos_elections_index(force=args.force)
    hidden_keys = {"contests", "candidate_records", "county_result_records", "turnout_records"}
    print(json.dumps({key: value for key, value in payload.items() if key not in hidden_keys}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
