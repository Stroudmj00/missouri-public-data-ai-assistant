"""Build and query Missouri MSDIS geospatial resource metadata.

This module indexes metadata and service links only. It does not download
vector layers, imagery tiles, LiDAR point clouds, shapefiles, or geodatabases.
"""

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
RAW_DIR = PROJECT_ROOT / "data" / "raw_public" / "msdis_geospatial"
INDEX_PATH = RAW_DIR / "msdis_geospatial_index.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "msdis_geospatial_index_report.json"
SOURCE_NAME = "MSDIS geospatial resource metadata"


@dataclass(frozen=True)
class HtmlPage:
    key: str
    label: str
    url: str
    default_topic: str


@dataclass(frozen=True)
class ArcgisRoot:
    key: str
    label: str
    url: str
    default_topic: str
    recurse_folders: bool = True


HTML_PAGES: tuple[HtmlPage, ...] = (
    HtmlPage("home", "MSDIS", "https://www.msdis.missouri.edu/", "MSDIS overview"),
    HtmlPage("web_services", "MSDIS Web Services", "https://www.msdis.missouri.edu/webservices.html", "web services"),
    HtmlPage("archive", "MSDIS Data Library Archive", "https://msdis-archive.missouri.edu/archive/", "archive/data library"),
)

DCAT_URL = "https://data-msdis.opendata.arcgis.com/data.json"

ARCGIS_ROOTS: tuple[ArcgisRoot, ...] = (
    ArcgisRoot(
        "vector_services",
        "MSDIS vector ArcGIS REST services",
        "https://services2.arcgis.com/kNS2ppBA4rwAQQZy/ArcGIS/rest/services?f=pjson",
        "vector feature services",
        recurse_folders=False,
    ),
    ArcgisRoot(
        "state_imagery_services",
        "MSDIS state imagery ArcGIS REST services",
        "https://stateimagery.msdis.missouri.edu/arcgis/rest/services?f=pjson",
        "imagery services",
    ),
    ArcgisRoot(
        "imagery_services",
        "MSDIS imagery ArcGIS REST services",
        "https://imagery.msdis.missouri.edu/arcgis/rest/services?f=pjson",
        "imagery services",
    ),
    ArcgisRoot(
        "lidar_services",
        "MSDIS LiDAR ArcGIS REST services",
        "https://lidar.msdis.missouri.edu/arcgis/rest/services?f=pjson",
        "LiDAR/elevation services",
    ),
)

ANCHOR_PATTERN = re.compile(r"<a\s+[^>]*href=['\"]([^'\"]+)['\"][^>]*>(.*?)</a>", re.I | re.S)
YEAR_PATTERN = re.compile(r"\b(20\d{2}|19\d{2})\b")
KEEP_PATTERN = re.compile(
    r"open data|web services?|arcgis|rest services?|feature server|map server|image server|gis|geospatial|"
    r"imagery|lidar|elevation|boundary|boundaries|county|municipal|parcel|hydro|water|transportation|"
    r"environment|conservation|health|demograph|census|archive|vector|download|shapefile|data library",
    re.I,
)
SKIP_PATTERN = re.compile(
    r"^(skip|home$|contact|copyright|privacy|give|donat|facebook|twitter|x - formerly twitter|"
    r"missouri university|university of missouri|mo\.gov|search)$",
    re.I,
)

GENERIC_QUERY_TOKENS = {
    "ABOUT",
    "AND",
    "ARE",
    "CAN",
    "CONNECTED",
    "DATA",
    "DATASET",
    "DATASETS",
    "FOR",
    "GEO",
    "GEOSPATIAL",
    "GIS",
    "GIVE",
    "INDEX",
    "INDEXED",
    "LINK",
    "LINKS",
    "MISSOURI",
    "MSDIS",
    "PUBLIC",
    "RESOURCE",
    "RESOURCES",
    "SEARCH",
    "SERVICE",
    "SERVICES",
    "SHOW",
    "SOURCE",
    "SOURCES",
    "SPATIAL",
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
        token.strip("$.,()")
        for token in normalize_text(value).replace("/", " ").replace("-", " ").split()
        if len(token.strip("$.,()")) > 2 and token.strip("$.,()") not in GENERIC_QUERY_TOKENS
    }


def year_label(*values: str) -> str | None:
    matches = YEAR_PATTERN.findall(" ".join(values))
    return matches[-1] if matches else None


