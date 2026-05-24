"""Verify required artifacts for the Missouri Tiny LLM case study."""

from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "README.md",
    "LICENSE",
    "requirements.txt",
    "configs/finetune_smollm2_135m_lora.yaml",
    "data/processed/public_data_summary.json",
    "data/qa/train.jsonl",
    "data/qa/eval.jsonl",
    "data/eval/evaluation_prompts.jsonl",
    "docs/CASE_STUDY.md",
    "docs/DATA_CARD.md",
    "docs/DATA_SAFETY.md",
    "docs/EVALUATION.md",
    "docs/LIMITATIONS.md",
    "docs/MODEL_CARD.md",
    "docs/PORTFOLIO_SUMMARY.md",
    "docs/ROADMAP.md",
    "reports/baseline_inference_report.md",
    "reports/training_preflight_001.json",
    "reports/training_run_001.md",
    "reports/training_run_001_metrics.csv",
    "reports/training_run_001_loss.png",
    "reports/training_run_001_summary.json",
    "reports/evaluation_comparison.md",
    "reports/evaluation_comparison.csv",
    "reports/evaluation_comparison_summary.json",
    "reports/command_log.md",
    "reports/project_screenshot_plan.md",
    "scripts/build_public_dataset.py",
    "scripts/build_psc_reports_index.py",
    "scripts/build_oa_budget_index.py",
    "scripts/build_ag_market_news_index.py",
    "scripts/build_modot_aadt_index.py",
    "scripts/build_mec_resources_index.py",
    "scripts/build_dnr_resources_index.py",
    "scripts/build_msdis_geospatial_index.py",
    "scripts/build_dese_school_data_index.py",
    "scripts/build_dhss_health_sources_index.py",
    "scripts/run_baseline.py",
    "scripts/finetune_lora.py",
    "scripts/evaluate_comparison.py",
    "scripts/test_chatbot_behavior.py",
    "src/missouri_tiny_llm/ingest_public_data.py",
    "src/missouri_tiny_llm/baseline_inference.py",
    "src/missouri_tiny_llm/finetune.py",
    "src/missouri_tiny_llm/evaluate_comparison.py",
    "src/missouri_tiny_llm/map_public_index.py",
    "src/missouri_tiny_llm/psc_reports_index.py",
    "src/missouri_tiny_llm/oa_budget_index.py",
    "src/missouri_tiny_llm/ag_market_news_index.py",
    "src/missouri_tiny_llm/modot_aadt_index.py",
    "src/missouri_tiny_llm/mec_resources_index.py",
    "src/missouri_tiny_llm/dnr_resources_index.py",
    "src/missouri_tiny_llm/msdis_geospatial_index.py",
    "src/missouri_tiny_llm/dese_school_data_index.py",
    "src/missouri_tiny_llm/dhss_health_sources_index.py",
    "reports/psc_reports_index_report.json",
    "reports/oa_budget_index_report.json",
    "reports/ag_market_news_index_report.json",
    "reports/modot_aadt_index_report.json",
    "reports/mec_resources_index_report.json",
    "reports/dnr_resources_index_report.json",
    "reports/msdis_geospatial_index_report.json",
    "reports/dese_school_data_index_report.json",
    "reports/dhss_health_sources_index_report.json",
]

PUBLIC_OUTPUT_GLOBS = [
    "data/processed/*",
    "data/qa/*",
    "data/eval/*",
    "reports/*.json",
    "reports/*.jsonl",
    "reports/*.csv",
]

FORBIDDEN_RAW_KEYS = [
    '"vendor_name"',
    '"Vendor Name"',
    '"administrator_full_name"',
    '"administrator full name"',
    '"address"',
    '"phone"',
    '"fax"',
    '"employee_name"',
    '"Employee Name"',
]


