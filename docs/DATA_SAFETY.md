# Data Safety And Publication Rules

This project should use public or synthetic data only.

## Allowed

- Public datasets from `data.mo.gov`
- Public Missouri Accountability Portal downloads and pages
- Public Missouri Office of Administration pages
- Public MissouriBUYS links and public contract pages
- Public federal/state open-data sources with documented licenses or access terms
- Synthetic examples created from generic procurement/operations patterns
- Aggregated statistics derived from public datasets

## Not Allowed Without Explicit Review

- Internal State of Missouri work notes
- Weekly status reports that include internal details
- Draft solicitations, procurement templates, evaluation notes, vendor communications, or agency-specific operational artifacts
- Any document that was not clearly published for public access
- Personal data, employee pay/name records, vendor/person rows, phone numbers, email addresses, or addresses unless there is a specific public-interest reason and the data use is documented

## Practical Rule

Even when data is public, prefer aggregation for model training:

- Good: "In fiscal year 2023, this agency/category combination had this total public expenditure."
- Riskier: "Vendor X received payment Y for detail Z."
- Avoid for training: public records involving named individuals, direct contact information, or anything that could make the model memorize personal details.

## Missouri Accountability Portal Rule

The Missouri Accountability Portal is public, searchable, and has downloadable files, but the model should not be trained to reproduce named employee or person-level salary records.

Allowed MAP-derived training examples:

- Definitions and source-description questions
- Fiscal-year availability questions
- File-size/download-format questions
- Aggregated expenditure totals by agency, category, fiscal year, or public program area
- Aggregated tax credit, federal grant, bond, or budget restriction summaries
- Questions where the correct behavior is "I do not know from the provided data"

Avoid MAP-derived training examples that ask for:

- Individual employee salaries
- Named-person compensation lookups
- Direct vendor/person payment memorization
- Sensitive inferences about people, agencies, or vendors
- Any claim that implies official State of Missouri endorsement

## Runtime Public Lookup Exception

The local chatbot can answer exact public Missouri Accountability Portal employee-pay questions through deterministic lookup because those records are public MAP records and the use is documented in this case study. These person-level records are not used as training targets, and the UI suppresses raw employee source-row previews by default. Private identifiers such as home address, mailing address, phone, email, birthdate, SSN, and bank/routing data remain out of scope.

The selected DHSS cannabis locator parser intentionally stores and returns only non-contact facility fields: dispensary name, license number, city, county, ZIP, update label, and source object id. Phone numbers, street addresses, websites, and coordinates from the public locator are excluded from the public report and chatbot previews.

The selected DESE child-care dashboard parser stores aggregate quarterly dashboard values only. Provider-level records, complaint narratives, addresses, phone numbers, and inspection findings are excluded from the current index and chatbot previews.

The selected PSC report parser stores report-volume metadata and official PDF links only. It does not download report PDFs or interpret utility filings, rate cases, tariffs, orders, staff positions, or legal/regulatory outcomes.

The selected OA Budget and Planning parser stores official page/link metadata only. It does not download or interpret linked PDF, Excel, redistricting, or budget-book contents, and it should not merge proposed, recommended, enacted, or historical budget stages without explicit source support.

## Recommended Dataset Strategy

1. Pull raw public data into `data/raw_public/`.
2. Generate sanitized intermediate files in `data/processed/`.
3. Generate QA pairs in `data/qa/`.
4. Publish only small samples if the source license is unclear.
5. Document source URL, access date, fields used, transformations, and exclusions.

## Public Claims Boundary

Do not claim the model is endorsed by, used by, or representative of the State of Missouri. Frame it as an independent educational case study using public data.
