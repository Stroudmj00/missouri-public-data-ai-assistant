"""Behavioral checks for the local public-data chatbot."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from missouri_tiny_llm.ask_model import AskEngine  # noqa: E402


CASES = [
    {
        "question": "Where does Kory Hubbard work?",
        "contains": ["AGRICULTURE", "ACCOUNTANT"],
        "citation_contains": ["Employee pay", "EMP_2026.txt"],
        "no_source_rows": True,
        "model": "deterministic_public_lookup",
    },
    {
        "question": "which missouri employee gets paid the most?",
        "contains": [
            "highest indexed MAP employee-pay entry for 2026",
            "PROTECTED (PUBLIC SAFETY)",
            "$2,618,673.69",
            "highest named individual",
            "AUGUSTINE",
        ],
        "citation_contains": ["Employee pay", "EMP_2026.txt"],
        "no_source_rows": True,
        "model": "deterministic_public_lookup",
    },
    {
        "question": "Where does Kory Hubbard live?",
        "contains": ["cannot help with private identifiers"],
        "model": "public_data_boundary",
    },
    {
        "question": "What is Kory Hubbard's mailing address?",
        "contains": ["cannot help with private identifiers"],
        "model": "public_data_boundary",
    },
    {
        "question": "How much did OFFICE OF ADMINISTRATION pay CAPITAL MALL JC 1 LLC in 2025?",
        "contains": ["$249,336.95", "OFFICE OF ADMINISTRATION", "CAPITAL MALL JC 1 LLC"],
        "citation_contains": ["Expenditures", "EXP_2025.txt", "expenditure_agency_vendor"],
        "source_rows_contains": ["EXP_2025.txt", "OFFICE OF ADMINISTRATION", "CAPITAL MALL JC 1 LLC", "Payments Total"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What are the top 5 vendors for TRANSPORTATION in 2025?",
        "contains": ["BOKF NA", "CAPITAL PAVING & CONSTRUCTION"],
        "citation_contains": ["Expenditures", "EXP_2025.txt"],
        "no_source_rows": True,
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What tax credit amount was issued to CARTWRIGHT HOLDINGS in fiscal year twenty twenty six?",
        "contains": ["$23,139.21", "CARTWRIGHT HOLDINGS", "2026"],
        "source_rows_contains": ["TC_2026.txt", "CARTWRIGHT HOLDINGS", "Issued Amount"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What is the unemployment rate in Missouri?",
        "contains": ["Missouri unemployment rate", "April 2026", "3.8%", "Seasonally adjusted"],
        "citation_contains": ["MERIC Local Area Unemployment Statistics", "meric_labor_index"],
        "source_rows_contains": ["MISSOURI", "unemployment_rate", "3.8"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "Forecast Missouri transportation spending in 2030",
        "contains": ["do not have indexed source support"],
        "model": "unsupported_scope_guardrail",
    },
    {
        "question": "How much was paid to imaginary vendor D L H LLC in 2025?",
        "contains": ["could not identify a matching vendor"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "How much was spent on transportation in 2025?",
        "contains": ["$3,084,106,408.79", "TRANSPORTATION"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What was the aggregate MAP expenditure total for TRANSPORTATION in 1999?",
        "contains": ["not for requested year(s) 1999", "2000-2026"],
        "citation_contains": ["Expenditures", "public_amount_lookup"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "How much was paid by CAPITAL MALL JC 1 LLC to TRANSPORTATION?",
        "contains": ["does not support vendor-to-agency payment direction"],
        "model": "unsupported_scope_guardrail",
    },
    {
        "question": "What are the top 10 vendors for TRANSPORTATION in 2025?",
        "contains": ["1. BOKF NA", "10. MAGRUDER PAVING LLC"],
        "no_source_rows": True,
        "model": "deterministic_public_lookup",
    },
    {
        "question": "Show me top 3 agencies by MAP spending in 2026",
        "contains": ["1. SOCIAL SERVICES", "3. MENTAL HEALTH"],
        "not_contains": ["4. TRANSPORTATION"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What year has the highest transportation spending and by how much?",
        "contains": ["highest indexed MAP expenditure for TRANSPORTATION is 2026", "$3,123,182,666.35", "difference"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "Get all transactions made by vendor ID 999999",
        "contains": ["do not have indexed source support"],
        "model": "unsupported_scope_guardrail",
    },
    {
        "question": "How much was paid to the Transportation agency in 2025?",
        "contains": ["$3,084,106,408.79", "TRANSPORTATION"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What are the top 10 agencies in 2026?",
        "contains": ["Top indexed MAP expenditure totals in 2026", "10. NATURAL RESOURCES"],
        "not_contains": ["tax-credit"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "Can you list every person at the Department of Revenue",
        "contains": ["do not have indexed source support"],
        "model": "unsupported_scope_guardrail",
    },
    {
        "question": "Which agency paid CAPITAL MALL JC 1 LLC in 2025?",
        "contains": ["OFFICE OF ADMINISTRATION", "$249,336.95"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "How much did TRANSPORTATION pay BOKF NA in 2025?",
        "contains": ["$453,479,131.62", "paid by TRANSPORTATION to BOKF NA"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "How many licensed hospital beds are in the processed hospital profile source?",
        "contains": ["21,202 licensed beds"],
        "citation_contains": ["Hospital Profile", "data_mo_hospital_profile.json", "sha256"],
        "model": "retrieved_public_qa",
    },
    {
        "question": "who is the govenor of missouri",
        "contains": ["Mike Kehoe", "58th Governor", "January 13, 2025"],
        "citation_contains": ["Missouri Civic Facts", "https://governor.mo.gov/"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "Find contract CC221256001 and show its document links.",
        "contains": ["AUTOMOTIVE PARTS AND SUPPLIES", "Elliott Auto Supply", "cc221256.pdf"],
        "citation_contains": ["Missouri Contracts", "https://missouribuys.mo.gov/contractboard"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "Explain contract CC221256001 in simple terms.",
        "contains": ["Plain-English contract summary", "AUTOMOTIVE PARTS AND SUPPLIES", "Source documents", "MAP payment context"],
        "citation_contains": ["Missouri Contracts", "cc221256.pdf"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What public data sources can this project add next?",
        "contains": ["Missouri Accountability Portal", "DESE School Data", "DHSS Data", "MSHP Statistical Analysis Center", "MoDOT", "contracts first"],
        "citation_contains": ["Public Data Source Registry", "https://data.mo.gov/data.json", "https://health.mo.gov/data/"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What MSHP crash data is connected?",
        "contains": ["MSHP Statistical Analysis Center data files is connected", "traffic safety", "CrashesSeverity.xls"],
        "citation_contains": ["Missouri public source index", "https://www.mshp.dps.mo.gov/MSHPWeb/SAC/data_960grid.html"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "How many people were killed in Missouri crashes in 2014?",
        "contains": ["766", "Persons Killed", "CrashesSeverity.xls"],
        "citation_contains": ["MSHP Statistical Analysis Center data files", "CrashesSeverity.xls", "mshp_crash_index"],
        "source_rows_contains": ["Persons Killed", "2014", "766"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "How many alcohol-involved crashes were listed in 2014?",
        "contains": ["5,976", "Alcohol Involved", "CrashesCircumstances.xls"],
        "citation_contains": ["MSHP Statistical Analysis Center data files", "CrashesCircumstances.xls", "mshp_crash_index"],
        "source_rows_contains": ["Alcohol Involved", "5976"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "How many fatal crashes involved speed in 2014?",
        "contains": ["248", "Fatal Crashes", "CrashesSpeed.xls"],
        "citation_contains": ["MSHP Statistical Analysis Center data files", "CrashesSpeed.xls", "mshp_crash_index"],
        "source_rows_contains": ["Fatal Crashes", "248"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What was the Missouri crash death rate in 2014?",
        "contains": ["1.08", "Death Rate", "CrashesRates.xls"],
        "citation_contains": ["MSHP Statistical Analysis Center data files", "CrashesRates.xls", "mshp_crash_index"],
        "source_rows_contains": ["Death Rate", "1.08"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "Which crash factor had the highest count in 2014?",
        "contains": ["Older Driver Involved", "42,747", "Young Driver Involved"],
        "citation_contains": ["MSHP Statistical Analysis Center data files", "CrashesCircumstances.xls", "mshp_crash_index"],
        "source_rows_contains": ["Older Driver Involved", "42747", "Speed Involved"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "How many people were killed in Missouri crashes in 2024?",
        "contains": ["not for requested year 2024", "1978 to 2014"],
        "citation_contains": ["MSHP Statistical Analysis Center data files", "mshp_crash_index"],
        "no_source_rows": True,
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What DESE education data is connected?",
        "contains": ["DESE School Data is connected", "accountability", "School Directory"],
        "citation_contains": ["Missouri public source index", "https://dese.mo.gov/school-data"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What DESE school directory data is indexed?",
        "contains": ["DESE School Directory exact lookup layer", "489 district row(s)", "2,433 school/building row(s)", "Data as of: 3/4/2026"],
        "citation_contains": ["DESE School Directory", "dese_directory_index", "FileDownloadWebHandler"],
        "no_source_rows": True,
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What county is Columbia 93 in?",
        "contains": ["Columbia 93", "010-093", "Boone County", "MSIP: Accredited", "18,628"],
        "citation_contains": ["DESE School Directory", "dese_directory_index"],
        "source_rows_contains": ["Columbia 93", "010-093", "Boone", "Accredited"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "How many schools are listed for Columbia 93 in the DESE directory?",
        "contains": ["34 school/building row(s)", "Columbia 93", "Boone County"],
        "citation_contains": ["DESE School Directory", "dese_directory_index"],
        "source_rows_contains": ["Columbia 93", "school_count", "34"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What grade span is Rock Bridge Sr. High?",
        "contains": ["Rock Bridge Sr. High", "1075", "Columbia 93", "Grade span: 09-12"],
        "citation_contains": ["DESE School Directory", "dese_directory_index"],
        "source_rows_contains": ["Rock Bridge Sr. High", "1075", "09-12"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "Which Missouri school district has the largest enrollment in the DESE directory?",
        "contains": ["Springfield R-XII", "25,114", "North Kansas City 74", "Rockwood R-VI"],
        "citation_contains": ["DESE School Directory", "dese_directory_index"],
        "source_rows_contains": ["Springfield R-XII", "25114"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What education data is indexed?",
        "contains": ["education exact lookup layer", "Total Number of High School Seniors in Missouri", "14,123"],
        "citation_contains": ["data_mo_education_index", "8yaf-xv66", "t9f4-ncza"],
        "no_source_rows": True,
        "model": "deterministic_public_lookup",
    },
    {
        "question": "How many high school seniors are listed for Rock Bridge Sr. High in 2026?",
        "contains": ["ROCK BRIDGE SR. HIGH", "COLUMBIA 93", "497 high school seniors", "2026"],
        "citation_contains": ["Total Number of High School Seniors in Missouri", "8yaf-xv66"],
        "source_rows_contains": ["ROCK BRIDGE SR. HIGH", "497", "2026"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "Which school had the most high school seniors in 2026?",
        "contains": ["Missouri Virtual Academy", "682", "LIBERTY NORTH HIGH SCHOOL"],
        "citation_contains": ["Total Number of High School Seniors in Missouri", "data_mo_education_index"],
        "source_rows_contains": ["Missouri Virtual Academy", "682"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "How many completed FAFSA applications did Rock Bridge Sr. High report in 2026?",
        "contains": ["Rock Bridge Sr. High", "259 completed FAFSA applications", "2026"],
        "citation_contains": ["Completed FAFSAs Reported to MDHE", "t9f4-ncza"],
        "source_rows_contains": ["Rock Bridge Sr. High", "259"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "How many FAFSA applications did St Pius X High School report in 2024?",
        "contains": ["ST PIUS X HIGH SCHOOL", "suppressed or not numeric", "source value is suppressed"],
        "citation_contains": ["Completed FAFSAs Reported to MDHE", "t9f4-ncza"],
        "source_rows_contains": ["ST PIUS X HIGH SCHOOL", "suppressed"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What DHSS public health data is connected?",
        "contains": ["DHSS Data", "county profiles", "MICA"],
        "citation_contains": ["Missouri public source index", "https://health.mo.gov/data/"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What public health data is indexed?",
        "contains": ["public-health exact lookup layer", "Missouri Communicable Disease Report (2026)", "52 aggregate disease/condition rows"],
        "citation_contains": ["Missouri Communicable Disease Report (2026)", "data_mo_health_index", "fk75-fa28"],
        "no_source_rows": True,
        "model": "deterministic_public_lookup",
    },
    {
        "question": "How many anaplasmosis cases are listed YTD in the Missouri communicable disease report?",
        "contains": ["ANAPLASMOSIS", "current week year-to-date count as 16", "rate per 100k: 0.26"],
        "citation_contains": ["Missouri Communicable Disease Report (2026)", "data_mo_health_index"],
        "source_rows_contains": ["ANAPLASMOSIS", "current_week_ytd", "16.0"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What is the rate per 100k for salmonellosis?",
        "contains": ["SALMONELLOSIS", "rate per 100k as 3.66", "Current week YTD: 225"],
        "citation_contains": ["Missouri Communicable Disease Report (2026)", "data_mo_health_index"],
        "source_rows_contains": ["SALMONELLOSIS", "rate_per_100k", "3.66"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "Which disease has the highest current week YTD count?",
        "contains": ["highest listed current week year-to-date count", "CAMPYLOBACTERIOSIS: 371", "SALMONELLOSIS: 225"],
        "citation_contains": ["Missouri Communicable Disease Report (2026)", "data_mo_health_index"],
        "source_rows_contains": ["CAMPYLOBACTERIOSIS", "current_week_ytd", "371.0"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "Does the communicable disease report list COVID?",
        "contains": ["did not match a listed disease/condition row", "not found in the indexed report snapshot"],
        "citation_contains": ["Missouri Communicable Disease Report (2026)", "data_mo_health_index"],
        "no_source_rows": True,
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What MERIC labor data is connected?",
        "contains": ["MERIC exact lookup layer", "353 aggregate rows", "115 counties", "unemployment rate"],
        "citation_contains": ["MERIC Local Area Unemployment Statistics", "meric_labor_index"],
        "no_source_rows": True,
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What is Boone County unemployment rate in March 2026?",
        "contains": ["Boone unemployment rate", "March 2026", "3.5%", "Not seasonally adjusted"],
        "citation_contains": ["MERIC Local Area Unemployment Statistics", "meric_labor_index"],
        "source_rows_contains": ["BOONE", "3667", "3.5"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "How many people were unemployed in Boone County in March 2026?",
        "contains": ["Boone unemployed people", "March 2026", "3,667"],
        "citation_contains": ["MERIC Local Area Unemployment Statistics", "meric_labor_index"],
        "source_rows_contains": ["BOONE", "unemployed", "3667"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "Which county had the highest unemployment rate in March 2026?",
        "contains": ["highest county unemployment rate", "Ozark", "7.0%", "Shannon"],
        "citation_contains": ["MERIC Local Area Unemployment Statistics", "meric_labor_index"],
        "source_rows_contains": ["OZARK", "7.0"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What DNR water data is connected?",
        "contains": ["Missouri DNR data and e-services is connected", "Water Data and e-Services", "Water Permits"],
        "citation_contains": ["Missouri public source index", "https://dnr.mo.gov/data-e-services"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What DNR water data is indexed?",
        "contains": ["DNR/water exact lookup layer", "Consumer Confidence Report", "1,425 public drinking water system rows"],
        "citation_contains": ["Consumer Confidence Report", "data_mo_water_index", "3mwf-kse4"],
        "no_source_rows": True,
        "model": "deterministic_public_lookup",
    },
    {
        "question": "How many public water systems are listed in Boone County?",
        "contains": ["12 public drinking water system row(s)", "BOONE County", "CITY OF COLUMBIA UTILITIES"],
        "citation_contains": ["Consumer Confidence Report", "data_mo_water_index"],
        "source_rows_contains": ["BOONE", "MO3010033", "ASHLAND PWS"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What is the PWSID for City of Columbia Utilities?",
        "contains": ["CITY OF COLUMBIA UTILITIES", "BOONE County", "MO3010181"],
        "citation_contains": ["Consumer Confidence Report", "data_mo_water_index"],
        "source_rows_contains": ["CITY OF COLUMBIA UTILITIES", "MO3010181"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "Which county has the most public water systems in the Consumer Confidence Report?",
        "contains": ["STONE County has the most", "92", "JEFFERSON: 67", "CAMDEN: 63"],
        "citation_contains": ["Consumer Confidence Report", "data_mo_water_index"],
        "source_rows_contains": ["STONE", "92"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "Does the Consumer Confidence Report list Imaginary Water System?",
        "contains": ["did not match a county, PWSID, or listed water-system name"],
        "citation_contains": ["Consumer Confidence Report", "data_mo_water_index"],
        "no_source_rows": True,
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What MSDIS geospatial data is connected?",
        "contains": ["MSDIS geospatial open data is connected", "GIS services", "LiDAR Services"],
        "citation_contains": ["Missouri public source index", "https://www.msdis.missouri.edu/"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What MoDOT traffic count data is connected?",
        "contains": ["MoDOT traffic and transportation data is connected", "traffic counts", "Traffic Volume Maps"],
        "citation_contains": ["Missouri public source index", "https://www.modot.org/modatazone/traffic"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What data.mo.gov catalog data is connected?",
        "contains": ["exact metadata lookup layer", "277 datasets", "Government Administration", "CSV (255)"],
        "citation_contains": ["State of Missouri data.mo.gov catalog", "data_mo_catalog_index", "https://data.mo.gov/data.json"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What are the top data.mo.gov catalog themes?",
        "contains": ["1. uncategorized: 74 dataset(s)", "2. Government Administration: 67 dataset(s)", "3. Health: 33 dataset(s)"],
        "citation_contains": ["State of Missouri data.mo.gov catalog", "data_mo_catalog_index"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "Which data.mo.gov datasets mention hospital?",
        "contains": ["Profile of Hospitals", "q8me-hzr8", "rows.csv?accessType=DOWNLOAD"],
        "citation_contains": ["State of Missouri data.mo.gov catalog", "https://data.mo.gov/d/q8me-hzr8"],
        "source_rows_contains": ["Profile of Hospitals", "q8me-hzr8", "CSV"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "Which data.mo.gov datasets mention contract?",
        "contains": ["found no matching dataset records", "specific data.mo.gov catalog snapshot"],
        "citation_contains": ["State of Missouri data.mo.gov catalog", "data_mo_catalog_index"],
        "no_source_rows": True,
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What Missouri Auditor reports are connected?",
        "contains": ["Missouri State Auditor reports is connected", "audit report discovery", "Audit Reports"],
        "citation_contains": ["Missouri public source index", "https://auditor.mo.gov/AuditReport/Menu"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What DOR reports are connected?",
        "contains": ["DOR exact lookup layer", "7 official public report files", "38,451 parsed aggregate records", "2025 county taxable sales"],
        "citation_contains": ["Missouri Department of Revenue public reports", "dor_reports_index", "https://dor.mo.gov/public-reports/"],
        "no_source_rows": True,
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What were Boone County taxable sales in 2025?",
        "contains": ["BOONE", "$4,237,498,350.94", "Q1 $961,887,603.61", "Q4 $1,151,755,888.00"],
        "citation_contains": ["Missouri Department of Revenue public reports", "DI60IL02_TXB_CNTY_F_2025.zip", "dor_reports_index"],
        "source_rows_contains": ["taxable_sales_county", "BOONE", "4237498350.94"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "Which county had the highest taxable sales in 2025?",
        "contains": ["ST LOUIS", "$23,431,048,064.90", "highest taxable-sales total"],
        "citation_contains": ["Missouri Department of Revenue public reports", "DI60IL02_TXB_CNTY_F_2025.zip"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "How many business locations are in Columbia in Boone County?",
        "contains": ["COLUMBIA", "BOONE", "4,502 business count", "5,200 location count"],
        "citation_contains": ["Missouri Department of Revenue public reports", "bus_location_tots_report.txt"],
        "source_rows_contains": ["business_locations_city", "COLUMBIA", "5200"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "How many registered passenger vehicles are in Boone County?",
        "contains": ["102,084", "registered passenger", "BOONE", "2017-12-31"],
        "citation_contains": ["Missouri Department of Revenue public reports", "kov_cnty_file.txt"],
        "source_rows_contains": ["vehicle_county_kind", "PASSENGER", "102084"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "How many licensed drivers are in Boone County?",
        "contains": ["129,318", "total drivers", "BOONE", "2024-11-14"],
        "citation_contains": ["Missouri Department of Revenue public reports", "drivers_age_cnty_report.txt"],
        "source_rows_contains": ["driver_county_total", "129318"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "How many motor vehicle dealers are in Boone County?",
        "contains": ["95 MOTOR V dealer records", "BOONE", "aggregate dealer counts only"],
        "citation_contains": ["Missouri Department of Revenue public reports", "DI52L06_dealers_file_cnty.txt"],
        "source_rows_contains": ["dealer_county_type", "MOTOR V", "95"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "How many SIC 0740 locations are listed statewide?",
        "contains": ["1,374 total statewide locations", "SIC 0740", "VETERINARY SERVICES"],
        "citation_contains": ["Missouri Department of Revenue public reports", "DT60871_SIC_statetots.txt"],
        "source_rows_contains": ["sic_state_total", "0740", "1374"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What were Boone County taxable sales in 2024?",
        "contains": ["currently indexes county Sales/Use totals for 2025", "not requested year 2024"],
        "citation_contains": ["Missouri Department of Revenue public reports", "dor_reports_index"],
        "no_source_rows": True,
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What MEC reports are connected?",
        "contains": ["Missouri Ethics Commission public records is connected", "campaign finance", "Committee Contributions & Expenditures"],
        "citation_contains": ["Missouri public source index", "https://mec.mo.gov/"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What SOS election data is connected?",
        "contains": ["Missouri Secretary of State election data is connected", "election source discovery", "Election Results"],
        "citation_contains": ["Missouri public source index", "https://www.sos.mo.gov/elections/s_default"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What OA Budget data is connected?",
        "contains": ["Office of Administration Budget and Planning is connected", "executive budget", "Budget Information"],
        "citation_contains": ["Missouri public source index", "https://oa.mo.gov/budget-and-planning"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What child care reports are connected?",
        "contains": ["DESE child care compliance dashboards is connected", "child-care source discovery", "Child Care Compliance"],
        "citation_contains": ["Missouri public source index", "https://dese.mo.gov/childhood/child-care/child-care-data-dashboards"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What long-term care reports are connected?",
        "contains": ["DHSS long-term care inspection data is connected", "long-term-care source discovery", "Show Me Long-Term Care"],
        "citation_contains": ["Missouri public source index", "https://health.mo.gov/safety/nursinghomesinspected/index.php"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What PSC reports are connected?",
        "contains": ["Missouri Public Service Commission reports is connected", "utility-regulation source discovery", "PSC Reports"],
        "citation_contains": ["Missouri public source index", "https://psc.mo.gov/General/PSC_Reports"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What utility data is indexed?",
        "contains": ["utility exact lookup layer", "Find A Missouri Utility", "1,718 city/county utility rows"],
        "citation_contains": ["Find A Missouri Utility", "data_mo_utility_index", "yeiz-h2m2"],
        "no_source_rows": True,
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What utilities serve Columbia in Boone County?",
        "contains": ["COLUMBIA, BOONE County", "electric: COLUMBIA", "gas: UNION ELECTRIC COMPANY", "telephone: CENTURYLINK"],
        "citation_contains": ["Find A Missouri Utility", "data_mo_utility_index"],
        "source_rows_contains": ["COLUMBIA", "BOONE", "UNION ELECTRIC COMPANY", "CENTURYLINK"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "How many utility rows are listed for Boone County?",
        "contains": ["19 utility row(s)", "BOONE County", "Example cities"],
        "citation_contains": ["Find A Missouri Utility", "data_mo_utility_index"],
        "source_rows_contains": ["ASHLAND", "BOONE", "UNION ELECTRIC COMPANY"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "Which electric utility appears most often?",
        "contains": ["most frequent listed electric utility", "UNION ELECTRIC COMPANY: 514", "KCP&L GREATER MISSOURI OPERATIONS"],
        "citation_contains": ["Find A Missouri Utility", "data_mo_utility_index"],
        "source_rows_contains": ["UNION ELECTRIC COMPANY", "514"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "Does the utility table list Imaginary City?",
        "contains": ["did not match a listed city/county utility row"],
        "citation_contains": ["Find A Missouri Utility", "data_mo_utility_index"],
        "no_source_rows": True,
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What agriculture feed testing data is indexed?",
        "contains": ["agriculture/feed exact lookup layer", "feed sample testing results", "8,388 public feed sample testing rows"],
        "citation_contains": ["Missouri Department of Agriculture - feed sample testing results", "data_mo_agriculture_index", "y9w9-qkg2"],
        "no_source_rows": True,
        "model": "deterministic_public_lookup",
    },
    {
        "question": "Which feed class appears most often in the agriculture feed testing data?",
        "contains": ["feed class with the most rows", "Beef Feed: 1536", "Poultry Feed: 816"],
        "citation_contains": ["Missouri Department of Agriculture - feed sample testing results", "data_mo_agriculture_index"],
        "source_rows_contains": ["Beef Feed", "1536"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What are the protein values for sample D202500550?",
        "contains": ["D202500550", "WHEAT MIDDS", "protein guarantee: 14.00 pct", "result: 17.2100 pct"],
        "citation_contains": ["Missouri Department of Agriculture - feed sample testing results", "data_mo_agriculture_index"],
        "source_rows_contains": ["D202500550", "WHEAT MIDDS", "17.2100"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "How many Poultry Feed samples are indexed?",
        "contains": ["816 Poultry Feed sample row(s)", "D202600589", "QUALITY EGG"],
        "citation_contains": ["Missouri Department of Agriculture - feed sample testing results", "data_mo_agriculture_index"],
        "source_rows_contains": ["Poultry Feed", "QUALITY EGG"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "Does the feed sample index list sample D209999999?",
        "contains": ["did not match a listed feed sample ID", "What agriculture feed testing data is indexed?"],
        "citation_contains": ["Missouri Department of Agriculture - feed sample testing results", "data_mo_agriculture_index"],
        "no_source_rows": True,
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What cannabis reports are connected?",
        "contains": ["DHSS Division of Cannabis Regulation reports is connected", "cannabis-regulation source discovery", "Data and Reports"],
        "citation_contains": ["Missouri public source index", "https://health.mo.gov/safety/cannabis/"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What agriculture reports are connected?",
        "contains": ["Missouri Agricultural Market News reports is connected", "agricultural market source discovery", "Missouri Cattle/Livestock Market Reports"],
        "citation_contains": ["Missouri public source index", "https://agmarketnews.mo.gov/reports/"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What federal grant amount did OFFICE OF ATTORNEY GENERAL receive in 2026?",
        "contains": ["$2,349,568.04", "OFFICE OF ATTORNEY GENERAL"],
        "source_rows_contains": ["FED_2026.txt", "Federal Agency Name", "Grant Name", "Received Amount"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What was the budget restricted amount for AGRICULTURE in 2026?",
        "contains": ["$2,000,000.00", "AGRICULTURE"],
        "source_rows_contains": ["BWH_2026.txt", "Budget Fiscal Year", "Restricted Amount", "Released Amount"],
        "model": "deterministic_public_lookup",
    },
    {
        "question": "What was the aggregate MAP expenditure total for TRANSPORTATION?",
        "contains": ["$49,783,139,212.11", "2000-2026"],
        "no_source_rows": True,
        "model": "deterministic_public_lookup",
    },
    {
        "question": "Can you list every transaction for TRANSPORTATION?",
        "contains": ["do not have indexed source support"],
        "no_source_rows": True,
        "model": "unsupported_scope_guardrail",
    },
]


def main() -> None:
    engine = AskEngine()
    failures: list[str] = []
    results = []
    for case in CASES:
        result = engine.ask(case["question"])
        answer = result.get("answer", "")
        results.append(
            {
                "question": case["question"],
                "answer": answer,
                "model": result.get("model"),
                "source": result.get("retrieved_source") or result.get("source"),
                "citations": result.get("citations", []),
                "source_row_count": len(result.get("source_rows", [])),
            }
        )
        if result.get("model") != case["model"]:
            failures.append(
                f"{case['question']!r}: expected model {case['model']}, got {result.get('model')}"
            )
        for expected in case["contains"]:
            if expected not in answer:
                failures.append(f"{case['question']!r}: answer missing {expected!r}")
        for forbidden in case.get("not_contains", []):
            if forbidden in answer:
                failures.append(f"{case['question']!r}: answer unexpectedly included {forbidden!r}")
        if case.get("citation_contains"):
            citation_blob = json.dumps(result.get("citations", []), sort_keys=True)
            if not result.get("citations"):
                failures.append(f"{case['question']!r}: expected citations")
            for expected in case["citation_contains"]:
                if expected not in citation_blob:
                    failures.append(f"{case['question']!r}: citations missing {expected!r}")
        if case.get("source_rows_contains"):
            source_rows_blob = json.dumps(result.get("source_rows", []), sort_keys=True)
            if not result.get("source_rows"):
                failures.append(f"{case['question']!r}: expected source row previews")
            if len(result.get("source_rows", [])) > 5:
                failures.append(f"{case['question']!r}: source row preview exceeded limit")
            for expected in case["source_rows_contains"]:
                if expected not in source_rows_blob:
                    failures.append(f"{case['question']!r}: source rows missing {expected!r}")
        if case.get("no_source_rows") and result.get("source_rows"):
            failures.append(f"{case['question']!r}: expected no source row previews")

    report_path = PROJECT_ROOT / "reports" / "chatbot_behavior_test_results.json"
    report_path.write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")

    if failures:
        print("Chatbot behavior tests failed:")
        for failure in failures:
            print(f"- {failure}")
        raise SystemExit(1)

    print("Chatbot behavior tests passed.")
    print(f"- cases: {len(CASES)}")
    print(f"- report: {report_path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
