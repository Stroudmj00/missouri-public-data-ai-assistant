"""Missouri public contract metadata lookup.

The index stores contract metadata and document URLs from public Office of
Administration pages. It intentionally does not download contract PDFs or Word
documents by default.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests

from missouri_tiny_llm.map_public_index import name_tokens, normalize_public_name


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw_public"
CONTRACT_RAW_DIR = RAW_DIR / "contracts"
REPORTS_DIR = PROJECT_ROOT / "reports"
CONTRACT_INDEX_PATH = CONTRACT_RAW_DIR / "missouri_contracts_index.json"

MISSOURI_BUYS_CONTRACT_BOARD_URL = "https://missouribuys.mo.gov/contractboard"
LEGACY_CONTRACT_SEARCH_URL = "https://archive.oa.mo.gov/purch/contracts/"
LEGACY_CONTRACT_LIST_URL = "https://archive.oa.mo.gov/purch/cgi/list.cgi"
LEGACY_CONTRACT_DETAIL_URL = "https://archive.oa.mo.gov/purch/cgi/display.cgi"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def clean_text(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value, flags=re.S)
    decoded = html.unescape(without_tags)
    return re.sub(r"\s+", " ", decoded).strip()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def parse_contract_list(page_text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row_match in re.finditer(r"<TR\s+VALIGN=TOP>(.*?)</TR>", page_text, flags=re.I | re.S):
        row_html = row_match.group(1)
        number_match = re.search(r"display\.cgi\?contnum=([A-Z0-9]+)", row_html, flags=re.I)
        if not number_match:
            continue
        cells = re.findall(r"<TD[^>]*>(.*?)</TD>", row_html, flags=re.I | re.S)
        if len(cells) < 9:
            continue
        contract_number = number_match.group(1).strip().upper()
        rows.append(
            {
                "contract_number": contract_number,
                "description": clean_text(cells[0]),
                "contractor": clean_text(cells[4]),
                "mbe": clean_text(cells[2]),
                "wbe": clean_text(cells[3]),
                "expiration_date": clean_text(cells[5]),
                "renewable": clean_text(cells[6]),
                "usage": clean_text(cells[7]),
                "coop": clean_text(cells[8]),
                "detail_url": f"{LEGACY_CONTRACT_DETAIL_URL}?contnum={contract_number}",
                "source": "Office of Administration legacy contract search",
            }
        )
    return rows


def detail_field(page_text: str, label: str) -> str | None:
    pattern = rf"<strong>\s*{re.escape(label)}\s*</strong>\s*(.*?)(?:<br>|</li>|</blockquote>)"
    match = re.search(pattern, page_text, flags=re.I | re.S)
    return clean_text(match.group(1)) if match else None


def parse_contract_detail(page_text: str, detail_url: str) -> dict[str, Any]:
    document_links: list[dict[str, str]] = []
    for href, label in re.findall(r"<a\s+href=['\"]?([^'\" >]+)['\"]?[^>]*>(.*?)</a>", page_text, flags=re.I | re.S):
        absolute = urljoin(detail_url, href)
        if "/purch/noa/" not in absolute.lower():
            continue
        document_links.append({"label": clean_text(label), "url": absolute})

    return {
        "contract_type": detail_field(page_text, "Contract Type:"),
        "category": detail_field(page_text, "Category:"),
        "contract_period": detail_field(page_text, "Contract Period:"),
        "document_links": document_links,
    }


def fetch_contract_list(session: requests.Session) -> tuple[str, list[dict[str, Any]]]:
    response = session.post(
        LEGACY_CONTRACT_LIST_URL,
        data={"sort": "contract", "submit3": "Submit"},
        timeout=60,
    )
    response.raise_for_status()
    return response.text, parse_contract_list(response.text)


def fetch_contract_detail(session: requests.Session, contract_number: str) -> dict[str, Any]:
    detail_url = f"{LEGACY_CONTRACT_DETAIL_URL}?contnum={contract_number}"
    response = session.get(detail_url, timeout=30)
    response.raise_for_status()
    return parse_contract_detail(response.text, detail_url)


def build_contract_index(force: bool = False, detail_limit: int | None = None, delay_seconds: float = 0.03) -> dict[str, Any]:
    if CONTRACT_INDEX_PATH.exists() and not force:
        return json.loads(CONTRACT_INDEX_PATH.read_text(encoding="utf-8"))

    start = time.perf_counter()
    session = requests.Session()
    list_page_text, contracts = fetch_contract_list(session)
    detail_count = 0
    errors: list[dict[str, str]] = []
    for index, contract in enumerate(contracts):
        if detail_limit is not None and index >= detail_limit:
            break
        try:
            contract.update(fetch_contract_detail(session, contract["contract_number"]))
            detail_count += 1
        except Exception as exc:  # noqa: BLE001 - keep indexing other public contracts.
            errors.append({"contract_number": contract["contract_number"], "error": str(exc)})
        if delay_seconds > 0:
            time.sleep(delay_seconds)

    payload = {
        "generated_at_utc": utc_now(),
        "source_urls": {
            "missouri_buys_contract_board": MISSOURI_BUYS_CONTRACT_BOARD_URL,
            "legacy_contract_search": LEGACY_CONTRACT_SEARCH_URL,
            "legacy_contract_list": LEGACY_CONTRACT_LIST_URL,
        },
        "contract_count": len(contracts),
        "detail_count": detail_count,
        "error_count": len(errors),
        "list_page_bytes": len(list_page_text.encode("utf-8", errors="replace")),
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "notes": [
            "Contract metadata and document URLs are indexed.",
            "Contract PDF and Word documents are linked but not downloaded by default.",
            "Payment totals, when shown, come from the separate local MAP expenditure index.",
        ],
        "errors": errors,
        "contracts": contracts,
    }
    write_json(CONTRACT_INDEX_PATH, payload)
    write_json(
        REPORTS_DIR / "contract_index_report.json",
        {
            key: value
            for key, value in payload.items()
            if key not in {"contracts"}
        },
    )
    return payload


class ContractIndex:
    def __init__(self, path: Path = CONTRACT_INDEX_PATH) -> None:
        self.path = path
        self._payload: dict[str, Any] | None = None
        self._contracts: list[dict[str, Any]] | None = None

    def available(self) -> bool:
        return self.path.exists() and self.path.stat().st_size > 0

    def payload(self) -> dict[str, Any]:
        if self._payload is None:
            if not self.available():
                self._payload = {}
            else:
                self._payload = json.loads(self.path.read_text(encoding="utf-8"))
        return self._payload

    def contracts(self) -> list[dict[str, Any]]:
        if self._contracts is None:
            self._contracts = list(self.payload().get("contracts", []))
        return self._contracts

    def summary(self) -> dict[str, Any]:
        payload = self.payload()
        return {
            "available": self.available(),
            "contract_count": payload.get("contract_count", 0),
            "detail_count": payload.get("detail_count", 0),
            "source_urls": payload.get("source_urls", {}),
            "generated_at_utc": payload.get("generated_at_utc"),
        }

    def find_by_number(self, question: str) -> dict[str, Any] | None:
        candidates = {contract["contract_number"]: contract for contract in self.contracts()}
        for token in re.findall(r"\b[A-Z]{2}\d{6,}[A-Z0-9]*\b", question.upper()):
            if token in candidates:
                return candidates[token]
        return None

    def search(self, question: str, limit: int = 5) -> list[dict[str, Any]]:
        tokens = name_tokens(question)
        if not tokens:
            return []
        ranked: list[tuple[int, dict[str, Any]]] = []
        for contract in self.contracts():
            haystack = " ".join(
                [
                    contract.get("contract_number", ""),
                    contract.get("description", ""),
                    contract.get("contractor", ""),
                    contract.get("category") or "",
                    contract.get("contract_type") or "",
                ]
            )
            haystack_tokens = set(normalize_public_name(haystack).split())
            overlap = len(tokens & haystack_tokens)
            if overlap == 0:
                continue
            score = overlap * 100 - abs(len(tokens) - len(haystack_tokens))
            ranked.append((score, contract))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [contract for _, contract in ranked[:limit]]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--detail-limit", type=int, default=None)
    parser.add_argument("--delay-seconds", type=float, default=0.03)
    args = parser.parse_args()
    payload = build_contract_index(
        force=args.force,
        detail_limit=args.detail_limit,
        delay_seconds=args.delay_seconds,
    )
    print(json.dumps({key: value for key, value in payload.items() if key != "contracts"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
