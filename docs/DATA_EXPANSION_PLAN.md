# Missouri Data Expansion Plan

This phase expands the chatbot beyond the original MAP, hospital, LTC, and civic-fact coverage while keeping the same rule: exact answers must come from cited public sources or deterministic local indexes.

## Phase 1 Scope

| Domain | Source | Phase 1 behavior | Risk |
| --- | --- | --- | --- |
| Contracts | [MissouriBUYS Contract Board](https://missouribuys.mo.gov/contractboard) and [OA Contract Search](https://archive.oa.mo.gov/purch/contracts/) | Index contract number, contractor, description, category, period, detail page, and document URLs. Link documents instead of downloading them. Join contractor names to MAP vendor payments when a likely match exists. | Moderate: legacy HTML/CGI pages can change. |
| Education | [DESE School Data](https://dese.mo.gov/school-data) | Catalog accountability, assessment, staff, school finance, dashboard, and directory sources before downloading. | Moderate: many exports live behind app/report surfaces. |
| Public health | [DHSS Data](https://health.mo.gov/data/) | Catalog county profiles, births, deaths, hospitalizations/PAS, BRFSS, and related public-health sources. Prefer aggregate outputs only. | High: health data needs privacy/suppression checks. |
| Traffic safety | [MSHP SAC Data](https://www.mshp.dps.mo.gov/MSHPWeb/SAC/data_960grid.html) | Inventory small aggregate Excel crash files for severity, rates, circumstances, and factor involvement. | Low: files are small aggregate tables, but `.xls` parsing needs `xlrd`. |

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

## Current Contract Lookup

The contract index is local-only under `data/raw_public/contracts/` and is ignored by Git. The published repo includes the code and reports, not the raw local index.

Supported question shapes:

```text
Find contract CC221256001 and show its document links.
Search contracts for automotive parts.
What contracts mention Elliott Auto Supply?
```

The chatbot returns contract metadata, detail-page links, document links, and a MAP payment context when the contractor name can be matched confidently to the local MAP vendor index.

## Not In Phase 1

- Downloading every contract PDF or Word document.
- Extracting contract-document text.
- Training on raw contract documents.
- Health row-level records.
- Person-level crash reports.
- DESE data behind secure/login-only surfaces.
