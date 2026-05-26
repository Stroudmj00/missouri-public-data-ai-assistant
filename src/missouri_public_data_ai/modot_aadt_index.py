"""Build and query selected MoDOT AADT traffic-volume records."""

from __future__ import annotations

import argparse
import json
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw_public" / "modot_aadt"
INDEX_PATH = RAW_DIR / "modot_aadt_index.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "modot_aadt_index_report.json"
SERVICE_URL = "https://mapping.modot.mo.gov/arcgis/rest/services/BusinessInt/TrafficInfoSegAADT/MapServer"
SOURCE_PAGE = "https://www.modot.org/modatazone/traffic"
TRAFFIC_VOLUME_PAGE = "https://www.modot.org/traffic-volume-maps"
APP_PAGE = "https://datazoneapps.modot.mo.gov/bi/apps/publicmaps/Home/Index/AADT"

FIELDS = [
    "SS_SEGMENT_ID",
    "YEAR",
    "TRF_INFO_SEG_ID",
    "TRF_INFO_SEG_DESC",
    "TRAVELWAY_DESG",
    "TRAVELWAY_NAME",
    "TRAVELWAY_DIR",
    "BEG_CONTINUOUS_LOG",
    "END_CONTINUOUS_LOG",
    "AREA_DESG_NAME",
    "NUMBER_OF_LANES",
    "AADT",
    "PERCENT_COMMERCIAL",
    "STATE_SYSTEM_CLASS",
    "PLANNING_CATEGORY",
    "FUNC_CLASS_NAME",
    "ROADWAY_TYPE_NAME",
    "CONGESTION_INDEX",
    "SAFETY_INDEX",
    "CNGST_INDEX_RATING",
    "SFTY_INDEX_RATING",
    "PLANNING_ORG",
    "PLANNING_ORG_TYPE",
    "AREA_ENGINEER",
    "SPEED_LIMIT",
]

DIRECTION_LAYERS = {
    1: "North",
    2: "South",
    3: "East",
    4: "West",
}
DIRECTION_CODES = {"North": "N", "South": "S", "East": "E", "West": "W"}
DESIGNATION_LABELS = {"IS": "I", "US": "US", "MO": "MO"}
GENERIC_QUERY_TOKENS = {
    "aadt",
    "annual",
    "average",
    "daily",
    "traffic",
    "volume",
    "volumes",
    "modot",
    "missouri",
    "route",
    "rte",
    "highway",
    "interstate",
    "east",
    "eastbound",
    "west",
    "westbound",
    "north",
    "northbound",
    "south",
    "southbound",
    "direction",
    "segment",
    "segments",
    "latest",
    "highest",
    "busiest",
    "top",
    "near",
    "around",
    "at",
    "between",
    "show",
    "what",
    "which",
    "how",
    "many",
    "count",
    "indexed",
    "data",
    "lookup",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_text(value: str) -> str:
    cleaned = re.sub(r"[^A-Z0-9]+", " ", clean_text(value).upper())
    return re.sub(r"\s+", " ", cleaned).strip()


def query_tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[A-Z0-9]+", normalize_text(value))
        if len(token) > 1 and token.lower() not in GENERIC_QUERY_TOKENS
    }


def number_value(value: Any) -> int | float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number.is_integer():
        return int(number)
    return round(number, 4)


def route_label(designation: str, name: str) -> str:
    prefix = DESIGNATION_LABELS.get(clean_text(designation).upper(), clean_text(designation).upper())
    route = clean_text(name).upper()
    if prefix == "I":
        return f"I-{route}"
    return f"{prefix} {route}".strip()


def route_key(designation: str, name: str) -> str:
    return f"{clean_text(designation).upper()}:{clean_text(name).upper()}"


