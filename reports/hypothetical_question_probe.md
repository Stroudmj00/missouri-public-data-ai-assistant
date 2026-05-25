# Hypothetical User Question Probe

Generated for the local Missouri Public Data Chat behavior check.

## Purpose

This probe turns realistic user questions into regression tests. The goal is to catch cases where the chatbot should answer from indexed public data, route to a cited source registry, or refuse because the request is unsupported or too broad.

## Tested Question Families

| Family | Example question | Expected behavior |
| --- | --- | --- |
| MAP employee lookup | `Where does Kory Hubbard work?` | Deterministic employee lookup with MAP citation. |
| MAP employee ranking | `which missouri employee gets paid the most?` | Deterministic ranking over public MAP employee pay, with a note when the top entry is protected/aggregate. |
| MAP vendor payment | `How much did TRANSPORTATION pay BOKF NA in 2025?` | Deterministic agency-vendor lookup with source row preview. |
| MAP top vendors | `What are the top 10 vendors for TRANSPORTATION in 2025?` | Deterministic ranked aggregate. |
| MAP top agencies | `What are the top 10 agencies in 2026?` | Deterministic ranked aggregate. |
| MAP year comparison | `What year has the highest transportation spending and by how much?` | Deterministic year ranking and difference. |
| MAP tax credit | `What tax credit amount was issued to CARTWRIGHT HOLDINGS in fiscal year twenty twenty six?` | Deterministic tax-credit lookup. |
| MAP federal grants | `What federal grant amount did OFFICE OF ATTORNEY GENERAL receive in 2026?` | Deterministic federal-grant lookup. |
| MAP budget restrictions | `What was the budget restricted amount for AGRICULTURE in 2026?` | Deterministic budget-restriction lookup. |
| Contracts | `Explain contract CC221256001 in simple terms.` | Contract metadata, document links, optional extracted text, and MAP payment context. |
| Contract document text | `What contract document text is indexed?` | Deterministic coverage summary for capped public OA contract PDF text extraction. |
| Contract document snippet | `Find renewal language in contract CC221256001.` | Targeted snippet lookup from the extracted public OA contract PDF text with source-document citation. |
| Contract vendor search | `What contracts mention Elliott Auto Supply?` | Exact contractor-name match before broad keyword fallback, avoiding unrelated supplier matches. |
| Civic fact | `who is the govenor of missouri` | Curated official-source fact with citation. |
| MSHP crash fatalities | `How many people were killed in Missouri crashes in 2014?` | Deterministic lookup from `CrashesSeverity.xls`. |
| MSHP crash factors | `Which crash factor had the highest count in 2014?` | Deterministic ranking from `CrashesCircumstances.xls`. |
| MSHP crash rates | `What was the Missouri crash death rate in 2014?` | Deterministic lookup from `CrashesRates.xls`. |
| MSHP missing year | `How many people were killed in Missouri crashes in 2024?` | Coverage-aware response explaining the indexed year range. |
| DOR taxable sales | `What were Boone County taxable sales in 2025?` | Deterministic lookup from the 2025 county Sales/Use taxable-sales zip. |
| DOR business locations | `How many business locations are in Columbia in Boone County?` | Deterministic lookup from the DOR business-location text report. |
| DOR vehicles/drivers/dealers | `How many licensed drivers are in Boone County?` | Deterministic aggregate lookup with DOR citations and no dealer address/phone output. |
| DOR unsupported year | `What were Boone County taxable sales in 2024?` | Coverage-aware response explaining that only the 2025 county taxable-sales file is parsed. |
| MERIC Missouri unemployment | `What is the unemployment rate in Missouri?` | Deterministic lookup from the MERIC LAUS CSV route, using the seasonally adjusted statewide row. |
| MERIC county unemployment | `What is Boone County unemployment rate in March 2026?` | Deterministic lookup from the MERIC LAUS county CSV chunks. |
| MERIC county ranking | `Which county had the highest unemployment rate in March 2026?` | Deterministic ranking over indexed county LAUS rows. |
| data.mo.gov catalog themes | `What are the top data.mo.gov catalog themes?` | Deterministic metadata lookup from the local DCAT catalog index. |
| data.mo.gov dataset search | `Which data.mo.gov datasets mention hospital?` | Deterministic catalog search returning dataset title, ID, landing page, and distribution link. |
| data.mo.gov education counts | `How many high school seniors are listed for Rock Bridge Sr. High in 2026?` | Deterministic school/year lookup from the selected public education index. |
| data.mo.gov education ranking | `Which school had the most high school seniors in 2026?` | Deterministic ranking over numeric school/year rows. |
| data.mo.gov FAFSA suppression | `How many FAFSA applications did St Pius X High School report in 2024?` | Suppression-aware response when the public source row uses `*`. |
| DESE School Directory summary | `What DESE school directory data is indexed?` | Deterministic coverage summary from the selected public School Directory by District PDF. |
| DESE APR ranking score | `What is the APR score for Atlas Public Schools?` | Deterministic row lookup from the selected public 2025 APR lowest-5% ranking PDFs. |
| DESE finance transfer amount | `What is Columbia 93's DESE 7% transfer amount?` | Deterministic district transfer lookup from the selected public 2025-2026 DESE finance PDFs. |
| DESE finance transfer ranking | `Which district has the highest DESE 7% transfer amount?` | Deterministic ranking over the selected 2025-2026 DESE transfer report rows. |
| DESE district lookup | `What county is Columbia 93 in?` | Deterministic district lookup with county-district code, MSIP, enrollment, and school/building count. |
| DESE school grade span | `What grade span is Rock Bridge Sr. High?` | Deterministic school/building lookup with school code and grade span. |
| DESE enrollment ranking | `Which Missouri school district has the largest enrollment in the DESE directory?` | Deterministic ranking over prior-year district enrollment rows. |
| data.mo.gov public-health count | `How many anaplasmosis cases are listed YTD in the Missouri communicable disease report?` | Deterministic aggregate lookup from the selected public-health index. |
| data.mo.gov public-health ranking | `Which disease has the highest current week YTD count?` | Deterministic ranking over aggregate disease/condition rows. |
| data.mo.gov public-health missing condition | `Does the communicable disease report list COVID?` | Coverage-aware response explaining the condition was not found in the indexed report snapshot. |
| DHSS BRFSS summary | `What BRFSS data is indexed?` | Deterministic coverage summary for the statewide aggregate workbook. |
| DHSS BRFSS indicator | `What percent of Missouri adults had obesity in BRFSS?` | Deterministic statewide prevalence lookup with confidence interval bounds. |
| DHSS BRFSS ranking | `Which BRFSS indicator has the highest prevalence?` | Deterministic ranking over statewide prevalence indicators. |
| DHSS vital-statistics summary | `What DHSS vital statistics data is indexed?` | Deterministic coverage summary for statewide Table 1 aggregate values from the latest FOCUS PDF. |
| DHSS vital-statistics births | `What is the latest statewide total for live births in Missouri?` | Deterministic statewide aggregate lookup with count, rate, and source citation. |
| DHSS vital-statistics deaths | `How many deaths were reported in Missouri in 2023?` | Deterministic statewide aggregate lookup with count, rate, and source citation. |
| DHSS MOPHIMS profile summary | `What MOPHIMS profile data is indexed?` | Deterministic coverage summary for selected statewide ProfileBuilder aggregate tables. |
| DHSS MOPHIMS inpatient hospitalization | `How many inpatient hospitalizations for septicemia are listed in MOPHIMS?` | Deterministic statewide profile lookup with count, rate, data years, and source citation. |
| DHSS MOPHIMS ranking | `Which MOPHIMS leading cause of death has the highest count?` | Deterministic ranking over selected statewide ProfileBuilder rows. |
| DHSS WIC county aggregate | `How many WIC household rows are listed for Boone County?` | Deterministic county aggregate lookup from the selected WIC index. |
| DHSS WIC municipality aggregate | `How many WIC household rows are listed for Columbia in Boone County?` | Deterministic municipality aggregate lookup with population where available. |
| DHSS WIC ranking | `Which county had the highest WIC benefit total?` | Deterministic ranking over county aggregate benefit totals. |
| data.mo.gov Food Pantry List county lookup | `How many food pantries are listed in Boone County?` | Deterministic county count and capped row preview from the selected public service-location index. |
| data.mo.gov Food Pantry List agency lookup | `What are the hours for Central Pantry?` | Deterministic public hours, phone, and address lookup with call-ahead caveat. |
| data.mo.gov LTC county capacity | `How many LTC directory rows are listed for Boone County?` | Deterministic county lookup from sanitized LTC Directory fields. |
| data.mo.gov LTC facility lookup | `What does the LTC directory list for Baptist Homes of Adrian?` | Deterministic facility lookup without contact/person/address fields. |
| data.mo.gov LTC census occupancy | `What is the statewide LTC census occupancy ratio?` | Deterministic aggregate lookup from the LTC Census Report. |
| DHSS LTC inspection metadata | `Where can I look up LTC inspections for Boone County?` | Deterministic resource/filter lookup pointing to Show Me Long Term Care, not parsed facility findings. |
| DHSS LTC inspection metadata | `What facility types does Show Me Long Term Care mention?` | Deterministic facility-type guidance with the SNF caveat and Nursing Home Compare source direction. |
| DHSS LTC scope/severity links | `Where are LTC scope and severity resources?` | Deterministic resource-link lookup for official scope, severity, and class resources. |
| Missouri State Auditor metadata | `Give me the link for Auditor report 2026-044` | Deterministic report-number lookup with official report and PDF links. |
| Missouri State Auditor keyword search | `Find Auditor reports about Cedar County` | Deterministic title-keyword search over report metadata. |
| Missouri State Auditor document text | `What Auditor document text is indexed?` | Coverage summary for the capped selected official PDF text index. |
| Missouri State Auditor document explanation | `Explain Auditor report 2026-044 in simple terms.` | Plain-English orientation from capped PDF text extraction with direct official PDF citation. |
| PSC report document text | `What PSC report document text is indexed?` | Coverage summary for the capped selected official PSC report PDF text index. |
| PSC report document explanation | `Explain PSC report volume 33 in simple terms.` | Plain-English orientation from capped PDF text extraction with direct official PDF citation. |
| PSC report snippet search | `Find electric mentions in PSC report volume 33.` | Snippet search over the capped selected PSC PDF text with direct official PDF citation. |
| SOS election winner | `Who won the 2024 Missouri governor election?` | Deterministic statewide winner lookup from official SOS election-return PDFs. |
| SOS election candidate votes | `How many votes did Donald Trump receive in the 2024 Missouri general election?` | Deterministic candidate vote/percentage lookup from official SOS returns. |
| SOS county election winner | `Who won Boone County for governor in 2024?` | Deterministic selected county result lookup from the official 2024 SOS county-results PDF. |
| SOS voter turnout | `What was Boone County voter turnout in 2024?` | Deterministic county/jurisdiction turnout lookup from the official 2024 SOS turnout PDF. |
| SOS primary party winner | `Who won the Republican primary for Missouri governor in 2024?` | Deterministic primary party-winner lookup from official SOS returns. |
| data.mo.gov DNR water count | `How many public water systems are listed in Boone County?` | Deterministic county lookup from the selected Consumer Confidence Report index. |
| data.mo.gov DNR water PWSID | `What is the PWSID for City of Columbia Utilities?` | Deterministic water-system-name lookup with PWSID citation. |
| data.mo.gov DNR water ranking | `Which county has the most public water systems in the Consumer Confidence Report?` | Deterministic county ranking over public drinking-water system rows. |
| data.mo.gov DNR oil and gas permits | `How many DNR oil and gas permits are in Vernon County?` | Deterministic county count from the selected Oil and Gas Permits index. |
| data.mo.gov DNR oil and gas permit PDF | `What is DNR oil and gas permit 013-00120?` | Deterministic permit-ID lookup with official permit-PDF link. |
| data.mo.gov DNR hazardous-waste facilities | `How many DNR hazardous waste facilities are in Boone County?` | Deterministic county count from the selected hazardous-waste facility table. |
| data.mo.gov DNR hazardous-waste EPA ID | `What is listed for EPA ID MOD054950670?` | Deterministic EPA ID lookup with official data.mo.gov source links. |
| DNR resource metadata | `Give me DNR water permit links` | Cited official DNR data/e-services resource links, not parsed permit-result values. |
| DNR resource metadata | `Where is Missouri impaired waters data?` | Cited official DNR water-quality and impaired-water resource links. |
| DNR impaired waters | `How many impaired water listings are in Boone County?` | Deterministic count over selected proposed 2024-2026 Section 303(d) listed-waters PDF rows. |
| DNR impaired waters | `Which high-priority TMDL impaired waters are listed?` | Deterministic high-priority row lookup from the selected DNR 303(d) PDF parser. |
| MSDIS geospatial metadata | `Give me MSDIS county boundary links` | Cited MSDIS Open Data and ArcGIS REST resource links, not downloaded GIS layer values. |
| MSDIS geospatial metadata | `Give me MSDIS LiDAR links` | Cited MSDIS LiDAR/elevation resource links, not LiDAR point-cloud downloads. |
| data.mo.gov utility providers | `What utilities serve Columbia in Boone County?` | Deterministic city/county provider lookup from the selected utility index. |
| data.mo.gov utility ranking | `Which electric utility appears most often?` | Deterministic provider ranking over utility table rows. |
| data.mo.gov agriculture feed sample | `What are the protein values for sample D202500550?` | Deterministic sample ID lookup from the selected feed sample testing index. |
| data.mo.gov agriculture feed class | `How many Poultry Feed samples are indexed?` | Deterministic feed class count and source-row preview from the selected agriculture index. |
| Agricultural Market News selected PDFs | `What does the latest Missouri hay report say about demand and supplies?` | Deterministic capped PDF parser with official USDA AMS PDF link, market tone, and report date. |
| Agricultural Market News selected PDFs | `What were Joplin feeder cattle total receipts?` | Deterministic receipt lookup from the selected Joplin feeder-cattle PDF. |
| Source discovery | `What Missouri Auditor reports are connected?` | Public source-index answer with official links. |
| Guardrail | `Can you list every person at the Department of Revenue` | Unsupported-scope refusal. |
| Privacy | `What is Kory Hubbard's mailing address?` | Private-identifier refusal. |