def read_jsonl_count(path: Path) -> int:
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def main() -> None:
    failures: list[str] = []

    for rel_path in REQUIRED_FILES:
        path = PROJECT_ROOT / rel_path
        if not path.exists() or path.stat().st_size == 0:
            failures.append(f"missing or empty required file: {rel_path}")

    train_count = read_jsonl_count(PROJECT_ROOT / "data/qa/train.jsonl")
    eval_count = read_jsonl_count(PROJECT_ROOT / "data/qa/eval.jsonl")
    prompt_count = read_jsonl_count(PROJECT_ROOT / "data/eval/evaluation_prompts.jsonl")
    if train_count != 100:
        failures.append(f"expected 100 training rows, found {train_count}")
    if eval_count != 20:
        failures.append(f"expected 20 eval rows, found {eval_count}")
    if prompt_count != 20:
        failures.append(f"expected 20 evaluation prompts, found {prompt_count}")

    training = json.loads((PROJECT_ROOT / "reports/training_run_001_summary.json").read_text(encoding="utf-8"))
    if training.get("max_steps") != 120:
        failures.append("training_run_001_summary.json does not show 120 max steps")
    if float(training.get("peak_allocated_vram_mb", 999999)) > 6500:
        failures.append("training peak VRAM exceeded configured stop limit")
    adapter_dir = PROJECT_ROOT / training.get("adapter_dir", "")
    adapter_note = "present"
    if not adapter_dir.exists():
        adapter_note = "missing as expected in a clean clone; checkpoints are ignored by Git"

    comparison = json.loads((PROJECT_ROOT / "reports/evaluation_comparison_summary.json").read_text(encoding="utf-8"))
    if comparison.get("prompt_count") != 20:
        failures.append("evaluation comparison did not use 20 prompts")
    if comparison.get("base", {}).get("passed_count") != 18:
        failures.append("expected base passed_count 18")
    if comparison.get("fine_tuned", {}).get("passed_count") != 18:
        failures.append("expected fine_tuned passed_count 18")

    map_index_report = PROJECT_ROOT / "reports/map_public_index_report.json"
    if map_index_report.exists():
        map_index = json.loads(map_index_report.read_text(encoding="utf-8"))
        if map_index.get("file_count", 0) < 100:
            failures.append("MAP public index covers fewer than 100 text files")
        if map_index.get("agency_vendor_lookup_rows", 0) < 1:
            failures.append("MAP agency-vendor lookup table is missing")
    else:
        failures.append("missing reports/map_public_index_report.json")

    oa_budget_report = PROJECT_ROOT / "reports/oa_budget_index_report.json"
    if oa_budget_report.exists():
        oa_budget = json.loads(oa_budget_report.read_text(encoding="utf-8"))
        if oa_budget.get("record_count", 0) < 100:
            failures.append("OA Budget metadata index covers fewer than 100 link records")
        if oa_budget.get("page_count") != 5:
            failures.append("OA Budget metadata index should cover 5 source pages")
        if "budget_summary" not in oa_budget.get("document_type_counts", {}):
            failures.append("OA Budget metadata index is missing budget-summary records")
        if "revenue_detail" not in oa_budget.get("document_type_counts", {}):
            failures.append("OA Budget metadata index is missing revenue-detail records")
    else:
        failures.append("missing reports/oa_budget_index_report.json")

    ag_market_report = PROJECT_ROOT / "reports/ag_market_news_index_report.json"
    if ag_market_report.exists():
        ag_market = json.loads(ag_market_report.read_text(encoding="utf-8"))
        if ag_market.get("record_count", 0) < 50:
            failures.append("Agricultural Market News index covers fewer than 50 report links")
        if ag_market.get("pdf_count", 0) < 50:
            failures.append("Agricultural Market News index covers fewer than 50 PDF links")
        if "cattle/livestock" not in {item.get("label") for item in ag_market.get("top_commodities", [])}:
            failures.append("Agricultural Market News index is missing cattle/livestock coverage")
        if "swine" not in {item.get("label") for item in ag_market.get("top_commodities", [])}:
            failures.append("Agricultural Market News index is missing swine coverage")
    else:
        failures.append("missing reports/ag_market_news_index_report.json")

    modot_aadt_report = PROJECT_ROOT / "reports/modot_aadt_index_report.json"
    if modot_aadt_report.exists():
        modot_aadt = json.loads(modot_aadt_report.read_text(encoding="utf-8"))
        if modot_aadt.get("record_count", 0) < 10000:
            failures.append("MoDOT AADT index covers fewer than 10,000 segment-direction records")
        if modot_aadt.get("latest_year", 0) < 2025:
            failures.append("MoDOT AADT index latest_year is older than 2025")
        if modot_aadt.get("route_count", 0) < 200:
            failures.append("MoDOT AADT index covers fewer than 200 route groups")
        if modot_aadt.get("layer_count") != 4:
            failures.append("MoDOT AADT index should cover 4 directional layers")
        top_blob = json.dumps(modot_aadt.get("top_aadt_segments", []), sort_keys=True)
        if "I-270" not in top_blob or "BIG BEND BLVD" not in top_blob:
            failures.append("MoDOT AADT index top segments should include I-270 near BIG BEND BLVD")
    else:
        failures.append("missing reports/modot_aadt_index_report.json")

    dese_school_data_report = PROJECT_ROOT / "reports/dese_school_data_index_report.json"
    if dese_school_data_report.exists():
        dese_school_data = json.loads(dese_school_data_report.read_text(encoding="utf-8"))
        if dese_school_data.get("record_count", 0) < 250:
            failures.append("DESE School Data resource metadata index covers fewer than 250 links")
        if dese_school_data.get("page_count", 0) < 6:
            failures.append("DESE School Data resource metadata index covers fewer than 6 source pages")
        topics = {item.get("label") for item in dese_school_data.get("top_topics", [])}
        for required_topic in ["accountability", "school finance", "code sets", "file layouts"]:
            if required_topic not in topics:
                failures.append(f"DESE School Data resource metadata index is missing {required_topic} coverage")
    else:
        failures.append("missing reports/dese_school_data_index_report.json")

    dhss_health_sources_report = PROJECT_ROOT / "reports/dhss_health_sources_index_report.json"
    if dhss_health_sources_report.exists():
        dhss_health_sources = json.loads(dhss_health_sources_report.read_text(encoding="utf-8"))
        if dhss_health_sources.get("record_count", 0) < 250:
            failures.append("DHSS health resource metadata index covers fewer than 250 links")
        if dhss_health_sources.get("page_count", 0) < 8:
            failures.append("DHSS health resource metadata index covers fewer than 8 source pages")
        topics = {item.get("label") for item in dhss_health_sources.get("top_topics", [])}
        for required_topic in ["county profiles", "BRFSS", "hospitalizations/PAS", "births/vital statistics", "deaths/vital statistics"]:
            if required_topic not in topics:
                failures.append(f"DHSS health resource metadata index is missing {required_topic} coverage")
    else:
        failures.append("missing reports/dhss_health_sources_index_report.json")

    mec_resources_report = PROJECT_ROOT / "reports/mec_resources_index_report.json"
    if mec_resources_report.exists():
        mec_resources = json.loads(mec_resources_report.read_text(encoding="utf-8"))
        if mec_resources.get("record_count", 0) < 125:
            failures.append("MEC public-resource metadata index covers fewer than 125 links")
        if mec_resources.get("page_count", 0) < 10:
            failures.append("MEC public-resource metadata index covers fewer than 10 source pages")
        if mec_resources.get("resource_type_counts", {}).get("search_page", 0) < 25:
            failures.append("MEC public-resource metadata index covers fewer than 25 search pages")
        topics = {item.get("label") for item in mec_resources.get("top_topics", [])}
        for required_topic in ["campaign finance searches", "lobbying", "financial disclosure/PFD", "annual reports"]:
            if required_topic not in topics:
                failures.append(f"MEC public-resource metadata index is missing {required_topic} coverage")
    else:
        failures.append("missing reports/mec_resources_index_report.json")

    dnr_resources_report = PROJECT_ROOT / "reports/dnr_resources_index_report.json"
    if dnr_resources_report.exists():
        dnr_resources = json.loads(dnr_resources_report.read_text(encoding="utf-8"))
        if dnr_resources.get("record_count", 0) < 200:
            failures.append("DNR data/e-services resource metadata index covers fewer than 200 links")
        if dnr_resources.get("page_count", 0) < 8:
            failures.append("DNR data/e-services resource metadata index covers fewer than 8 source pages")
        if dnr_resources.get("resource_type_counts", {}).get("search_or_data_system", 0) < 40:
            failures.append("DNR data/e-services resource metadata index covers fewer than 40 search/data systems")
        if dnr_resources.get("resource_type_counts", {}).get("map_or_gis", 0) < 20:
            failures.append("DNR data/e-services resource metadata index covers fewer than 20 map/GIS resources")
        topics = {item.get("label") for item in dnr_resources.get("top_topics", [])}
        for required_topic in ["air quality/emissions", "impaired waters/water quality", "land/geology/GIS", "water permits/wastewater/stormwater"]:
            if required_topic not in topics:
                failures.append(f"DNR data/e-services resource metadata index is missing {required_topic} coverage")
    else:
        failures.append("missing reports/dnr_resources_index_report.json")

    msdis_geospatial_report = PROJECT_ROOT / "reports/msdis_geospatial_index_report.json"
    if msdis_geospatial_report.exists():
        msdis_geospatial = json.loads(msdis_geospatial_report.read_text(encoding="utf-8"))
        if msdis_geospatial.get("record_count", 0) < 400:
            failures.append("MSDIS geospatial resource metadata index covers fewer than 400 links")
        if msdis_geospatial.get("page_count", 0) < 8:
            failures.append("MSDIS geospatial resource metadata index covers fewer than 8 source pages/endpoints")
        if msdis_geospatial.get("resource_type_counts", {}).get("feature_service", 0) < 150:
            failures.append("MSDIS geospatial resource metadata index covers fewer than 150 feature services")
        if msdis_geospatial.get("resource_type_counts", {}).get("image_service", 0) < 50:
            failures.append("MSDIS geospatial resource metadata index covers fewer than 50 image services")
        topics = {item.get("label") for item in msdis_geospatial.get("top_topics", [])}
        for required_topic in ["ArcGIS/web services", "boundaries/administrative", "imagery", "LiDAR/elevation"]:
            if required_topic not in topics:
                failures.append(f"MSDIS geospatial resource metadata index is missing {required_topic} coverage")
    else:
        failures.append("missing reports/msdis_geospatial_index_report.json")

    for pattern in PUBLIC_OUTPUT_GLOBS:
        for path in PROJECT_ROOT.glob(pattern):
            if path.is_dir() or path.suffix.lower() in {".png"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for forbidden in FORBIDDEN_RAW_KEYS:
                if forbidden in text:
                    failures.append(f"{path.relative_to(PROJECT_ROOT)} contains raw key {forbidden}")

    if failures:
        print("Verification failed:")
        for failure in failures:
            print(f"- {failure}")
        raise SystemExit(1)

    print("Verification passed.")
    print(f"- train rows: {train_count}")
    print(f"- eval rows: {eval_count}")
    print(f"- evaluation prompts: {prompt_count}")
    print(f"- training peak VRAM MB: {training['peak_allocated_vram_mb']}")
    print(f"- adapter directory: {adapter_note}")
    print(f"- base pass count: {comparison['base']['passed_count']} / {comparison['prompt_count']}")
    print(f"- fine-tuned pass count: {comparison['fine_tuned']['passed_count']} / {comparison['prompt_count']}")
    if map_index_report.exists():
        print(f"- MAP indexed text files: {map_index['file_count']}")
        print(f"- MAP parsed rows: {map_index['file_rows_total']}")
    if oa_budget_report.exists():
        print(f"- OA Budget metadata records: {oa_budget['record_count']}")
        print(f"- OA Budget source pages: {oa_budget['page_count']}")
    if ag_market_report.exists():
        print(f"- Agricultural Market News records: {ag_market['record_count']}")
        print(f"- Agricultural Market News PDF links: {ag_market['pdf_count']}")
    if modot_aadt_report.exists():
        print(f"- MoDOT AADT records: {modot_aadt['record_count']}")
        print(f"- MoDOT AADT latest year: {modot_aadt['latest_year']}")
    if dese_school_data_report.exists():
        print(f"- DESE School Data resource links: {dese_school_data['record_count']}")
        print(f"- DESE School Data source pages: {dese_school_data['page_count']}")
    if dhss_health_sources_report.exists():
        print(f"- DHSS health resource links: {dhss_health_sources['record_count']}")
        print(f"- DHSS health source pages: {dhss_health_sources['page_count']}")
    if mec_resources_report.exists():
        print(f"- MEC public-resource links: {mec_resources['record_count']}")
        print(f"- MEC public-resource source pages: {mec_resources['page_count']}")
    if dnr_resources_report.exists():
        print(f"- DNR data/e-services resource links: {dnr_resources['record_count']}")
        print(f"- DNR data/e-services source pages: {dnr_resources['page_count']}")
    if msdis_geospatial_report.exists():
        print(f"- MSDIS geospatial resource links: {msdis_geospatial['record_count']}")
        print(f"- MSDIS geospatial source pages/endpoints: {msdis_geospatial['page_count']}")


if __name__ == "__main__":
    main()