def normalize_record(attributes: dict[str, Any], layer_id: int, layer_name: str) -> dict[str, Any]:
    designation = clean_text(attributes.get("TRAVELWAY_DESG")).upper()
    name = clean_text(attributes.get("TRAVELWAY_NAME")).upper()
    desc = clean_text(attributes.get("TRF_INFO_SEG_DESC"))
    direction = clean_text(attributes.get("TRAVELWAY_DIR") or DIRECTION_CODES[layer_name]).upper()
    record = {
        "segment_id": attributes.get("SS_SEGMENT_ID"),
        "traffic_segment_id": attributes.get("TRF_INFO_SEG_ID"),
        "year": attributes.get("YEAR"),
        "layer_id": layer_id,
        "layer_name": f"AADT {layer_name}",
        "direction": direction,
        "route_designation": designation,
        "route_name": name,
        "route_key": route_key(designation, name),
        "route_label": route_label(designation, name),
        "segment_description": desc,
        "begin_log_mile": number_value(attributes.get("BEG_CONTINUOUS_LOG")),
        "end_log_mile": number_value(attributes.get("END_CONTINUOUS_LOG")),
        "area": clean_text(attributes.get("AREA_DESG_NAME")),
        "lanes": number_value(attributes.get("NUMBER_OF_LANES")),
        "aadt": number_value(attributes.get("AADT")),
        "percent_commercial": number_value(attributes.get("PERCENT_COMMERCIAL")),
        "state_system_class": clean_text(attributes.get("STATE_SYSTEM_CLASS")),
        "planning_category": clean_text(attributes.get("PLANNING_CATEGORY")),
        "functional_class": clean_text(attributes.get("FUNC_CLASS_NAME")),
        "roadway_type": clean_text(attributes.get("ROADWAY_TYPE_NAME")),
        "congestion_index": number_value(attributes.get("CONGESTION_INDEX")),
        "safety_index": number_value(attributes.get("SAFETY_INDEX")),
        "congestion_rating": clean_text(attributes.get("CNGST_INDEX_RATING")),
        "safety_rating": clean_text(attributes.get("SFTY_INDEX_RATING")),
        "planning_org": clean_text(attributes.get("PLANNING_ORG")),
        "planning_org_type": clean_text(attributes.get("PLANNING_ORG_TYPE")),
        "area_engineer": clean_text(attributes.get("AREA_ENGINEER")),
        "speed_limit": number_value(attributes.get("SPEED_LIMIT")),
        "source_url": f"{SERVICE_URL}/{layer_id}",
    }
    record["search_text"] = normalize_text(
        " ".join(
            [
                record["route_label"],
                record["segment_description"],
                record["area"],
                record["state_system_class"],
                record["planning_org"],
                record["area_engineer"],
                record["roadway_type"],
                record["functional_class"],
            ]
        )
    )
    return record


def arcgis_get(session: requests.Session, url: str, params: dict[str, Any]) -> dict[str, Any]:
    response = session.get(url, params=params, timeout=90)
    response.raise_for_status()
    payload = response.json()
    if "error" in payload:
        raise RuntimeError(payload["error"])
    return payload


def latest_year(session: requests.Session) -> int:
    payload = arcgis_get(
        session,
        f"{SERVICE_URL}/1/query",
        {
            "where": "1=1",
            "outFields": "YEAR",
            "returnDistinctValues": "true",
            "returnGeometry": "false",
            "orderByFields": "YEAR DESC",
            "f": "json",
        },
    )
    years = [int(item["attributes"]["YEAR"]) for item in payload.get("features", []) if item.get("attributes", {}).get("YEAR")]
    if not years:
        raise RuntimeError("MoDOT AADT service did not return any years")
    return max(years)


def fetch_layer_records(session: requests.Session, layer_id: int, layer_name: str, year: int) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    offset = 0
    page_size = 2000
    query_url = f"{SERVICE_URL}/{layer_id}/query"
    while True:
        payload = arcgis_get(
            session,
            query_url,
            {
                "where": f"YEAR={year}",
                "outFields": ",".join(FIELDS),
                "returnGeometry": "false",
                "orderByFields": "SS_SEGMENT_ID",
                "resultOffset": offset,
                "resultRecordCount": page_size,
                "f": "json",
            },
        )
        features = payload.get("features", [])
        if not features:
            break
        records.extend(normalize_record(item.get("attributes", {}), layer_id, layer_name) for item in features)
        if len(features) < page_size:
            break
        offset += page_size
    return records