def rest_base(url: str) -> str:
    return url.split("?", 1)[0].rstrip("/")


def service_url(root_url: str, service: dict[str, Any]) -> str:
    base = rest_base(root_url)
    service_name = str(service.get("name", "")).strip("/")
    service_type = str(service.get("type", "")).strip("/")
    if not service_name or not service_type:
        return base
    return f"{base}/{service_name}/{service_type}"


def resource_type(label: str, url: str, fallback: str = "metadata_link") -> str:
    lowered = f"{label} {url}".lower()
    path = urlparse(url).path.lower()
    if "featureserver" in lowered:
        return "feature_service"
    if "imageserver" in lowered:
        return "image_service"
    if "mapserver" in lowered:
        return "map_service"
    if "rest/services" in lowered:
        return "web_service_directory"
    if "opendata.arcgis.com" in lowered or "data-msdis" in lowered:
        return "open_data_dataset"
    if path.endswith((".zip", ".shp", ".gdb", ".geojson", ".csv", ".kml", ".kmz")):
        return "download"
    if "archive" in lowered:
        return "archive_directory"
    return fallback


def infer_topic(label: str, url: str, default_topic: str = "geospatial data") -> str:
    lowered = f"{default_topic} {label} {url}".lower()
    if any(term in lowered for term in ["lidar", "elevation", "dem", "hillshade", "contour"]):
        return "LiDAR/elevation"
    if any(term in lowered for term in ["imagery", "ortho", "aerial", "photo"]):
        return "imagery"
    if any(term in lowered for term in ["boundary", "boundaries", "county", "municipal", "city limits", "school district"]):
        return "boundaries/administrative"
    if any(term in lowered for term in ["transportation", "road", "route", "rail", "airport", "bridge"]):
        return "transportation"
    if any(term in lowered for term in ["hydro", "water", "stream", "river", "lake", "flood", "wetland"]):
        return "hydrography/water"
    if any(term in lowered for term in ["environment", "conservation", "land cover", "natural", "soil", "geology"]):
        return "environment/conservation"
    if any(term in lowered for term in ["parcel", "cadastral", "tax district"]):
        return "parcels/cadastral"
    if any(term in lowered for term in ["demograph", "census", "population", "income", "economic"]):
        return "demographics/economy"
    if any(term in lowered for term in ["emergency", "fire", "police", "public safety", "911"]):
        return "public safety"
    if any(term in lowered for term in ["feature service", "map service", "image service", "arcgis", "rest/services", "web service"]):
        return "ArcGIS/web services"
    if any(term in lowered for term in ["archive", "data library", "vector"]):
        return "archive/data library"
    return default_topic


def is_relevant_link(label: str, absolute_url: str) -> bool:
    if not label or SKIP_PATTERN.search(label):
        return False
    if absolute_url.startswith(("mailto:", "tel:", "javascript:")):
        return False
    parsed = urlparse(absolute_url)
    if parsed.scheme not in {"http", "https"}:
        return False
    return bool(KEEP_PATTERN.search(f"{label} {absolute_url}"))


def make_record(
    *,
    label: str,
    url: str,
    topic: str,
    resource_kind: str,
    source_page: str,
    page_key: str,
    page_label: str,
    description: str = "",
    keywords: list[str] | None = None,
) -> dict[str, Any]:
    keyword_values = [clean_text(value) for value in (keywords or []) if clean_text(value)]
    label_clean = clean_text(label)
    url_clean = clean_text(url)
    return {
        "resource_id": hashlib.sha1(f"{page_key}:{label_clean}:{url_clean}".encode("utf-8")).hexdigest()[:16],
        "label": label_clean,
        "url": url_clean,
        "topic": topic,
        "resource_type": resource_kind,
        "year_label": year_label(label_clean, url_clean, description),
        "description": clean_text(description)[:500],
        "keywords": keyword_values[:12],
        "page_key": page_key,
        "page_label": page_label,
        "source_page": source_page,
        "source_host": urlparse(url_clean).netloc,
    }


