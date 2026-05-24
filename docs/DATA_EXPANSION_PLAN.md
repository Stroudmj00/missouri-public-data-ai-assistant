# Missouri Data Expansion Plan

This phase expands the chatbot beyond the original MAP, hospital, LTC, and civic-fact coverage while keeping the same rule: exact answers must come from cited public sources or deterministic local indexes.

## Phase 1 Scope

| Domain | Source | Phase 1 behavior | Risk |
| --- | --- | --- | --- |
| Contracts | [MissouriBUYS Contract Board](https://missouribuys.mo.gov/contractboard) and [OA Contract Search](https://archive.oa.mo.gov/purch/contracts/) | Index contract number, contractor, description, category, period, detail page, and document URLs. Join contractor names to MAP vendor payments when a likely match exists. | Moderate: legacy HTML/CGI pages can change. |
| Contract documents | [OA Contract Search](https://archive.oa.mo.gov/purch/contracts/) | Capped local PDF download and text extraction for plain-English contract explanations. | Moderate: PDF extraction can be imperfect; downloads must be capped. |
| Open data catalog | [data.mo.gov data.json](https://data.mo.gov/data.json) | Inventory statewide Socrata/DCAT metadata before picking more datasets. | Moderate: mixed datasets, maps, files, and stale records. |
| Education | [DESE School Data](https://dese.mo.gov/school-data) | Catalog accountability, assessment, staff, school finance, dashboard, and directory sources before downloading. | Moderate: many exports live behind app/report surfaces. |
| Public health | [DHSS Data](https://health.mo.gov/data/) | Catalog county profiles, births, deaths, hospitalizations/PAS, BRFSS, and related public-health sources. Prefer aggregate outputs only. | High: health data needs privacy/suppression checks. |
| Traffic safety | [MSHP SAC Data](https://www.mshp.dps.mo.gov/MSHPWeb/SAC/data_960grid.html) | Inventory small aggregate Excel crash files for severity, rates, circumstances, and factor involvement. | Low: files are small aggregate tables, but `.xls` parsing needs `xlrd`. |
| Labor market | [MERIC unemployment data](https://meric.mo.gov/data/unemployment) | Catalog unemployment, labor force, wage, industry, projection, and regional profile releases. | Moderate: current values need clear release timestamps. |
| Environment | [Missouri DNR Data and e-Services](https://dnr.mo.gov/data-e-services) | Catalog water permits, public water systems, impaired waters, water quality, and environmental GIS surfaces. | Moderate: many surfaces are search tools or maps. |
| Geospatial | [MSDIS](https://www.msdis.missouri.edu/) | Catalog vector/GIS services first; avoid imagery and LiDAR downloads by default. | High: imagery and LiDAR can be very large. |

## Commands

Preflight all expansion sources:

```powershell
python scripts\preflight_data_expansion.py
```

Build a conservative local contract metadata index:

```powershell
python scripts\build_contract_index.py --detail-limit 200 --delay-seconds 0.04
```

Build the full contract-detail index after the conservative run is stable:

```powershell
python scripts\build_contract_index.py --force --delay-seconds 0.04
```

Build a capped local contract-document text index:

```powershell
python scripts\build_contract_document_index.py --limit 25 --max-mb 25
```

## Current Contract Lookup

The contract index is local-only under `data/raw_public/contracts/` and is ignored by Git. The published repo includes the code and reports, not the raw local index.

Supported question shapes:

```text
Find contract CC221256001 and show its document links.
Explain contract CC221256001 in simple terms.
Search contracts for automotive parts.
What contracts mention Elliott Auto Supply?
```

The chatbot returns contract metadata, detail-page links, document links, optional extracted PDF text snippets, and a MAP payment context when the contractor name can be matched confidently to the local MAP vendor index.

## Not In Phase 1

- Downloading every contract PDF or Word document.
- Training on raw contract documents.
- Health row-level records.
- Person-level crash reports.
- DESE data behind secure/login-only surfaces.