def build_modot_aadt_index(force: bool = False, delay_seconds: float = 0.03) -> dict[str, Any]:
    if INDEX_PATH.exists() and not force:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (compatible; MissouriPublicDataAssistant/1.0)",
            "Accept": "application/json,*/*;q=0.8",
        }
    )
    start = time.perf_counter()
    year = latest_year(session)
    all_records: list[dict[str, Any]] = []
    layer_summaries: list[dict[str, Any]] = []
    for layer_id, layer_name in DIRECTION_LAYERS.items():
        records = fetch_layer_records(session, layer_id, layer_name, year)
        all_records.extend(records)
        layer_summaries.append(
            {
                "layer_id": layer_id,
                "layer_name": f"AADT {layer_name}",
                "direction": DIRECTION_CODES[layer_name],
                "record_count": len(records),
                "source_url": f"{SERVICE_URL}/{layer_id}",
            }
        )
        if delay_seconds > 0:
            time.sleep(delay_seconds)

    route_counts = Counter(record["route_label"] for record in all_records if record.get("route_label"))
    top_routes_by_count = [
        {"route": route, "segment_direction_records": count}
        for route, count in sorted(route_counts.items(), key=lambda item: (-item[1], item[0]))[:12]
    ]
    top_aadt = sorted(all_records, key=lambda item: (item.get("aadt") or -1), reverse=True)[:12]
    payload = {
        "generated_at_utc": utc_now(),
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "source": "MoDOT TrafficInfoSegAADT ArcGIS service",
        "source_url": SERVICE_URL,
        "source_page": SOURCE_PAGE,
        "traffic_volume_page": TRAFFIC_VOLUME_PAGE,
        "app_page": APP_PAGE,
        "index_path": str(INDEX_PATH.relative_to(PROJECT_ROOT)),
        "latest_year": year,
        "layer_count": len(layer_summaries),
        "record_count": len(all_records),
        "route_count": len(route_counts),
        "layers": layer_summaries,
        "top_routes_by_count": top_routes_by_count,
        "top_aadt_segments": top_aadt,
        "notes": [
            "This index stores latest-year directional AADT segment attributes from the official MoDOT ArcGIS REST service.",
            "Geometry is not stored in the public report; the local ignored index stores selected non-person traffic attributes only.",
            "Location matching is route/segment-text based and does not geocode addresses.",
        ],
        "records": all_records,
    }
    write_json(INDEX_PATH, payload)
    report = {key: value for key, value in payload.items() if key != "records"}
    write_json(REPORT_PATH, report)
    return payload


def direction_from_question(question: str) -> str | None:
    lowered = question.lower()
    checks = [
        ("N", [r"\bnorthbound\b", r"\bnb\b", r"\bnorth\s+direction\b"]),
        ("S", [r"\bsouthbound\b", r"\bsb\b", r"\bsouth\s+direction\b"]),
        ("E", [r"\beastbound\b", r"\beb\b", r"\beast\s+direction\b"]),
        ("W", [r"\bwestbound\b", r"\bwb\b", r"\bwest\s+direction\b"]),
    ]
    for code, patterns in checks:
        if any(re.search(pattern, lowered) for pattern in patterns):
            return code
    return None


def route_from_question(question: str, valid_routes: set[str]) -> tuple[str, str] | None:
    upper = question.upper()
    explicit_patterns = [
        (r"\b(?:I|IS|INTERSTATE)[-\s]*(\d{1,3})\b", "IS"),
        (r"\b(?:US|U\.S\.|U S|UNITED STATES|US ROUTE)[-\s]*(\d{1,3})\b", "US"),
        (r"\b(?:MO|MISSOURI)[-\s]*(\d{1,3})\b", "MO"),
    ]
    for pattern, designation in explicit_patterns:
        match = re.search(pattern, upper)
        if match:
            key = route_key(designation, match.group(1))
            if key in valid_routes:
                return key, route_label(designation, match.group(1))
    generic = re.search(r"\b(?:ROUTE|RTE|RT|HIGHWAY|HWY)[-\s]*(\d{1,3})\b", upper)
    if generic:
        number = generic.group(1)
        for designation in ["US", "MO", "IS"]:
            key = route_key(designation, number)
            if key in valid_routes:
                return key, route_label(designation, number)
    return None


def asks_for_summary(question: str) -> bool:
    lowered = question.lower()
    return bool(re.search(r"\b(modot|aadt|traffic\s+volume|traffic\s+count)\b.*\b(indexed|lookup|data)\b", lowered))


def asks_for_top(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["highest", "largest", "busiest", "top", "most traffic"])