def parse_html_links(page: HtmlPage, page_text: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for href, raw_label in ANCHOR_PATTERN.findall(page_text):
        absolute = urljoin(page.url, html.unescape(href)).split("#", 1)[0]
        label = clean_text(raw_label) or absolute
        if not is_relevant_link(label, absolute):
            continue
        key = (label, absolute)
        if key in seen:
            continue
        seen.add(key)
        records.append(
            make_record(
                label=label,
                url=absolute,
                topic=infer_topic(label, absolute, page.default_topic),
                resource_kind=resource_type(label, absolute, "msdis_page"),
                source_page=page.url,
                page_key=page.key,
                page_label=page.label,
            )
        )
    return records


def parse_dcat_records(dcat_payload: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for dataset in dcat_payload.get("dataset", []):
        if not isinstance(dataset, dict):
            continue
        title = clean_text(dataset.get("title"))
        if not title:
            continue
        landing_page = clean_text(dataset.get("landingPage") or dataset.get("identifier") or DCAT_URL)
        description = clean_text(dataset.get("description"))
        keywords = dataset.get("keyword") if isinstance(dataset.get("keyword"), list) else []
        distributions = dataset.get("distribution") if isinstance(dataset.get("distribution"), list) else []
        access_urls = []
        for distribution in distributions:
            if not isinstance(distribution, dict):
                continue
            access_url = clean_text(
                distribution.get("accessURL")
                or distribution.get("downloadURL")
                or distribution.get("mediaType")
                or ""
            )
            if access_url.startswith("http"):
                access_urls.append(access_url)
        record_url = access_urls[0] if access_urls else landing_page
        records.append(
            make_record(
                label=title,
                url=record_url,
                topic=infer_topic(title, f"{record_url} {' '.join(str(item) for item in keywords)}", "open data catalog"),
                resource_kind=resource_type(title, record_url, "open_data_dataset"),
                source_page=DCAT_URL,
                page_key="open_data_dcat",
                page_label="MSDIS Open Data DCAT feed",
                description=description,
                keywords=[str(item) for item in keywords],
            )
        )
    return records


def parse_arcgis_services(root: ArcgisRoot, payload: dict[str, Any], source_page: str | None = None) -> list[dict[str, Any]]:
    page_url = source_page or root.url
    records: list[dict[str, Any]] = []
    for service in payload.get("services", []):
        if not isinstance(service, dict):
            continue
        name = clean_text(service.get("name"))
        service_type = clean_text(service.get("type"))
        if not name or not service_type:
            continue
        url = service_url(root.url, service)
        label = f"{name} ({service_type})"
        records.append(
            make_record(
                label=label,
                url=url,
                topic=infer_topic(name, url, root.default_topic),
                resource_kind=resource_type(label, url, "arcgis_service"),
                source_page=page_url,
                page_key=root.key,
                page_label=root.label,
                keywords=[service_type],
            )
        )
    return records


def fetch_json(url: str, timeout: int = 30) -> tuple[dict[str, Any], str]:
    response = requests.get(url, timeout=timeout, headers={"User-Agent": "missouri-tiny-llm-case-study/1.0"})
    response.raise_for_status()
    return response.json(), response.text


def build_msdis_geospatial_index(force: bool = False, delay_seconds: float = 0.03) -> dict[str, Any]:
    if INDEX_PATH.exists() and not force:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))

    session = requests.Session()
    session.headers.update({"User-Agent": "missouri-tiny-llm-case-study/1.0"})
    records: list[dict[str, Any]] = []
    pages: list[dict[str, Any]] = []

    for page in HTML_PAGES:
        response = session.get(page.url, timeout=30)
        response.raise_for_status()
        page_records = parse_html_links(page, response.text)
        records.extend(page_records)
        pages.append(
            {
                "key": page.key,
                "label": page.label,
                "url": page.url,
                "bytes": len(response.text.encode("utf-8")),
                "sha256": sha256_text(response.text),
                "resource_count": len(page_records),
            }
        )
        time.sleep(delay_seconds)

    dcat_payload, dcat_text = fetch_json(DCAT_URL)
    dcat_records = parse_dcat_records(dcat_payload)
    records.extend(dcat_records)
    pages.append(
        {
            "key": "open_data_dcat",
            "label": "MSDIS Open Data DCAT feed",
            "url": DCAT_URL,
            "bytes": len(dcat_text.encode("utf-8")),
            "sha256": sha256_text(dcat_text),
            "resource_count": len(dcat_records),
        }
    )
    time.sleep(delay_seconds)

    for root in ARCGIS_ROOTS:
        payload, text = fetch_json(root.url)
        root_records = parse_arcgis_services(root, payload)
        records.extend(root_records)
        page_count = len(root_records)
        pages.append(
            {
                "key": root.key,
                "label": root.label,
                "url": root.url,
                "bytes": len(text.encode("utf-8")),
                "sha256": sha256_text(text),
                "resource_count": len(root_records),
            }
        )
        if root.recurse_folders:
            folders = [str(folder).strip("/") for folder in payload.get("folders", []) if str(folder).strip("/")]
            for folder in folders:
                if folder.lower() == "utilities":
                    continue
                folder_url = f"{rest_base(root.url)}/{folder}?f=pjson"
                folder_payload, folder_text = fetch_json(folder_url)
                folder_records = parse_arcgis_services(root, folder_payload, folder_url)
                records.extend(folder_records)
                page_count += len(folder_records)
                pages.append(
                    {
                        "key": f"{root.key}:{folder}",
                        "label": f"{root.label}: {folder}",
                        "url": folder_url,
                        "bytes": len(folder_text.encode("utf-8")),
                        "sha256": sha256_text(folder_text),
                        "resource_count": len(folder_records),
                    }
                )
                time.sleep(delay_seconds)
        time.sleep(delay_seconds)

    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for record in records:
        key = (record["label"], record["url"])
        deduped.setdefault(key, record)
    records = sorted(deduped.values(), key=lambda item: (item["topic"], item["label"], item["url"]))

    topic_counts = Counter(str(record.get("topic", "")) for record in records)
    type_counts = Counter(str(record.get("resource_type", "")) for record in records)
    host_counts = Counter(str(record.get("source_host", "")) for record in records)
    payload = {
        "source": SOURCE_NAME,
        "generated_at_utc": utc_now(),
        "record_count": len(records),
        "page_count": len(pages),
        "pages": pages,
        "top_topics": [{"label": label, "count": count} for label, count in topic_counts.most_common(12)],
        "resource_type_counts": dict(sorted(type_counts.items())),
        "top_hosts": [{"label": label, "count": count} for label, count in host_counts.most_common(12)],
        "sanitization_note": (
            "This index stores public MSDIS metadata and service links only. It does not download vector layers, "
            "imagery tiles, LiDAR point clouds, shapefiles, or geodatabases."
        ),
        "records": records,
    }
    write_json(INDEX_PATH, payload)
    write_json(REPORT_PATH, {key: value for key, value in payload.items() if key != "records"})
    return payload


