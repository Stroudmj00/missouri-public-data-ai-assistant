# Ingestion Report

Generated at: `2026-05-23T02:04:53+00:00`

## Preflight Estimates

| Source | Step | Expected Download | Safety Limit |
| --- | --- | ---: | --- |
| Missouri Accountability Portal | Download EXP_2026 only | 8.3 MB | single recent expenditure file; no employee salary files |
| Profile of Hospitals | Download all rows from data.mo.gov JSON endpoint | 0.0547 MB | sanitize columns before public output |
| LTC Census Report | Download all rows from data.mo.gov JSON endpoint | 0.0016 MB | sanitize columns before public output |

## Actual Downloads

| Artifact | Downloaded | Size | Runtime |
| --- | ---: | ---: | ---: |
| MAP_EXP_2026 | False | 8.295 MB | 0 sec |
| data_mo_hospital_profile | False | 0.135 MB | 0 sec |
| data_mo_ltc_census | False | 0.005 MB | 0 sec |

## Public Aggregate Output

- MAP rows processed: 94,731
- MAP agencies: 25
- MAP categories: 18
- Training QA rows: 100
- Evaluation QA rows: 20
- End-to-end runtime: 1.915 seconds

## Safety Checks

- Employee salary files were not downloaded.
- MAP vendor names were not emitted in processed public artifacts.
- Hospital administrator names, addresses, phone, and fax fields were not emitted.