def aadt_label(value: Any) -> str:
    if value is None:
        return "unknown AADT"
    return f"{int(round(float(value))):,} AADT"


def percent_label(value: Any) -> str:
    if value is None:
        return "unknown commercial share"
    return f"{float(value) * 100:.1f}% commercial"


class ModotAadtIndex:
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

    def valid_routes(self) -> set[str]:
        return {record["route_key"] for record in self.records()}

    def citation(self, matched_rows: int = 0) -> list[dict[str, Any]]:
        payload = self.payload()
        return [
            {
                "dataset": payload.get("source", "MoDOT TrafficInfoSegAADT ArcGIS service"),
                "category": "MoDOT AADT",
                "kind": "latest-year directional AADT segment lookup",
                "lookup_table": "modot_aadt_index",
                "year": payload.get("latest_year"),
                "year_range": None,
                "source_files": [
                    {
                        "category": "modot_arcgis_service",
                        "category_label": "TrafficInfoSegAADT ArcGIS service",
                        "file_name": payload.get("source_url", SERVICE_URL),
                        "row_count": payload.get("record_count"),
                        "bytes": None,
                        "sha256": None,
                    },
                    {
                        "category": "modot_traffic_page",
                        "category_label": "MoDOT Traffic Toolbox",
                        "file_name": payload.get("source_page", SOURCE_PAGE),
                        "row_count": None,
                        "bytes": None,
                        "sha256": None,
                    },
                    {
                        "category": "modot_aadt_app",
                        "category_label": "Average Annual Daily Traffic Map",
                        "file_name": payload.get("app_page", APP_PAGE),
                        "row_count": None,
                        "bytes": None,
                        "sha256": None,
                    },
                ],
                "source_file_count": 3,
                "source_rows": payload.get("record_count"),
                "matched_rows": matched_rows,
            }
        ]

    def unavailable_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "The MoDOT AADT lookup index has not been built yet. Run "
                "`python scripts/build_modot_aadt_index.py --force` to index the latest public TrafficInfoSegAADT route segments."
            ),
            "retrieved_context_id": "modot_aadt_index:missing",
            "retrieved_source": "modot_aadt_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "The MoDOT AADT route exists, but the local ignored index is missing.",
            "citations": [],
            "source_rows": [],
        }

    def summary_answer(self, question: str) -> dict[str, Any]:
        payload = self.payload()
        layers = ", ".join(f"{item['layer_name']} ({item['record_count']:,})" for item in payload.get("layers", []))
        top = "; ".join(
            f"{item['route']} ({item['segment_direction_records']:,})"
            for item in payload.get("top_routes_by_count", [])[:5]
        )
        return {
            "question": question,
            "answer": (
                f"The MoDOT AADT exact lookup layer indexes {payload.get('record_count', 0):,} latest-year "
                f"directional segment record(s) for {payload.get('latest_year')} from the official TrafficInfoSegAADT "
                f"ArcGIS service. It covers {payload.get('route_count', 0):,} route(s) across {payload.get('layer_count', 0)} "
                f"directional layers: {layers}. It can answer route-level AADT questions, highest-AADT segment questions, "
                f"direction filters, and segment-text searches. Largest route groups by record count: {top}."
            ),
            "retrieved_context_id": "modot_aadt_index:summary",
            "retrieved_source": "modot_aadt_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local MoDOT AADT latest-year index.",
            "citations": self.citation(matched_rows=payload.get("record_count", 0)),
            "source_rows": [],
        }

    def render_records(self, records: list[dict[str, Any]], lead: str) -> str:
        rendered: list[str] = []
        for index, record in enumerate(records[:5], start=1):
            desc = record.get("segment_description") or "segment"
            miles = f"log mile {record.get('begin_log_mile')} to {record.get('end_log_mile')}"
            commercial = f", {percent_label(record.get('percent_commercial'))}" if record.get("percent_commercial") is not None else ""
            lanes = f", {record.get('lanes')} lane(s)" if record.get("lanes") is not None else ""
            rendered.append(
                f"{index}. {record['route_label']} {record['direction']} near {desc}: "
                f"{aadt_label(record.get('aadt'))} ({miles}{lanes}{commercial})"
            )
        return f"{lead}\n" + "\n".join(rendered)

    def top_answer(self, question: str, records: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        pool = records if records is not None else self.records()
        ranked = sorted(pool, key=lambda item: (item.get("aadt") or -1), reverse=True)[:5]
        route_text = f" for {ranked[0]['route_label']}" if records is not None and ranked else ""
        lead = f"Highest indexed {self.payload().get('latest_year')} MoDOT AADT segment(s){route_text}:"
        return {
            "question": question,
            "answer": self.render_records(ranked, lead),
            "retrieved_context_id": "modot_aadt_index:top",
            "retrieved_source": "modot_aadt_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed by ranking latest-year directional AADT segment records in the local MoDOT AADT index.",
            "citations": self.citation(matched_rows=len(pool)),
            "source_rows": [{"source_file": record["source_url"], "values": record} for record in ranked],
        }

    def route_records(self, route: str, direction: str | None = None) -> list[dict[str, Any]]:
        rows = [record for record in self.records() if record.get("route_key") == route]
        if direction:
            rows = [record for record in rows if record.get("direction") == direction]
        return rows

    def score_record(self, record: dict[str, Any], question: str) -> int:
        tokens = query_tokens(question)
        record_tokens = query_tokens(record.get("search_text", ""))
        score = len(tokens & record_tokens) * 10
        lowered = question.lower()
        desc = record.get("segment_description", "").lower()
        if desc and desc in lowered:
            score += 120
        if record.get("planning_org", "").lower() and record["planning_org"].lower() in lowered:
            score += 60
        if record.get("area_engineer", "").lower() and record["area_engineer"].lower() in lowered:
            score += 40
        return score

    def route_answer(self, question: str, route: str, label: str, direction: str | None = None) -> dict[str, Any]:
        rows = self.route_records(route, direction=direction)
        if not rows:
            return self.missing_answer(question)
        if asks_for_top(question):
            return self.top_answer(question, rows)
        scored = sorted(
            [(self.score_record(record, question), record) for record in rows],
            key=lambda item: (item[0], item[1].get("aadt") or -1),
            reverse=True,
        )
        if scored and scored[0][0] > 0:
            matched = [record for score, record in scored if score == scored[0][0]][:5]
            lead = f"Best matching {self.payload().get('latest_year')} MoDOT AADT segment(s) for {label}:"
        else:
            matched = sorted(rows, key=lambda item: (item.get("aadt") or -1), reverse=True)[:5]
            filter_text = f" {direction}" if direction else ""
            lead = (
                f"I found {len(rows):,} {self.payload().get('latest_year')} MoDOT AADT segment-direction record(s) "
                f"for {label}{filter_text}. Showing the highest-AADT matches:"
            )
        return {
            "question": question,
            "answer": self.render_records(matched, lead),
            "retrieved_context_id": f"modot_aadt_index:route:{route}",
            "retrieved_source": "modot_aadt_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local MoDOT AADT latest-year index.",
            "citations": self.citation(matched_rows=len(rows)),
            "source_rows": [{"source_file": record["source_url"], "values": record} for record in matched],
        }

    def missing_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "I have indexed MoDOT AADT traffic-volume records, but this question did not match a supported route, "
                "direction, or segment phrase. Try `What MoDOT AADT data is indexed?`, "
                "`What is the highest AADT on I-70 eastbound?`, or `Show MoDOT AADT for MO 163 near Stadium Blvd.`"
            ),
            "retrieved_context_id": "modot_aadt_index:no_match",
            "retrieved_source": "modot_aadt_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Answered from MoDOT AADT coverage metadata because no exact route record matched.",
            "citations": self.citation(),
            "source_rows": [],
        }

    def answer(self, question: str) -> dict[str, Any] | None:
        if not self.available():
            return self.unavailable_answer(question)
        if asks_for_summary(question) and not asks_for_top(question):
            route = route_from_question(question, self.valid_routes())
            if route is None:
                return self.summary_answer(question)
        route = route_from_question(question, self.valid_routes())
        direction = direction_from_question(question)
        if route:
            return self.route_answer(question, route[0], route[1], direction=direction)
        if asks_for_top(question):
            return self.top_answer(question)
        return self.missing_answer(question)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--delay-seconds", type=float, default=0.03)
    args = parser.parse_args()
    payload = build_modot_aadt_index(force=args.force, delay_seconds=args.delay_seconds)
    print(json.dumps({key: value for key, value in payload.items() if key != "records"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