def topic_terms(question: str) -> set[str]:
    lowered = question.lower()
    topics: set[str] = set()
    if any(term in lowered for term in ["lidar", "elevation", "dem", "hillshade"]):
        topics.add("LiDAR/elevation")
    if any(term in lowered for term in ["imagery", "aerial", "photo", "orthophoto"]):
        topics.add("imagery")
    if any(term in lowered for term in ["boundary", "boundaries", "county", "municipal", "city limit", "district"]):
        topics.add("boundaries/administrative")
    if any(term in lowered for term in ["transportation", "road", "route", "rail", "airport"]):
        topics.add("transportation")
    if any(term in lowered for term in ["hydro", "water", "stream", "river", "lake", "flood", "wetland"]):
        topics.add("hydrography/water")
    if any(term in lowered for term in ["environment", "conservation", "land cover", "soil", "geology"]):
        topics.add("environment/conservation")
    if any(term in lowered for term in ["parcel", "cadastral"]):
        topics.add("parcels/cadastral")
    if any(term in lowered for term in ["demographic", "census", "population"]):
        topics.add("demographics/economy")
    if any(term in lowered for term in ["arcgis", "rest", "web service", "feature service", "map service", "image service"]):
        topics.add("ArcGIS/web services")
    if any(term in lowered for term in ["archive", "data library", "vector"]):
        topics.add("archive/data library")
    return topics


def resource_type_terms(question: str) -> set[str]:
    lowered = question.lower()
    terms: set[str] = set()
    if "feature service" in lowered:
        terms.add("feature_service")
    if "map service" in lowered:
        terms.add("map_service")
    if "image service" in lowered:
        terms.add("image_service")
    if any(term in lowered for term in ["rest", "web service", "services"]):
        terms.add("web_service_directory")
    if any(term in lowered for term in ["open data", "dataset", "datasets", "catalog"]):
        terms.add("open_data_dataset")
    if any(term in lowered for term in ["archive", "data library"]):
        terms.add("archive_directory")
    return terms


