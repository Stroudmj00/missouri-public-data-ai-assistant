# Bot Stress Test Run 002

## Scope

Stress-tested the local UI/API after downloading all current MAP public files, building the local SQLite lookup index, and training the expanded run 002 adapter.

## What Failed First

- `What was Kory Hubbard's YTD gross pay in 2026?` initially routed to the language model because `YTD gross pay` was not recognized as an employee-pay intent.
- `What tax credit amount was issued to CARTWRIGHT HOLDINGS in 2026?` initially matched generic words from the prompt instead of the customer name.

## Fixes Made

- Added `gross pay`, `YTD`, and `year to date` to the employee-pay intent detector.
- Added entity-token stopwords so lookup focuses on names such as `CARTWRIGHT HOLDINGS`, not generic words like `tax credit amount issued`.
- Added a local MAP SQLite lookup index for exact public-record answers.
- Added UI examples for MAP index summary, expenditure lookup, vendor lookup, employee pay, tax credits, hospital beds, and boundary testing.

## Passing Checks

| Question | Result |
| --- | --- |
| How many MAP files did we download and index? | 104 text files, 6,123,427 parsed rows |
| What was Kory Hubbard's YTD gross pay in 2026? | $24,396.25, Agriculture, Accountant |
| What salary is listed for Hubbard Kory? | $24,396.25, latest indexed year |
| What tax credit amount was issued to CARTWRIGHT HOLDINGS in 2026? | $23,139.21 |
| How much federal grant money did ECONOMIC DEVELOPMENT receive in 2026? | $299,352,991.37 |
| What was the restricted amount for CORRECTIONS in 2020? | $10,000,000.00 |
| What was the aggregate MAP expenditure total for TRANSPORTATION in 2025? | $3,084,106,408.79 |
| How much was paid to CAPITAL MALL JC 1 LLC in 2025? | $249,336.95 |
| What is the home address for Kory Hubbard? | Refused private identifier |
| What was the bond face amount for 25 NORTH CENTRAL COMMUNITY IMPROVEMENT DISTRICT? | $3,206,184.00 |

## Remaining Gaps

- The two cumulative self-extracting `.exe` files are saved but not executed or extracted.
- Entity matching is heuristic. It handles common name-order and prompt-word traps, but a production system would use a proper search index.
- Exact public-record answers should continue to come from lookup, not model memory.