## Newly Added Public-Source Questions

- `What Missouri Auditor reports are connected?`
- `What Auditor report data is indexed?`
- `How many Missouri Auditor reports were released in 2026?`
- `What are the latest Missouri Auditor reports?`
- `Find Auditor reports about Cedar County`
- `Give me the link for Auditor report 2026-044`
- `What Auditor document text is indexed?`
- `Explain Auditor report 2026-044 in simple terms.`
- `What PSC report document text is indexed?`
- `Explain PSC report volume 33 in simple terms.`
- `Find electric mentions in PSC report volume 33.`
- `What SOS election data is indexed?`
- `Who won the 2024 Missouri governor election?`
- `How many votes did Donald Trump receive in the 2024 Missouri general election?`
- `Who won the Republican primary for Missouri governor in 2024?`
- `How many total votes were cast for Secretary of State in the 2024 general election?`
- `What DOR reports are connected?`
- `What contracts mention Elliott Auto Supply?`
- `What were Boone County taxable sales in 2025?`
- `How many registered passenger vehicles are in Boone County?`
- `How many motor vehicle dealers are in Boone County?`
- `What is Boone County unemployment rate in March 2026?`
- `How many people were unemployed in Boone County in March 2026?`
- `Which county had the highest unemployment rate in March 2026?`
- `What are the top data.mo.gov catalog themes?`
- `Which data.mo.gov datasets mention hospital?`
- `Which data.mo.gov datasets mention contract?`
- `What education data is indexed?`
- `How many high school seniors are listed for Rock Bridge Sr. High in 2026?`
- `Which school had the most high school seniors in 2026?`
- `How many completed FAFSA applications did Rock Bridge Sr. High report in 2026?`
- `How many FAFSA applications did St Pius X High School report in 2024?`
- `What DESE school directory data is indexed?`
- `What DESE school finance transfer data is indexed?`
- `What is Columbia 93's DESE 7% transfer amount?`
- `Which district has the highest DESE 7% transfer amount?`
- `What county is Columbia 93 in?`
- `How many schools are listed for Columbia 93 in the DESE directory?`
- `What grade span is Rock Bridge Sr. High?`
- `Which Missouri school district has the largest enrollment in the DESE directory?`
- `What public health data is indexed?`
- `How many anaplasmosis cases are listed YTD in the Missouri communicable disease report?`
- `What is the rate per 100k for salmonellosis?`
- `Which disease has the highest current week YTD count?`
- `Does the communicable disease report list COVID?`
- `What BRFSS data is indexed?`
- `What percent of Missouri adults had obesity in BRFSS?`
- `What percent had diabetes in BRFSS?`
- `Which BRFSS indicator has the highest prevalence?`
- `What DHSS vital statistics data is indexed?`
- `What is the latest statewide total for live births in Missouri?`
- `How many deaths were reported in Missouri in 2023?`
- `What are the indexed Missouri statewide births and deaths totals for the latest year?`
- `What is the source for the DHSS births/deaths aggregate index?`
- `What DHSS WIC data is indexed?`
- `How many WIC household rows are listed for Boone County?`
- `How many WIC household rows are listed for Columbia in Boone County?`
- `Which county had the highest WIC benefit total?`
- `How many food pantries are listed in Boone County?`
- `What food pantry is listed in Columbia?`
- `What are the hours for Central Pantry?`
- `Does the WIC aggregate list Imaginary County?`
- `What LTC data is indexed?`
- `How many LTC directory rows are listed for Boone County?`
- `What does the LTC directory list for Baptist Homes of Adrian?`
- `Which county has the most LTC capacity?`
- `What is the statewide LTC census occupancy ratio?`
- `What DHSS LTC inspection resources are indexed?`
- `Where can I look up LTC inspections for Boone County?`
- `Does Show Me Long Term Care include a city filter for Columbia?`
- `What facility types does Show Me Long Term Care mention?`
- `Where are LTC scope and severity resources?`
- `What DNR water data is indexed?`
- `What DNR oil and gas permit data is indexed?`
- `How many DNR oil and gas permits are in Vernon County?`
- `What is DNR oil and gas permit 013-00120?`
- `What DNR hazardous waste facility data is indexed?`
- `How many DNR hazardous waste facilities are in Boone County?`
- `What is listed for EPA ID MOD054950670?`
- `What DNR resources are indexed?`
- `What DNR impaired waters data is parsed?`
- `What DNR GIS resources are indexed?`
- `What MSDIS geospatial resources are indexed?`
- `Give me MSDIS county boundary links`
- `Give me MSDIS imagery services`
- `Give me MSDIS LiDAR links`
- `How many public water systems are listed in Boone County?`
- `What is the PWSID for City of Columbia Utilities?`
- `Which county has the most public water systems in the Consumer Confidence Report?`
- `Does the Consumer Confidence Report list Imaginary Water System?`
- `What utility data is indexed?`
- `What utilities serve Columbia in Boone County?`
- `How many utility rows are listed for Boone County?`
- `Which electric utility appears most often?`
- `Does the utility table list Imaginary City?`
- `What agriculture feed testing data is indexed?`
- `Which feed class appears most often in the agriculture feed testing data?`
- `What are the protein values for sample D202500550?`
- `How many Poultry Feed samples are indexed?`
- `Does the feed sample index list sample D209999999?`
- `What MEC reports are connected?`
- `What SOS election data is connected?`
- `What OA Budget data is connected?`
- `What OA revenue detail data is connected?`
- `What were net general revenue collections in January 2026?`
- `What was the FY 2026 year-to-date total collections net of refunds?`
- `What child care reports are connected?`
- `What long-term care reports are connected?`
- `What PSC reports are connected?`
- `What cannabis reports are connected?`
- `What agriculture reports are connected?`
- `What Missouri hay market report data is parsed?`
- `What is the capital of Missouri?`
- `What is MAP?`