def asks_for_summary(question: str) -> bool:
    lowered = question.lower()
    return any(
        term in lowered
        for term in ["indexed", "available", "coverage", "what data", "what resources", "what links", "what msdis", "what gis", "what datasets"]
    )


class MsdisGeospatialIndex:
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
                "category": "Geospatial",
                "kind": "MSDIS public-resource metadata",
                "lookup_table": "msdis_geospatial_index",
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
                "The MSDIS geospatial resource metadata index has not been built yet. Run "
                "`python scripts/build_msdis_geospatial_index.py --force` to index official MSDIS geospatial resource links."
            ),
            "retrieved_context_id": "msdis_geospatial_index:missing",
            "retrieved_source": "msdis_geospatial_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "The MSDIS route exists, but the local ignored index is missing.",
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
                "The MSDIS geospatial resource metadata layer indexes official Missouri Spatial Data Information Service links from "
                f"{payload.get('page_count', 0)} source page/feed/service endpoint(s). It contains {payload.get('record_count', 0):,} resource link(s). "
                f"Top topics: {topics}. Resource types: {resource_types}. "
                "It can return cited links for the MSDIS Open Data portal, ArcGIS REST feature services, map/image services, county boundaries, imagery, LiDAR/elevation, archive directories, and vector GIS resources. "
                "It is metadata only, not a downloader for GIS layers, imagery, LiDAR, or geodatabases."
            ),
            "retrieved_context_id": "msdis_geospatial_index:summary",
            "retrieved_source": "msdis_geospatial_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local MSDIS geospatial resource metadata index.",
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
                f"The MSDIS geospatial resource metadata layer has {len(rows):,} indexed link(s) for this topic request. "
                f"Topic counts: {topic_text}. Resource types: {type_text}. Examples: {examples}. "
                "These are source links and metadata, not downloaded GIS data values."
            ),
            "retrieved_context_id": "msdis_geospatial_index:topic_summary",
            "retrieved_source": "msdis_geospatial_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local MSDIS geospatial resource metadata index.",
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
                blob = " ".join(
                    str(record.get(key, ""))
                    for key in ["label", "topic", "resource_type", "description", "keywords", "page_label", "year_label"]
                )
                tokens = query_tokens(blob)
                score = len(q_tokens & tokens)
                label_norm = normalize_text(record.get("label", ""))
                url_lowered = str(record.get("url", "")).lower()
                if label_norm and label_norm in question_norm:
                    score += 25
                if "COUNTY" in question_norm and any(term in url_lowered for term in ["county", "boundar"]):
                    score += 10
                if "BOUND" in question_norm and any(term in url_lowered for term in ["bound", "county"]):
                    score += 10
                if "LIDAR" in question_norm and "lidar" in url_lowered:
                    score += 10
                if "IMAGERY" in question_norm and "imagery" in url_lowered:
                    score += 10
                if "ARCGIS" in question_norm and "arcgis" in url_lowered:
                    score += 8
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
            "answer": f"Showing {len(preview)} of {matched_count} matching MSDIS geospatial resource metadata row(s): {rendered}.",
            "retrieved_context_id": "msdis_geospatial_index:match",
            "retrieved_source": "msdis_geospatial_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local MSDIS geospatial resource metadata index.",
            "citations": self.citation(matched_rows=matched_count),
            "source_rows": [{"source_file": row["source_page"], "values": row} for row in source_preview],
        }

    def missing_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "I have indexed MSDIS geospatial resource metadata, but this question did not match a supported topic, resource label, or year. "
                "Try `What MSDIS geospatial resources are indexed?`, `What MSDIS GIS links are indexed?`, "
                "`List MSDIS geospatial datasets with county boundary coverage`, or `Give me MSDIS LiDAR links`."
            ),
            "retrieved_context_id": "msdis_geospatial_index:no_match",
            "retrieved_source": "msdis_geospatial_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Answered from MSDIS resource coverage metadata because no exact resource row matched.",
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
    payload = build_msdis_geospatial_index(force=args.force, delay_seconds=args.delay_seconds)
    print(json.dumps({key: value for key, value in payload.items() if key != "records"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
