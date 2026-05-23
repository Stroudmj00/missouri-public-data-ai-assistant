"""Inventory and download all Missouri Accountability Portal public files."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw_public"
MAP_ALL_DIR = RAW_DIR / "map_all"
REPORTS_DIR = PROJECT_ROOT / "reports"
MAP_DOWNLOAD_URL = "https://mapyourtaxes.mo.gov/MAP/Download/"

CATEGORY_NAMES = {
    "EXP": "expenditures",
    "STM": "stimulus",
    "CC": "check_cancellations",
    "EMP": "employees",
    "TC": "tax_credits",
    "BWH": "budget_restrictions",
    "FED": "federal_grants",
    "BND": "bonds",
}


class InputParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.inputs: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "input":
            return
        values = dict(attrs)
        name = values.get("name")
        if name:
            self.inputs[name] = values.get("value") or ""


@dataclass(frozen=True)
class MapDownloadItem:
    target: str
    title: str
    label: str
    category: str
    category_name: str
    estimated_mb: float
    size_label: str


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return cleaned.strip("._") or "download"


def parse_size_to_mb(size_text: str, unit: str) -> float:
    size = float(size_text)
    if unit.upper() == "KB":
        return round(size / 1024, 4)
    return round(size, 4)


def fetch_map_page(session: requests.Session) -> tuple[str, dict[str, str]]:
    response = session.get(MAP_DOWNLOAD_URL, timeout=30)
    response.raise_for_status()
    parser = InputParser()
    parser.feed(response.text)
    return response.text, parser.inputs


def parse_inventory(page_text: str) -> list[MapDownloadItem]:
    anchor_re = re.compile(
        r'<a id="(?P<id>[^"]+)" title="(?P<title>[^"]+)" '
        r'href="javascript:__doPostBack\(&#39;(?P<target>[^&]+)&#39;,&#39;&#39;\)">'
        r"(?P<label>[^<]+)</a>",
        re.IGNORECASE,
    )
    items: list[MapDownloadItem] = []
    for match in anchor_re.finditer(page_text):
        target = match.group("target")
        after = page_text[match.end() : match.end() + 180]
        size_match = re.search(
            r'<span id="lbl'
            + re.escape(match.group("id"))
            + r'">\s*(?:&nbsp;?|&#160;|\s)*([\d.]+)\s*(KB|MB)',
            after,
            re.IGNORECASE,
        )
        if not size_match:
            continue
        size_text, unit = size_match.groups()
        category = target.split("_", 1)[0]
        items.append(
            MapDownloadItem(
                target=target,
                title=match.group("title"),
                label=match.group("label"),
                category=category,
                category_name=CATEGORY_NAMES.get(category, category.lower()),
                estimated_mb=parse_size_to_mb(size_text, unit),
                size_label=f"{size_text} {unit}",
            )
        )
    return items


def content_disposition_filename(header: str) -> str | None:
    if not header:
        return None
    utf_match = re.search(r"filename\*=UTF-8''([^;]+)", header, re.IGNORECASE)
    if utf_match:
        return unquote(utf_match.group(1).strip().strip('"'))
    simple_match = re.search(r'filename="?([^";]+)"?', header, re.IGNORECASE)
    if simple_match:
        return simple_match.group(1).strip()
    return None


def fallback_extension(content: bytes, content_type: str) -> str:
    if content.startswith(b"MZ"):
        return ".exe"
    if content.startswith(b"PK\x03\x04"):
        return ".zip"
    if b"|" in content[:4096]:
        return ".txt"
    if "text" in content_type.lower():
        return ".txt"
    return ".bin"


def target_path(item: MapDownloadItem, response: requests.Response | None = None) -> Path:
    category_dir = MAP_ALL_DIR / item.category_name
    if response is not None:
        filename = content_disposition_filename(response.headers.get("content-disposition", ""))
        if filename:
            return category_dir / safe_name(filename)
        extension = fallback_extension(response.content, response.headers.get("content-type", ""))
    else:
        extension = ".dat"
    return category_dir / f"MAP_{safe_name(item.target)}{extension}"


def disk_free_mb(path: Path) -> float:
    usage = shutil.disk_usage(path)
    return round(usage.free / 1024**2, 2)


def inventory_payload(items: list[MapDownloadItem]) -> dict[str, Any]:
    categories: dict[str, dict[str, Any]] = {}
    for item in items:
        current = categories.setdefault(
            item.category_name,
            {"count": 0, "estimated_mb": 0.0, "prefix": item.category},
        )
        current["count"] += 1
        current["estimated_mb"] = round(current["estimated_mb"] + item.estimated_mb, 4)

    return {
        "generated_at_utc": utc_now(),
        "source_url": MAP_DOWNLOAD_URL,
        "item_count": len(items),
        "estimated_total_mb": round(sum(item.estimated_mb for item in items), 4),
        "local_raw_dir": str(MAP_ALL_DIR.relative_to(PROJECT_ROOT)),
        "c_drive_free_mb": disk_free_mb(PROJECT_ROOT.anchor or "C:\\"),
        "categories": categories,
        "items": [asdict(item) for item in items],
        "notes": [
            "MAP page says expenditure files before fiscal year 2026 and employee files before calendar year 2026 are zipped executable downloads.",
            "Downloader saves those files as raw public artifacts and never executes them.",
            "Training should use generated examples and indexes, not raw row memorization.",
        ],
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def download_item(
    session: requests.Session,
    item: MapDownloadItem,
    hidden_inputs: dict[str, str],
    force: bool,
) -> dict[str, Any]:
    category_dir = MAP_ALL_DIR / item.category_name
    category_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(category_dir.glob(f"*{safe_name(item.target)}*"))
    if existing and not force:
        path = existing[0]
        return {
            "target": item.target,
            "downloaded": False,
            "path": str(path.relative_to(PROJECT_ROOT)),
            "bytes": path.stat().st_size,
            "elapsed_seconds": 0,
            "reason": "exists",
        }

    data = dict(hidden_inputs)
    data["__EVENTTARGET"] = item.target
    data["__EVENTARGUMENT"] = ""
    start = time.perf_counter()
    response = session.post(MAP_DOWNLOAD_URL, data=data, timeout=240)
    response.raise_for_status()

    if b"<html" in response.content[:512].lower() and b"|" not in response.content[:4096]:
        raise RuntimeError(f"Download for {item.target} returned HTML instead of a data file")

    path = target_path(item, response)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(response.content)
    return {
        "target": item.target,
        "downloaded": True,
        "path": str(path.relative_to(PROJECT_ROOT)),
        "bytes": path.stat().st_size,
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "estimated_mb": item.estimated_mb,
        "content_type": response.headers.get("content-type"),
        "content_disposition": response.headers.get("content-disposition"),
        "file_kind": "zipped_executable" if response.content.startswith(b"MZ") else "data_file",
    }


def run(download: bool, force: bool, delay_seconds: float, max_items: int | None) -> dict[str, Any]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    MAP_ALL_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    page_text, hidden_inputs = fetch_map_page(session)
    items = parse_inventory(page_text)
    if max_items is not None:
        items = items[:max_items]

    inventory = inventory_payload(items)
    write_json(REPORTS_DIR / "map_all_inventory.json", inventory)

    if not download:
        return inventory | {"downloaded": False}

    minimum_free_mb = inventory["estimated_total_mb"] * 3 + 2048
    if inventory["c_drive_free_mb"] < minimum_free_mb:
        raise RuntimeError(
            f"Refusing download: need at least {minimum_free_mb:.1f} MB free, "
            f"found {inventory['c_drive_free_mb']:.1f} MB"
        )

    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    start = time.perf_counter()
    for index, item in enumerate(items, start=1):
        try:
            result = download_item(session, item, hidden_inputs, force=force)
            results.append(result | {"index": index, "item_count": len(items)})
        except Exception as exc:  # noqa: BLE001 - report per-file failures and continue.
            errors.append({"target": item.target, "error": str(exc)})
        if delay_seconds > 0 and index < len(items):
            time.sleep(delay_seconds)

    payload = {
        "generated_at_utc": utc_now(),
        "source_url": MAP_DOWNLOAD_URL,
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "item_count": len(items),
        "downloaded_count": sum(1 for result in results if result.get("downloaded")),
        "existing_count": sum(1 for result in results if not result.get("downloaded")),
        "error_count": len(errors),
        "bytes_total": sum(result.get("bytes", 0) for result in results),
        "map_all_dir": str(MAP_ALL_DIR.relative_to(PROJECT_ROOT)),
        "results": results,
        "errors": errors,
    }
    write_json(REPORTS_DIR / "map_all_download_report.json", payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--download", action="store_true", help="Download files after writing inventory.")
    parser.add_argument("--force", action="store_true", help="Redownload existing files.")
    parser.add_argument("--delay-seconds", type=float, default=0.15)
    parser.add_argument("--max-items", type=int, default=None)
    args = parser.parse_args()

    payload = run(
        download=args.download,
        force=args.force,
        delay_seconds=args.delay_seconds,
        max_items=args.max_items,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