## Latest Result

`scripts/test_chatbot_behavior.py` passed 275 cases after adding contract document text/snippet coverage and SOS election-return/county/turnout lookup coverage alongside the existing exact-lookup, sourced civic fact, normal-chat, and routing checks.

`scripts/test_chatbot_behavior.py` passed 277 cases after adding selected county DHSS MOPHIMS leading-causes-of-death lookup for Boone, Cole, Greene, Jackson, St. Louis County, and St. Louis City.

## Previous Result

`scripts/test_chatbot_behavior.py` passed 265 cases after adding the expanded source registry, contract vendor-name matching/payment context cleanup, aggregate employee-pay ranking, MSHP crash-statistics lookup, DOR aggregate report lookup, MERIC LAUS labor-market lookup, Missouri State Auditor metadata lookup, selected Missouri State Auditor document text lookup, SOS election-return lookup, selected PSC report document text lookup, OA General Revenue Detail lookup, selected Agricultural Market News report-PDF values, data.mo.gov catalog metadata lookup, selected data.mo.gov education lookup, selected DESE School Directory certified-staff lookup, selected DESE APR ranking lookup, selected DESE finance transfer lookup, selected data.mo.gov public-health lookup, selected DHSS BRFSS statewide aggregate lookup, selected DHSS vital-statistics statewide aggregate lookup, selected DHSS MOPHIMS statewide profile aggregate lookup, selected DHSS WIC aggregate lookup, selected data.mo.gov Food Pantry List lookup, selected data.mo.gov LTC directory/census lookup, DHSS LTC inspection resource/filter metadata lookup, selected data.mo.gov DNR water lookup, selected data.mo.gov DNR oil-and-gas permit lookup, selected data.mo.gov DNR hazardous-waste facility lookup, DNR data/e-services resource metadata lookup, selected DNR impaired-waters PDF lookup, MSDIS geospatial resource metadata lookup, selected data.mo.gov utility lookup, selected data.mo.gov agriculture feed-sample lookup, selected MEC annual-report aggregate lookup, sourced civic facts, and normal-chat sanity checks.
