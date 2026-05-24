# Missouri Public-Data Source Research

This project uses a source-first pattern: catalog official public sources, estimate access and size, then add deterministic lookup or retrieval before asking the local model to explain anything.

## Current Findings

| Source | Access | Product value | Current status |
| --- | --- | --- | --- |
| [Missouri Accountability Portal](https://mapyourtaxes.mo.gov/MAP/Portal/Default.aspx) | Public state transparency portal; MAP says it covers expenditures, revenues, tax credits, employee pay, budget restrictions, federal grants, bonds, and ARRA data, updated each business day. | Exact public finance lookup with citations. | Indexed locally: 104 files, 6,123,427 rows. |
| [MissouriBUYS Contract Board](https://missouribuys.mo.gov/contractboard) and [OA Contract Search](https://archive.oa.mo.gov/purch/contracts/) | Public contract board and legacy statewide contract search. OA purchasing also links current contracts, awarded bid/contract document search, and statewide contract search. | Contract number/vendor lookup, source document links, plain-English explanations, MAP payment context. | Metadata indexed: 991 contracts; first local PDF text pass: 12 documents, 4.29 MB. |
| [data.mo.gov data.json](https://data.mo.gov/data.json) | Public Socrata/DCAT catalog. | Discovery layer for health, labor, natural resources, regulatory, and government administration data. | Preflight found 277 catalog datasets and 272 with distributions. |
| [DESE School Data](https://dese.mo.gov/school-data) | Official school data pages for accountability, dashboard, staff, district data, state assessment, student characteristics, and school directory. | District/school accountability and finance summaries. | Cataloged; no bulk ingestion yet. |
| [DESE School Directory Data Downloads](https://dese.mo.gov/school-directory/data-downloads) | Directory data refreshed weekly; reports can be saved as Excel/PDF. | Good first education ingestion target because it is small and public. | Planned. |
| [DHSS Data & Statistics](https://health.mo.gov/data/) | Public health dashboards, profiles, MOPHIMS, MICA, births, deaths, PAS, BRFSS, CLS, HAI, ESSENCE, and reports. | County public-health profiles and aggregate trend explanations. | Cataloged; aggregate-only policy required. |
| [MSHP SAC Data Files](https://www.mshp.dps.mo.gov/MSHPWeb/SAC/data_960grid.html) | Public Excel files for crime, crash, and traffic arrests. | Traffic safety facts: fatalities, injuries, crash factors, rates. | Preflight found 22 Excel files; key crash files are about 0.32 MB. |
| [MSHP Crash Data](https://www.mshp.dps.mo.gov/MSHPWeb/SAC/crash_data_960grid.html) | Official crash definitions and statistics from the Statewide Traffic Accident Records System. | Makes crash questions interpretable and cited. | Cataloged. |
| [MERIC unemployment data](https://meric.mo.gov/data/unemployment) | Public unemployment reports, labor force data, and dashboard links. | Labor market and county unemployment questions. | Cataloged. |
| [Missouri DNR Data and e-Services](https://dnr.mo.gov/data-e-services) | Environmental data, ArcGIS services, water permits, public water systems, impaired waters, water quality tools. | Environment and water lookup questions. | Cataloged; start small because many surfaces are search tools/maps. |
| [MSDIS](https://www.msdis.missouri.edu/) | Missouri GIS data, ArcGIS services, imagery, elevation, LiDAR, vector layers. | Geospatial context for county/district/source mapping. | Cataloged; avoid imagery/LiDAR downloads by default. |
| [Secretary of State Elections](https://www.sos.mo.gov/elections/s_default) | Official election results pages; some precinct files may require contact/purchase. | Election result lookup where public bulk files are available. | Watchlist; preflight hit 403 from script. |

## Recommended Product Direction

1. Contract explainer: best immediate feature. It combines contract metadata, public document links, optional PDF text extraction, and MAP vendor-payment context.
2. MSHP crash aggregates: small files, low storage risk, easy demos.
3. DESE school directory and public aggregate school data: useful, public, and portfolio-relevant.
4. DHSS aggregate county profiles: high value, but apply privacy/suppression rules.
5. data.mo.gov catalog-driven additions: use catalog metadata to select stable datasets instead of guessing URLs.

## Local-Only Constraints

- Raw downloads stay under `data/raw_public/` and are ignored by Git.
- Contract PDFs are capped by `--limit` and `--max-mb`.
- Health and education ingestion should prefer aggregate public outputs.
- The chatbot should refuse private identifiers, full table dumps, and unsupported claims.
