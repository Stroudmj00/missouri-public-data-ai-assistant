"""Ask the fine-tuned model with sanitized retrieved context."""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from missouri_tiny_llm.ag_market_news_index import AgMarketNewsIndex
from missouri_tiny_llm.ag_market_report_documents import AgMarketReportDocumentIndex
from missouri_tiny_llm.cannabis_index import CannabisIndex
from missouri_tiny_llm.child_care_index import ChildCareIndex
from missouri_tiny_llm.contract_documents import ContractDocumentIndex
from missouri_tiny_llm.contract_lookup import ContractIndex
from missouri_tiny_llm.data_mo_agriculture_index import DataMoAgricultureIndex
from missouri_tiny_llm.data_mo_catalog_index import DataMoCatalogIndex
from missouri_tiny_llm.data_mo_dnr_hazardous_waste_index import DataMoDnrHazardousWasteIndex
from missouri_tiny_llm.data_mo_dnr_oil_gas_index import DataMoDnrOilGasIndex
from missouri_tiny_llm.data_mo_education_index import DataMoEducationIndex
from missouri_tiny_llm.data_mo_farmers_market_index import DataMoFarmersMarketIndex
from missouri_tiny_llm.data_mo_food_pantry_index import DataMoFoodPantryIndex
from missouri_tiny_llm.data_mo_health_index import DataMoHealthIndex
from missouri_tiny_llm.data_mo_hospital_index import DataMoHospitalIndex
from missouri_tiny_llm.data_mo_ltc_index import DataMoLtcIndex
from missouri_tiny_llm.data_mo_utility_index import DataMoUtilityIndex
from missouri_tiny_llm.data_mo_water_index import DataMoWaterIndex
from missouri_tiny_llm.data_mo_wic_index import DataMoWicIndex
from missouri_tiny_llm.dese_apr_index import DeseAprIndex
from missouri_tiny_llm.dese_directory_index import DeseDirectoryIndex
from missouri_tiny_llm.dese_finance_index import DeseFinanceIndex
from missouri_tiny_llm.dese_school_data_index import DeseSchoolDataIndex
from missouri_tiny_llm.dese_special_education_index import DeseSpecialEducationIndex
from missouri_tiny_llm.dhss_brfss_index import DhssBrfssIndex
from missouri_tiny_llm.dhss_health_sources_index import DhssHealthSourcesIndex
from missouri_tiny_llm.dhss_ltc_inspection_index import DhssLtcInspectionIndex
from missouri_tiny_llm.dhss_mophims_profiles_index import DhssMophimsProfilesIndex
from missouri_tiny_llm.dhss_vital_stats_index import DhssVitalStatsIndex
from missouri_tiny_llm.dnr_impaired_waters_index import DnrImpairedWatersIndex
from missouri_tiny_llm.dnr_resources_index import DnrResourcesIndex
from missouri_tiny_llm.dor_reports_index import DorReportsIndex
from missouri_tiny_llm.expanded_public_sources import PublicSourceIndex
from missouri_tiny_llm.map_public_index import MapPublicIndex, normalize_public_name, years_in_question
from missouri_tiny_llm.mec_annual_report_index import MecAnnualReportIndex
from missouri_tiny_llm.mec_resources_index import MecResourcesIndex
from missouri_tiny_llm.meric_labor_index import MericLaborIndex
from missouri_tiny_llm.modot_aadt_index import ModotAadtIndex
from missouri_tiny_llm.mshp_crash_index import MshpCrashIndex
from missouri_tiny_llm.msdis_geospatial_index import MsdisGeospatialIndex
from missouri_tiny_llm.oa_budget_index import OaBudgetIndex
from missouri_tiny_llm.oa_revenue_detail_index import OaRevenueDetailIndex
from missouri_tiny_llm.psc_report_documents import PscReportDocumentIndex
from missouri_tiny_llm.psc_reports_index import PscReportsIndex
from missouri_tiny_llm.public_source_catalog import PUBLIC_SOURCE_CATALOG, catalog_by_status
from missouri_tiny_llm.sos_elections_index import SosElectionsIndex
from missouri_tiny_llm.state_auditor_documents import StateAuditorDocumentIndex
from missouri_tiny_llm.state_auditor_index import StateAuditorIndex


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL = "HuggingFaceTB/SmolLM2-135M-Instruct"
DEFAULT_ADAPTER = PROJECT_ROOT / "checkpoints" / "smollm2_135m_lora_run_002"
MAP_EXPENDITURE_FILE = PROJECT_ROOT / "data" / "raw_public" / "MAP_EXP_2026.txt"
RETRIEVED_QA_MIN_SCORE = 0.42
LOCAL_SOURCE_FILES = {
    "hospital_profile": PROJECT_ROOT / "data" / "raw_public" / "data_mo_hospital_profile.json",
    "ltc_census": PROJECT_ROOT / "data" / "raw_public" / "data_mo_ltc_census.json",
}
LOCAL_SOURCE_URLS = {
    "hospital_profile": "https://data.mo.gov/d/q8me-hzr8",
    "ltc_census": "https://data.mo.gov/d/bf8b-a47t",
}

PUBLIC_DATA_LIKE_TERMS = {
    "accountability",
    "agency",
    "apr",
    "audit",
    "budget",
    "cannabis",
    "contract",
    "county",
    "data.mo.gov",
    "department",
    "dese",
    "dhss",
    "dnr",
    "dor",
    "employee",
    "expenditure",
    "federal grant",
    "finance",
    "governor",
    "hospital",
    "ltc",
    "map",
    "mec",
    "meric",
    "missouri",
    "modot",
    "mophims",
    "mshp",
    "oa budget",
    "public data",
    "public record",
    "school district",
    "sos",
    "tax",
    "vendor",
    "wic",
}

CURRENT_FACT_TERMS = {
    "current",
    "latest",
    "newest",
    "now",
    "right now",
    "today",
    "this week",
    "this month",
    "this year",
    "yesterday",
}

ARITHMETIC_OPERATOR_WORDS = {
    "plus": "+",
    "minus": "-",
    "times": "*",
    "multiplied by": "*",
    "x": "*",
    "divided by": "/",
    "over": "/",
}

ARITHMETIC_NUMBER_WORDS = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
    "eleven": "11",
    "twelve": "12",
}

PRIVATE_IDENTIFIER_PATTERNS = [
    r"\bwhere\b.*\blive\b",
    r"\blive\b.*\bwhere\b",
    r"\bmailing address\b",
    r"\bsocial security\b",
    r"\bssn\b",
    r"\bdate of birth\b",
    r"\bdob\b",
    r"\bbirth\s*date\b",
    r"\bbirthdate\b",
    r"\bhome address\b",
    r"\bpersonal address\b",
    r"\bpersonal contact\b",
    r"\bphone number\b",
    r"\bemail address\b",
    r"\bbank account\b",
    r"\brouting number\b",
]

SALARY_SCOPE_PATTERNS = [
    r"\bsalary\b",
    r"\bemployee\b",
    r"\bpayroll\b",
    r"\bwages?\b",
    r"\bgross pay\b",
    r"\bytd\b",
    r"\byear to date\b",
    r"\bwhere\b.*\bwork",
    r"\bwork\b.*\bwhere",
    r"\bposition\b",
    r"\btitle\b",
]
VENDOR_LOOKUP_PATTERNS = [r"\bvendor\b", r"\bvendors\b", r"\bpaid to\b", r"\bpayments? to\b"]
CONTRACT_LOOKUP_PATTERNS = [
    r"\bcontract\b",
    r"\bcontracts\b",
    r"\bmissouribuys\b",
    r"\bcontract board\b",
    r"\bcontract number\b",
]
CONTRACT_EXPLANATION_PATTERNS = [
    r"\bexplain\b",
    r"\bsummar(?:y|ize|ise)\b",
    r"\bplain\s+english\b",
    r"\bsimple\b",
    r"\bwhat\s+does\b.*\bmean\b",
    r"\bwhat\s+is\b.*\bfor\b",
]
CONTRACT_DOCUMENT_INDEX_PATTERNS = [
    r"\bcontract\b.*\b(document text|pdf text|documents? indexed|pdfs? indexed|coverage|parsed|extracted)\b",
    r"\b(document text|pdf text|documents? indexed|pdfs? indexed|coverage|parsed|extracted)\b.*\bcontract\b",
]
CONTRACT_DOCUMENT_SNIPPET_PATTERNS = [
    r"\b(?:find|search|show|quote|snippet|language|mentions?|inside)\b.*\bcontract\b",
    r"\bcontract\b.*\b(?:find|search|show|quote|snippet|language|mentions?|inside)\b",
    r"\b(document text|pdf text|extracted text)\b.*\bcontract\b",
    r"\bcontract\b.*\b(document text|pdf text|extracted text)\b",
    r"\b(?:renewal|expiration|termination|scope|purpose|pricing|delivery|insurance|public use)\b.*\bcontract\b",
    r"\bcontract\b.*\b(?:renewal|expiration|termination|scope|purpose|pricing|delivery|insurance|public use)\b",
]
CONTRACT_PAYMENT_CONTEXT_PATTERNS = [
    r"\bhow\s+much\b.*\b(?:pay|paid|payment|payments|spend|spent)\b.*\bcontract\b",
    r"\b(?:payment|payments|pay|paid|spend|spent)\b.*\b(?:total|totals|context|history)\b.*\bcontract\b",
    r"\bcontract\b.*\b(?:payment|payments|pay|paid|spend|spent|map)\b",
    r"\bwhich\s+agenc(?:y|ies)\b.*\b(?:uses?|used|pay|paid|paying)\b.*\bcontract\b",
    r"\b(?:top|largest)\s+agenc(?:y|ies)\b.*\bcontract\b",
]
PUBLIC_SOURCE_CATALOG_PATTERNS = [
    r"\bpublic\s+data\b.*\b(source|sources|catalog|available|access|hook|connect|include)\b",
    r"\bdata\s+(source|sources|catalog)\b",
    r"\bwhat\s+data\b.*\b(access|include|hook|connect|available)\b",
    r"\bwhich\s+datasets\b",
    r"\bwhat\s+datasets\b",
    r"\bresearch\b.*\bpublic\s+data\b",
]
DATA_MO_CATALOG_PATTERNS = [
    r"\bdata\.mo\.gov\b",
    r"\bstate\s+of\s+missouri\s+open\s+data\s+catalog\b",
    r"\bmissouri\s+open\s+data\s+catalog\b",
]
EDUCATION_LOOKUP_PATTERNS = [
    r"\bfafsa\b",
    r"\bhigh\s+school\s+senior(?:s)?\b",
    r"\bsenior\s+count\b",
    r"\bschool\s+senior(?:s)?\b",
    r"\bnumber\s+of\s+seniors\b",
    r"\beducation\b.*\b(indexed|lookup|data)\b",
    r"\bschool\b.*\b(indexed|lookup|data)\b",
]
DESE_DIRECTORY_LOOKUP_PATTERNS = [
    r"\bdese\b.*\bdirectory\b",
    r"\bschool\s+directory\b.*\b(indexed|lookup|data|county|district|school|grade|msip)\b",
    r"\bcounty[-\s]+district\b",
    r"\bgrade\s+span\b",
    r"\bmsip\b.*\b(school|district|dese)\b",
    r"\bcertified\s+staff\b",
    r"\b(?:district|school|dese)\b.*\b(?:staff\s+count|staffing|teacher\s+count|teacher\s+staffing)\b",
]
DESE_APR_LOOKUP_PATTERNS = [
    r"\bdese\b.*\bapr\b.*\b(score|scores|ranking|rankings|rank|ranks|lowest|highest|bottom|listed|index|indexed|lookup|data)\b",
    r"\bapr\b.*\b(dese|score|scores|ranking|rankings|rank|ranks|lea|leas|district|school|building|lowest|highest|bottom|listed)\b",
    r"\bsingle[-\s]+year\s+apr\b",
]
DESE_FINANCE_LOOKUP_PATTERNS = [
    r"\bdese\b.*\b(school\s+finance|finance|7%|7\s+percent|5%|5\s+percent|transfer|transportation\s+transfer|capital\s+projects?|incidental|wm/wada|wada|designated\s+levy)\b",
    r"\bschool\s+finance\b.*\b(dese|transfer|7%|7\s+percent|5%|5\s+percent|transportation|capital\s+projects?|incidental|wm/wada|wada)\b",
    r"\b(7%|7\s+percent|5%|5\s+percent|162,326|162326|designated\s+levy)\b.*\b(dese|school|district|transfer|capital\s+projects?|incidental)\b",
    r"\btransportation\s+transfer\b.*\b(dese|school|district|finance|fund|columbia|wada)\b",
    r"\b(columbia\s+93|adair\s+co\.?\s+r-i|st\.?\s+louis\s+city)\b.*\b(dese|transfer|school\s+finance)\b",
]
DESE_SPECIAL_EDUCATION_LOOKUP_PATTERNS = [
    r"\bdese\b.*\bspecial[-\s]+(?:education|ed)\b.*\b(incidence|child\s+count|counts?|rate|rates?|disabilit(?:y|ies)|autism|learning|speech|language|enrollment|highest|largest|top|trend|change|indexed|coverage|what data)\b",
    r"\bspecial[-\s]+(?:education|ed)\b.*\b(incidence|child\s+count|counts?|rate|rates?|disabilit(?:y|ies)|autism|learning|speech|language|enrollment|highest|largest|top|trend|change)\b.*\b(missouri|statewide|dese|20\d{2})\b",
    r"\b(autism|specific learning disabilit(?:y|ies)|learning disabilit(?:y|ies)|other health impaired|speech impairment|language impairment|emotional disturbance|intellectual disabilit(?:y|ies)|traumatic brain injury|developmental delay)\b.*\bspecial[-\s]+(?:education|ed)\b",
    r"\b(autism|specific learning disabilit(?:y|ies)|learning disabilit(?:y|ies)|other health impaired|speech impairment|language impairment|emotional disturbance|intellectual disabilit(?:y|ies)|traumatic brain injury|developmental delay)\b.*\b(dese|special[-\s]+(?:education|ed)|incidence|child\s+count|counts?|rate|rates?)\b",
]
DESE_SCHOOL_DATA_LOOKUP_PATTERNS = [
    r"\bdese\b.*\b(accountability|assessment|school\s+finance|finance|core\s+data|mosis|file\s+layouts?|file\s+spec|code\s+sets?|apr|msip|special\s+education|data\s+portal|dashboard|resources?|links?)\b",
    r"\b(apr|msip)\b.*\b(dese|ranking|lea|school|accountability)\b",
    r"\bcore\s+data\b.*\b(mosis|file\s+layouts?|code\s+sets?|resources?|links?)\b",
    r"\bmosis\b.*\b(file\s+layouts?|code\s+sets?|resources?|links?)\b",
    r"\bfile\s+layouts?\b.*\b(dese|mosis|core\s+data|2025|2026)\b",
    r"\bcode\s+sets?\b.*\b(dese|mosis|core\s+data|2025|2026)\b",
    r"\basmnt\b.*\b(subject|codes?)\b",
    r"\b(subject|codes?)\b.*\basmnt\b",
    r"\bschool\s+finance\b.*\b(dese|resources?|links?|budget|salary|accounting|fund)\b",
    r"\bminimum\s+teachers?\s+salary\b",
    r"\bteachers?\s+salary\b.*\b(20\d{2}|link|dese|school)\b",
    r"\bspecial\s+education\s+data\b.*\b(dese|resources?|reports?|links?)\b",
]
HEALTH_LOOKUP_PATTERNS = [
    r"\bcommunicable\s+disease\b",
    r"\bdisease\s+report\b",
    r"\bcurrent\s+week\s+ytd\b",
    r"\brate\s+per\s+100k\b",
    r"\banaplasmosis\b",
    r"\bsalmonellosis\b",
    r"\bpertussis\b",
    r"\bcampylobacteriosis\b",
    r"\behrlichiosis\b",
    r"\bgiardiasis\b",
    r"\blegionellosis\b",
    r"\bvaricella\b",
    r"\bpublic\s+health\b.*\b(indexed|lookup|exact)\b",
    r"\bhealth\b.*\b(indexed|lookup|exact)\b",
]
HOSPITAL_PROFILE_LOOKUP_PATTERNS = [
    r"\bprofile\s+of\s+hospitals?\b",
    r"\bhospital\s+profile\b",
    r"\bprocessed\s+hospital\s+profile\s+source\b",
    r"\bq8me-hzr8\b",
    r"\bhospital\b.*\b(licensed\s+beds?|icu\s+beds?|med(?:ical)?/?surg(?:ical)?|pediatric|psych|rehab|ob\s+beds?|neonatal|nicu|license\s+type|facility\s+type|accredited|region|facility|facilities|coverage|indexed|source)\b",
    r"\b(licensed\s+beds?|icu\s+beds?)\b.*\bhospital\b",
    r"\bwhich\s+hospitals?\b.*\b(most|largest|highest|licensed\s+beds?|icu\s+beds?)\b",
]
DHSS_HEALTH_SOURCE_LOOKUP_PATTERNS = [
    r"\bdhss\b.*\b(health|public\s+health|resources?|links?|indexed|mica|mophims|profiles?|brfss|births?|deaths?|vital|hospitalizations?|patient\s+abstract|pas|county[-\s]+level|focus)\b",
    r"\b(health|public\s+health)\b.*\b(dhss|resources?|links?|source|sources|indexed|mica|mophims|profiles?|brfss)\b",
    r"\b(county\s+health|community\s+data)\s+profiles?\b",
    r"\bmophims\b|\bmica\b",
    r"\bbrfss\b|\bbehavioral\s+risk\s+factor\b",
    r"\bpatient\s+abstract\b|\bhospitalizations?\b.*\b(dhss|pas|mica|source|link|data)\b",
    r"\b(live\s+births?|birth\s+data|death\s+data|vital\s+statistics|focus\s+reports?)\b.*\b(dhss|health|source|link|indexed|data)\b",
]
DHSS_BRFSS_LOOKUP_PATTERNS = [
    r"\bbrfss\b.*\b(percent|percentage|prevalence|rate|estimate|value|obesity|diabetes|asthma|smoking|cigarette|coverage|binge|drinking|cholesterol|blood pressure|dentist|mammogram|influenza|stroke|copd|kidney|arthritis|screening|indexed|highest|lowest)\b",
    r"\bbehavioral\s+risk\s+factor\b.*\b(percent|percentage|prevalence|rate|estimate|value|indexed|highest|lowest)\b",
    r"\b(obesity|diabetes|current\s+asthma|current\s+cigarette\s+smoking|no\s+health\s+care\s+coverage|binge\s+drinking|high\s+blood\s+pressure|high\s+cholesterol|visited\s+a\s+dentist)\b.*\bbrfss\b",
]
DHSS_VITAL_STATS_LOOKUP_PATTERNS = [
    r"\b(dhss|missouri|statewide)\b.*\b(vital\s+statistics|live\s+births?|births?|deaths?|natural\s+increase|infant\s+deaths?)\b.*\b(aggregate|indexed|data|count|counts|total|totals|reported|latest|year|source|rate)\b",
    r"\b(vital\s+statistics|live\s+births?|births?|deaths?|natural\s+increase|infant\s+deaths?)\b.*\b(dhss|missouri|statewide)\b.*\b(aggregate|indexed|data|count|counts|total|totals|reported|latest|year|source|rate)\b",
    r"\bhow\s+many\s+(live\s+births?|births?|deaths?)\b.*\bmissouri\b",
    r"\bindexed\s+missouri\s+statewide\s+births?\s+and\s+deaths?\b",
]
DHSS_MOPHIMS_PROFILES_LOOKUP_PATTERNS = [
    r"\bmophims\b.*\b(profile|profiles|count|counts|rate|rates|value|values|indexed|coverage|hospitalizations?|inpatient|emergency\s+room|er\s+visits?|leading\s+causes?|chronic\s+disease|child\s+health|septicemia|heart\s+disease|diabetes|county)\b",
    r"\b(inpatient\s+hospitalizations?|emergency\s+room\s+visits?|er\s+visits?|leading\s+causes?\s+of\s+death|chronic\s+disease\s+comparisons?|child\s+health\s+profile)\b.*\b(mophims|dhss|profile|count|rate|statewide|county|indexed)\b",
    r"\bhow\s+many\b.*\b(inpatient\s+hospitalizations?|emergency\s+room\s+visits?)\b.*\bmissouri\b",
    r"\bsepticemia\b.*\b(hospitalizations?|mophims|dhss|profile|count|rate|county)\b",
    r"\b(boone|cole|greene|jackson|st\.?\s+louis)\s+(county|city)\b.*\b(inpatient|hospitalizations?|septicemia|mophims|dhss|profile|causes?\s+of\s+death|deaths?|mortality|heart\s+disease|cancer|stroke|suicide|homicide)\b",
    r"\b(causes?\s+of\s+death|deaths?|mortality|heart\s+disease|cancer|stroke|suicide|homicide)\b.*\b(boone|cole|greene|jackson|st\.?\s+louis)\s+(county|city)\b",
]
MEC_RESOURCES_LOOKUP_PATTERNS = [
    r"\bmec\b.*\b(indexed|lookup|data|reports?|resources?|links?|campaign|finance|lobbying|lobbyist|committee|commission|actions?|advisory|opinions?|financial\s+disclosure|pfd|forms?|annual\s+report)\b",
    r"\bethics\s+commission\b.*\b(indexed|lookup|data|reports?|resources?|links?|campaign|finance|lobbying|lobbyist|committee|commission|actions?|advisory|opinions?|financial\s+disclosure|pfd|forms?|annual\s+report)\b",
    r"\bcampaign\s+finance\b.*\b(mec|ethics|committee|contribution|expenditure|reports?|search|lookup|link|indexed)\b",
    r"\blobby(?:ing|ist)\b.*\b(mec|ethics|search|reports?|principal|link|indexed)\b",
    r"\bcommission\s+(actions?|cases?)\b.*\b(mec|ethics|search|link|indexed)\b",
    r"\badvisory\s+opinions?\b.*\b(mec|ethics|search|link|indexed)\b",
]
MEC_ANNUAL_REPORT_LOOKUP_PATTERNS = [
    r"\bmec\b.*\b(annual\s+report|registered\s+lobbyists?|campaign\s+finance\s+activity|registered\s+campaign\s+finance\s+committees?|large\s+contributions?|receipts?\s+reported|personal\s+financial\s+disclosure|pfd|subdivisions?|ordinances?|operating\s+budget)\b.*\b(total|count|how\s+many|how\s+much|amount|receipts?|expenditures?|registered|highest|largest|most|top|data|indexed|coverage|20\d{2})\b",
    r"\b(which|what|how\s+many|how\s+much)\b.*\b(candidate\s+positions?|state\s+candidate|receipts?|expenditures?|registered\s+lobbyists?|campaign\s+finance|large\s+contributions?|pfd|personal\s+financial\s+disclosure|subdivisions?|ordinances?|operating\s+budget)\b.*\bmec\s+annual\s+report\b",
    r"\bethics\s+commission\b.*\b(annual\s+report|registered\s+lobbyists?|campaign\s+finance\s+activity|large\s+contributions?|receipts?\s+reported|pfd|subdivisions?|ordinances?|operating\s+budget)\b.*\b(total|count|how\s+many|how\s+much|amount|highest|largest|most|top|20\d{2})\b",
    r"\bcampaign\s+finance\b.*\b(total|receipts?|expenditures?|registered\s+committees?|large\s+contributions?|amount|how\s+much|how\s+many|highest|largest|top)\b.*\b(mec|ethics|annual\s+report|20\d{2})\b",
    r"\b(registered\s+)?lobbyists?\b.*\b(count|how\s+many|registered|total|mec|ethics|annual\s+report|20\d{2})\b",
    r"\bpfd\b.*\b(subdivisions?|school\s+districts?|city|village|county|ordinances?|operating\s+budget|count|how\s+many|total|20\d{2})\b",
    r"\bpersonal\s+financial\s+disclosure\b.*\b(subdivisions?|school\s+districts?|city|village|county|ordinances?|operating\s+budget|count|how\s+many|total|20\d{2})\b",
]
WIC_LOOKUP_PATTERNS = [
    r"\bwic\b",
    r"\bwomen\s+infants\s+(?:and\s+)?children\b",
    r"\bnutrition\s+benefits?\b",
]
FOOD_PANTRY_LOOKUP_PATTERNS = [
    r"\bfood\s+pantr(?:y|ies)\b",
    r"\bfood\s+bank\b",
    r"\bfood\s+pantry\s+list\b",
    r"\bmissouri\s+food\s+pantr(?:y|ies)\b",
    r"\bdata\.mo\.gov\b.*\beb3y-vtsa\b",
    r"\beb3y-vtsa\b",
    r"\bcentral\s+pantry\b",
    r"\bwhere\b.*\bfood\s+(?:help|assistance)\b",
]
FARMERS_MARKET_LOOKUP_PATTERNS = [
    r"\bfarmers?'?\s+markets?\b",
    r"\bfarm\s+markets?\b",
    r"\bmissouri\s+farmers?'?\s+markets?\b",
    r"\bdata\.mo\.gov\b.*\b2zg8-cta8\b",
    r"\b2zg8-cta8\b",
    r"\bkiwanis\s+club\s+of\s+kirksville\b",
]
LTC_LOOKUP_PATTERNS = [
    r"\bltc\b",
    r"\blong[-\s]+term\s+care\b",
    r"\bnursing\s+homes?\b",
    r"\bassisted\s+living\b",
    r"\bresidential\s+care\b",
    r"\bskilled\s+nursing\b",
    r"\bltc\s+census\b",
    r"\bltc\s+directory\b",
]
DHSS_LTC_INSPECTION_LOOKUP_PATTERNS = [
    r"\b(dhss|show\s+me|showme|long[-\s]+term\s+care|ltc|nursing\s+homes?)\b.*\b(inspection|inspections|inspected|survey|complaint|complaints|scope|severity|class\s+i|class\s+ii|class\s+iii|resources?|links?|indexed|lookup|county\s+filter|city\s+filter|facility\s+types?|show\s+me\s+long[-\s]+term\s+care)\b",
    r"\bwhere\b.*\b(ltc|long[-\s]+term\s+care|nursing\s+home)\b.*\b(inspection|survey|complaint|look\s+up|lookup)\b",
    r"\b(show\s+me|showme)\s+long[-\s]+term\s+care\b",
]
DNR_WATER_LOOKUP_PATTERNS = [
    r"\bconsumer\s+confidence\s+report\b",
    r"\bpublic\s+drinking\s+water\b",
    r"\bdrinking\s+water\s+systems?\b",
    r"\b(?:public\s+)?water\s+systems?\b",
    r"\bwater\s+systems?\b.*\b(indexed|lookup|count|pwsid)\b",
    r"\bpwsid\b",
    r"\bdnr\b.*\bwater\b.*\b(indexed|lookup|count|systems?)\b",
]
DNR_OIL_GAS_LOOKUP_PATTERNS = [
    r"\bdnr\b.*\b(oil\s+and\s+gas|oil\s*&\s*gas|oil|gas)\b.*\b(permit|permits|well|wells|operator|operators|company|county|count|status|pdf|indexed|lookup|data)\b",
    r"\b(oil\s+and\s+gas|oil\s*&\s*gas)\b.*\b(dnr|permit|permits|well|wells|operator|operators|company|county|count|status|pdf|indexed|lookup|data)\b",
    r"\b(?:permit|ogc)\s*\d{3}-\d{5}\b",
    r"\b\d{3}-\d{5}\b.*\b(oil|gas|dnr|permit|well)\b",
    r"\b(available|active|abandoned|plugged|shut[-\s]+in)\b.*\b(oil\s+and\s+gas|oil\s*&\s*gas)\b.*\b(permits?|wells?)\b",
]
DNR_HAZARDOUS_WASTE_LOOKUP_PATTERNS = [
    r"\bdnr\b.*\b(hazardous\s+waste|tsd|treatment\s*,?\s*storage\s*(?:and|&)?\s*disposal|waste\s+facilit(?:y|ies))\b.*\b(facilit(?:y|ies)|epa\s+id|county|count|status|region|indexed|lookup|data)\b",
    r"\b(hazardous\s+waste|tsd|treatment\s*,?\s*storage\s*(?:and|&)?\s*disposal|waste\s+facilit(?:y|ies))\b.*\b(dnr|facilit(?:y|ies)|epa\s+id|county|count|status|region|indexed|lookup|data)\b",
    r"\bepa\s+id\s+mod\d{9}\b",
    r"\bmod\d{9}\b",
    r"\b(permitted|interim\s+status|other)\b.*\b(hazardous\s+waste|tsd|waste\s+facilit(?:y|ies))\b",
]
DNR_IMPAIRED_WATERS_LOOKUP_PATTERNS = [
    r"\bdnr\b.*\b(impaired\s+waters?|303\s*d|303d|tmdl|pollutants?|waterbod(?:y|ies)|listed\s+waters?)\b",
    r"\b(impaired\s+waters?|303\s*d|303d|tmdl|listed\s+waters?)\b.*\b(missouri|dnr|county|count|pollutants?|waterbod(?:y|ies)|high[-\s]+priority)\b",
    r"\b(pollutants?|county|count|how\s+many|high[-\s]+priority)\b.*\b(impaired\s+waters?|303\s*d|303d|tmdl|listed\s+waters?)\b",
    r"\b(is|are|what|which|how\s+many)\b.*\b(?:bass|hinkson|gans|big)\b.*\b(?:creek|cr\.|cr|river|r\.|r|listed|impaired)\b",
]
DNR_RESOURCES_LOOKUP_PATTERNS = [
    r"\bdnr\b.*\b(resources?|links?|data\s+and\s+e-services|e-services|permits?|certifications?|registrations?|licenses?|forms?|applications?|public\s+notices?|impaired|water\s+quality|gis|maps?|viewer|mocwis|mogem|lims|wims|geostrat|geoedge|air|emissions?|waste|recycling|energy)\b",
    r"\bmissouri\s+dnr\b.*\b(resources?|links?|lookup|indexed|e-services|permits?|impaired|water\s+quality|gis|maps?|viewer|air|waste|recycling|energy)\b",
    r"\b(impaired\s+waters?|water\s+quality|mocwis|mogem|lims|wims|geostrat|geoedge|e-start|drinking\s+water\s+viewer|missouri\s+clean\s+water\s+information)\b",
    r"\b(environmental|water|air|waste|geology|energy)\b.*\b(dnr|resources?|links?|e-services|permits?|maps?|lookup|indexed)\b",
]
MSDIS_GEOSPATIAL_LOOKUP_PATTERNS = [
    r"\bmsdis\b.*\b(indexed|lookup|exact|resources?|links?|datasets?|data|gis|geospatial|spatial|boundar(?:y|ies)|imagery|lidar|elevation|arcgis|rest|services?|open\s+data|archive)\b",
    r"\bmissouri\s+spatial\s+data\s+information\s+service\b",
    r"\bmissouri\s+(?:gis|geospatial|spatial)\b.*\b(indexed|lookup|resources?|links?|datasets?|open\s+data|arcgis|services?)\b",
    r"\bmsdis\b.*\b(county|municipal|boundary|boundaries|vector|feature\s+service|map\s+service|image\s+service)\b",
]
MODOT_AADT_LOOKUP_PATTERNS = [
    r"\bmodot\b.*\b(aadt|traffic\s+volume|traffic\s+count|traffic\s+counts|indexed|lookup|exact|route|segment|highest|busiest)\b",
    r"\b(aadt|traffic\s+volume|traffic\s+count|traffic\s+counts)\b.*\b(modot|i[-\s]?\d{1,3}|interstate\s+\d{1,3}|us\s+\d{1,3}|mo\s+\d{1,3}|route\s+\d{1,3})\b",
    r"\b(highest|busiest|top)\b.*\b(aadt|traffic\s+volume|traffic\s+count)\b",
]
UTILITY_LOOKUP_PATTERNS = [
    r"\bfind\s+a\s+missouri\s+utility\b",
    r"\butilities\s+serve\b",
    r"\butility\s+providers?\b",
    r"\belectric\s+utilit(?:y|ies)\b",
    r"\bgas\s+utilit(?:y|ies)\b",
    r"\bwater\s+utilit(?:y|ies)\b",
    r"\btelephone\s+providers?\b",
    r"\bwhat\s+utilities\b",
    r"\butility\s+(?:rows?|table)\b",
    r"\butility\b.*\b(indexed|lookup|data|provider|providers|serve|serves)\b",
    r"\butilities\b.*\b(indexed|lookup|data|provider|providers|serve|serves)\b",
]
AGRICULTURE_LOOKUP_PATTERNS = [
    r"\bfeed\s+sample(?:s)?\b",
    r"\bfeed\s+testing\b",
    r"\bfeed\s+class(?:es)?\b",
    r"\bsample\s+D\d{9}\b",
    r"\bD\d{9}\b",
    r"\bprotein\b.*\bsample\b",
    r"\b(poultry|beef|swine|horse|goat)\s+feed\b",
    r"\bagriculture\b.*\b(indexed|lookup|exact|feed|sample|testing)\b",
]
AG_MARKET_NEWS_LOOKUP_PATTERNS = [
    r"\bag(?:ricultural|riculture)?\s+market\s+reports?\b",
    r"\bagricultural\s+market\s+news\b",
    r"\bagmarketnews\b",
    r"\bmarket\s+news\b.*\b(agriculture|agricultural|cattle|livestock|swine|hog|pig|sheep|goat|hay|forage|grain|feedstuff)\b",
    r"\b(cattle|livestock|swine|hog|pig|sheep|goat|hay|forage|grain|feedstuff|heifer)\b.*\b(market\s+reports?|report\s+links?|indexed|auction|summary|ams_\d{4})\b",
    r"\bams_\d{4}\b",
    r"\bjoplin\s+regional\s+stockyards\b",
]
AG_MARKET_REPORT_DOCUMENT_LOOKUP_PATTERNS = [
    r"\b(?:explain|summarize|summary|plain[-\s]+english|what does|what is inside|find|search|mentions?|snippet|document text|pdf text)\b.*\b(?:agricultural\s+market|agriculture\s+market|market\s+news|joplin|hay|grain|cattle|livestock)\b.*\b(?:report|pdf|document)\b",
    r"\b(?:agricultural\s+market|agriculture\s+market|market\s+news|joplin|hay|grain|cattle|livestock)\b.*\b(?:report|pdf|document)\b.*\b(?:document text|pdf text|explain|summarize|summary|plain[-\s]+english|find|search|mentions?|snippet|inside|price|prices|range|receipts?|demand|suppl(?:y|ies))\b",
    r"\bmissouri\s+(?:direct\s+)?hay\s+report\b",
    r"\bmissouri\s+hay\s+market\s+report\b",
    r"\b(?:alfalfa|mixed\s+grass|straw)\b.*\b(?:price|prices|range|ranges|per\s+ton|per\s+bale)\b",
    r"\bshould\s+i\s+(?:buy|sell|trade)\b.*\bhay\b",
    r"\bhay\b.*\b(?:buying|selling|trading)\s+advice\b",
    r"\bjoplin\b.*\b(?:receipts?|price|prices|steers?|feeder\s+cattle)\b",
]
CANNABIS_LOOKUP_PATTERNS = [
    r"\bcannabis\b.*\b(indexed|lookup|exact|dispensar(?:y|ies)|facility|facilities|annual|report|sales|tax|microbusiness|license|licenses)\b",
    r"\bmarijuana\b.*\b(indexed|lookup|exact|dispensar(?:y|ies)|facility|facilities|annual|report|sales|tax|microbusiness|license|licenses)\b",
    r"\bverified\s+dispensar(?:y|ies)\b",
    r"\bdispensar(?:y|ies)\b.*\b(count|county|city|license|listed|verified|most|how many)\b",
    r"\bdis\d{6}\b",
    r"\bmicrobusiness\s+licenses?\b",
    r"\badult[-\s]+use\s+cannabis\b",
    r"\bPY2[234]\b.*\b(cannabis|marijuana|adult-use|medical|microbusiness|sales|tax|veterans|reinvestment|agent)\b",
    r"\b20(?:22|23|24)\b.*\b(cannabis|marijuana|adult-use|medical|microbusiness|sales|tax|veterans|reinvestment|agent)\b",
]
CHILD_CARE_LOOKUP_PATTERNS = [
    r"\bchild\s+care\b.*\b(indexed|lookup|exact|dashboard|dashboards|slots?|facilit(?:y|ies)|pending|inspections?|complaints?|licensed|licensure|centers?|homes?)\b",
    r"\bchildcare\b.*\b(indexed|lookup|exact|dashboard|dashboards|slots?|facilit(?:y|ies)|pending|inspections?|complaints?|licensed|licensure|centers?|homes?)\b",
    r"\bchild\s+care\s+compliance\b",
    r"\bchild\s+care\s+dashboard\b",
    r"\bdaycare\b.*\b(slots?|inspection|complaint|licensed|licensure|dashboard)\b",
    r"\bcomplaint\s+investigations?\b.*\b(20\d{2}|q[1-4]|quarter|child\s+care|childcare)\b",
    r"\binspections?\b.*\b(20\d{2}|q[1-4]|quarter)\b.*\b(child\s+care|childcare)?\b",
    r"\blicensed\b.*\b(less than 6|under 6|6 to 12|6 - 12|more than 12|over 12)\b.*\b(20\d{2}|q[1-4]|quarter)\b",
    r"\b20\d{2}\s+q[1-4]\b.*\b(child\s+care|childcare|slots?|inspection|complaint|licensed|pending)\b",
    r"\bq[1-4]\s+20\d{2}\b.*\b(child\s+care|childcare|slots?|inspection|complaint|licensed|pending)\b",
]
PSC_REPORTS_LOOKUP_PATTERNS = [
    r"\bpsc\b.*\b(reports?|volume|vol\.?|indexed|lookup|data|pdf|coverage|latest|newest|recent)\b",
    r"\bpublic\s+service\s+commission\b.*\b(reports?|volume|vol\.?|indexed|lookup|data|pdf|coverage|latest|newest|recent)\b",
    r"\bmissouri\s+psc\s+reports?\b",
    r"\bpsc\s+reports?\s+vol\b",
    r"\bvol(?:ume)?\.?\s*\d{1,2}\b.*\b(psc|public\s+service\s+commission)\b",
]
PSC_REPORT_DOCUMENT_LOOKUP_PATTERNS = [
    r"\b(?:explain|summarize|summary|plain[-\s]+english|what does|what is inside|find|search|mentions?|snippet)\b.*\b(?:psc|public\s+service\s+commission)\b.*\b(?:report|volume|vol\.?|pdf|document)\b",
    r"\b(?:psc|public\s+service\s+commission)\b.*\b(?:report|volume|vol\.?|pdf|document)\b.*\b(?:document text|pdf text|explain|summarize|summary|plain[-\s]+english|find|search|mentions?|snippet|inside)\b",
    r"\bpsc\s+report\s+document\s+text\b",
    r"\bpsc\s+report\s+volume\s+\d{1,2}\b.*\b(?:explain|summarize|summary|plain[-\s]+english|find|search|mentions?|snippet|inside)\b",
]
OA_BUDGET_LOOKUP_PATTERNS = [
    r"\boa\s+budget\b.*\b(indexed|lookup|data|metadata|executive|summary|revenue|performance|demographic|redistrict|appropriation|fringe|link|pdf|latest)\b",
    r"\bbudget\s+and\s+planning\b.*\b(indexed|lookup|data|metadata|executive|summary|revenue|performance|demographic|redistrict|appropriation|fringe|link|pdf|latest)\b",
    r"\bexecutive\s+budget\b.*\b(fy\s*\d{2,4}|20\d{2}|latest|link|pdf|budget\s+and\s+planning|oa)\b",
    r"\bbudget\s+summary\b.*\b(fy\s*\d{2,4}|20\d{2}|link|pdf|budget\s+and\s+planning|oa)\b",
    r"\bappropriation\s+bills?\b.*\b(fy\s*\d{2,4}|20\d{2}|budget\s+and\s+planning|oa)\b",
    r"\b(revenue\s+information|general\s+revenue|revenue\s+detail)\b.*\b(20\d{2}|january|february|march|april|may|june|july|august|september|october|november|december|budget\s+and\s+planning|oa)\b",
    r"\bperformance\s+measure(?:s)?\b.*\b(resource|resources|budget|oa|indexed|lookup|data)\b",
    r"\b(redistricting|demographic|census|population)\b.*\b(oa|budget\s+and\s+planning|indexed|lookup|data|resource|resources)\b",
]
OA_REVENUE_DETAIL_LOOKUP_PATTERNS = [
    r"\boa\b.*\brevenue\s+detail\b.*\b(indexed|connected|coverage|data|available|source|sources)\b",
    r"\brevenue\s+detail\b.*\b(oa|budget\s+and\s+planning)\b.*\b(indexed|connected|coverage|data|available|source|sources)\b",
    r"\b(general\s+revenue|revenue\s+detail|net\s+general\s+revenue|net\s+of\s+refunds)\b.*\b(20\d{2}|fy\s*\d{2,4}|latest|current|january|february|march|april|may|june|july|august|september|october|november|december|collections?|refunds?|tax|year[-\s]+to[-\s]+date|ytd)\b",
    r"\b(sales\s+and\s+use\s+tax|individual\s+income\s+tax|corporate\s+income|pass[-\s]+through\s+entity\s+tax|total\s+collections|total\s+refunds)\b.*\b(20\d{2}|fy\s*\d{2,4}|general\s+revenue|revenue\s+detail|january|february|march|april|may|june|july|august|september|october|november|december)\b",
    r"\b(20\d{2}|fy\s*\d{2,4}|january|february|march|april|may|june|july|august|september|october|november|december)\b.*\b(sales\s+and\s+use\s+tax|individual\s+income\s+tax|corporate\s+income|pass[-\s]+through\s+entity\s+tax|total\s+collections|total\s+refunds)\b",
    r"\b(fy\s*\d{2,4}|fiscal\s+year\s+20\d{2})\b.*\b(year[-\s]+to[-\s]+date|ytd)\b.*\b(collections?|refunds?|revenue)\b",
    r"\bwhat\s+(?:were|was)\b.*\bmissouri\b.*\b(revenue|collections)\b.*\b(20\d{2}|fy\s*\d{2,4}|january|february|march|april|may|june|july|august|september|october|november|december)\b",
]
AUDITOR_LOOKUP_PATTERNS = [
    r"\bauditor\b",
    r"\bstate\s+auditor\b",
    r"\baudit\s+reports?\b",
    r"\baudit\s+metadata\b",
    r"\breport\s+20\d{2}[-\s]?\d{3}\b",
]
AUDITOR_DOCUMENT_LOOKUP_PATTERNS = [
    r"\b(?:explain|summarize|summary|plain[-\s]+english|what does)\b.*\b(?:auditor|audit report|state auditor|report\s+20\d{2}[-\s]?\d{3})\b",
    r"\b(?:auditor|audit report|state auditor)\b.*\b(?:document text|pdf text|pdfs?|explain|summarize|summary|plain[-\s]+english|findings?|recommendations?)\b",
    r"\breport\s+20\d{2}[-\s]?\d{3}\b.*\b(?:explain|summarize|summary|plain[-\s]+english|findings?|recommendations?)\b",
]
SOS_ELECTION_LOOKUP_PATTERNS = [
    r"\bsos\b.*\belection\b",
    r"\bsecretary\s+of\s+state\b.*\belection\b",
    r"\belection\s+(?:results?|returns?|data)\b",
    r"\bofficial\s+election\s+returns?\b",
    r"\bwho\s+won\b.*\belection\b",
    r"\bwho\s+won\b.*\bprimary\b",
    r"\bhow\s+many\s+votes\b.*\belection\b",
    r"\bhow\s+many\s+votes\b.*\bprimary\b",
    r"\bhow\s+many\s+votes\b.*\b(county|city|governor|president)\b.*\b20\d{2}\b",
    r"\btotal\s+votes\b.*\belection\b",
    r"\bvotes\s+cast\b.*\belection\b",
    r"\b(?:voter\s+)?turnout\b.*\b(20\d{2}|election|county|city|missouri)\b",
    r"\b(20\d{2}|election|county|city|missouri)\b.*\b(?:voter\s+)?turnout\b",
    r"\bregistered\s+voters\b.*\b(20\d{2}|election|county|city|missouri)\b",
    r"\bwho\s+won\b.*\b(county|city|governor|president)\b.*\b20\d{2}\b",
    r"\b(?:general|primary)\s+election\b",
]
EXPANDED_SOURCE_PATTERNS = [
    r"\bdata\.mo\.gov\b",
    r"\bdese\b",
    r"\bschool\s+data\b",
    r"\bdhss\b",
    r"\bpublic\s+health\b",
    r"\bmshp\b",
    r"\btraffic\s+safety\b",
    r"\bcrash(?:es)?\b",
    r"\bmeric\b",
    r"\blabor\s+market\b",
    r"\bdnr\b",
    r"\benvironment(?:al)?\b",
    r"\bwater\s+(?:data|permit|quality|system)",
    r"\bmsdis\b",
    r"\bgeospatial\b",
    r"\bgis\b",
    r"\bmodot\b",
    r"\btraffic\s+(?:count|volume|data)",
    r"\bauditor\b",
    r"\baudit\s+reports?\b",
    r"\bdor\b",
    r"\bdepartment\s+of\s+revenue\b",
    r"\brevenue\s+reports?\b",
    r"\btaxable\s+sales\b",
    r"\bmec\b",
    r"\bethics\s+commission\b",
    r"\bcampaign\s+finance\b",
    r"\blobby(?:ing|ist)\b",
    r"\bsos\b",
    r"\bsecretary\s+of\s+state\b",
    r"\belection\s+(?:data|results?)\b",
    r"\boa\s+budget\b",
    r"\bbudget\s+and\s+planning\b",
    r"\bperformance\s+measures?\b",
    r"\bchild\s+care\b",
    r"\bchildcare\b",
    r"\blong[-\s]+term\s+care\b",
    r"\bnursing\s+homes?\b",
    r"\bpsc\b",
    r"\bpublic\s+service\s+commission\b",
    r"\butilit(?:y|ies)\b",
    r"\bcannabis\b",
    r"\bmarijuana\b",
    r"\bagricultur(?:e|al)\b",
    r"\bmarket\s+reports?\b",
]
MAP_INVENTORY_PATTERNS = [r"\bhow many\b.*\bmap\b.*\bfiles?\b", r"\bmap\b.*\bcategories\b", r"\bdownloaded\b.*\bfiles?\b"]
HELP_PATTERNS = [
    r"^\s*help\s*$",
    r"\bwhat can (you|i) ask\b",
    r"\bwhat do you cover\b",
    r"\bwhat datasets\b",
    r"\bcapabilities\b",
]
MISSOURI_GOVERNOR_PATTERNS = [
    r"\bwho(?:\s+is|'s)?\s+(?:the\s+)?(?:governor|govenor)\s+of\s+(?:missouri|mo)\b",
    r"\b(?:missouri|mo)\s+(?:governor|govenor)\b",
    r"\b(?:governor|govenor)\s+of\s+(?:missouri|mo)\b",
]
MISSOURI_CAPITAL_PATTERNS = [
    r"\bwhat(?:\s+is|'s)?\s+(?:the\s+)?(?:state\s+)?capital\s+of\s+(?:missouri|mo)\b",
    r"\b(?:missouri|mo)(?:'s)?\s+(?:state\s+)?capital\b",
    r"\bwhere\s+is\s+(?:the\s+)?(?:missouri|mo)\s+(?:state\s+)?capitol\b",
]
MAP_DEFINITION_PATTERNS = [
    r"\bwhat(?:\s+is|'s)?\s+(?:the\s+)?(?:missouri\s+)?(?:accountability\s+portal|map)\b",
    r"\bexplain\s+(?:the\s+)?(?:missouri\s+)?(?:accountability\s+portal|map)\b",
]
TOP_PATTERNS = [r"\btop\b", r"\blargest\b", r"\bhighest\b", r"\bbiggest\b", r"\bmost\b"]
PUBLIC_DATA_TERMS = [
    "missouri",
    "state",
    "map",
    "public data",
    "hospital",
    "ltc",
    "census",
    "expenditure",
    "vendor",
    "employee",
    "salary",
    "tax credit",
    "federal grant",
    "budget",
    "bond",
    "stimulus",
]
UNSUPPORTED_PATTERNS = [
    r"\bforecast\b",
    r"\bpredict\b",
    r"\bprojection\b",
    r"\bactive contract\b",
    r"\bcurrent contract\b",
    r"\bendorse(?:d|ment)?\b",
    r"\blist every row\b",
    r"\blist every (payment|transaction|person|employee)\b",
    r"\b(all|every) (payment|payments|transaction|transactions|person|people|employee|employees)\b",
    r"\ball rows\b",
    r"\bdump\b.*\brows?\b",
    r"\bvendor\s+id\b",
    r"\boverpay(?:ment|ments|ing|ed)?\b",
]

NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def clean_answer_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def load_knowledge_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in [
        PROJECT_ROOT / "data" / "qa" / "train.jsonl",
        PROJECT_ROOT / "data" / "qa" / "eval.jsonl",
        PROJECT_ROOT / "data" / "qa" / "train_map_run_002.jsonl",
        PROJECT_ROOT / "data" / "qa" / "eval_map_run_002.jsonl",
        PROJECT_ROOT / "data" / "eval" / "evaluation_prompts.jsonl",
    ]:
        if path.exists():
            for row in read_jsonl(path):
                answer = row.get("answer") or row.get("expected_answer", "")
                rows.append(
                    {
                        "id": row["id"],
                        "source": row["source"],
                        "question": row["question"],
                        "context": row["context"],
                        "answer": answer,
                    }
                )
    return rows


def contains_private_identifier_request(question: str) -> bool:
    lowered = question.lower()
    if re.search(r"\b(food\s+pantr(?:y|ies)|food\s+bank|central\s+pantry)\b", lowered) and any(
        term in lowered for term in ["phone", "address", "hours", "where", "located", "location"]
    ):
        return False
    return any(re.search(pattern, lowered) for pattern in PRIVATE_IDENTIFIER_PATTERNS)


def asks_about_salary_scope(question: str) -> bool:
    lowered = question.lower()
    return any(re.search(pattern, lowered) for pattern in SALARY_SCOPE_PATTERNS)


def asks_about_vendor_lookup(question: str) -> bool:
    lowered = question.lower()
    if "agency" in lowered or "agencies" in lowered:
        return bool(re.search(r"\bvendors?\b", lowered))
    if any(re.search(pattern, lowered) for pattern in VENDOR_LOOKUP_PATTERNS):
        return True
    if re.search(r"\bpaid\s+[A-Z0-9& ]{4,}\b", question) and re.search(
        r"\b(llc|inc|corp|corporation|co|company|bank|na)\b", lowered
    ):
        return True
    return False


def asks_about_contract_lookup(question: str) -> bool:
    lowered = question.lower()
    return any(re.search(pattern, lowered) for pattern in CONTRACT_LOOKUP_PATTERNS)


def asks_for_contract_explanation(question: str) -> bool:
    lowered = question.lower()
    return any(re.search(pattern, lowered) for pattern in CONTRACT_EXPLANATION_PATTERNS)


def asks_about_contract_document_index(question: str) -> bool:
    lowered = question.lower()
    return any(re.search(pattern, lowered) for pattern in CONTRACT_DOCUMENT_INDEX_PATTERNS)


def asks_for_contract_document_snippet(question: str) -> bool:
    lowered = question.lower()
    if "show" in lowered and "document link" in lowered:
        return False
    return any(re.search(pattern, lowered) for pattern in CONTRACT_DOCUMENT_SNIPPET_PATTERNS)


def asks_for_contract_payment_context(question: str) -> bool:
    lowered = question.lower()
    return any(re.search(pattern, lowered) for pattern in CONTRACT_PAYMENT_CONTEXT_PATTERNS)


def asks_about_public_source_catalog(question: str) -> bool:
    lowered = question.lower()
    return any(re.search(pattern, lowered) for pattern in PUBLIC_SOURCE_CATALOG_PATTERNS)


def asks_about_data_mo_catalog_lookup(question: str) -> bool:
    lowered = question.lower()
    return any(re.search(pattern, lowered) for pattern in DATA_MO_CATALOG_PATTERNS)


def asks_about_education_lookup(question: str) -> bool:
    lowered = question.lower()
    if "dese" in lowered and any(term in lowered for term in ["connected", "source", "sources", "available"]):
        return False
    if ("dese" in lowered and "directory" in lowered) or any(
        term in lowered for term in ["county-district", "grade span"]
    ):
        return False
    return any(re.search(pattern, lowered) for pattern in EDUCATION_LOOKUP_PATTERNS)


def asks_about_dese_directory_lookup(question: str) -> bool:
    lowered = question.lower()
    if any(term in lowered for term in ["connected", "source", "sources", "available"]) and "indexed" not in lowered:
        return False
    return any(re.search(pattern, lowered) for pattern in DESE_DIRECTORY_LOOKUP_PATTERNS)


def asks_about_dese_apr_lookup(question: str) -> bool:
    lowered = question.lower()
    if "child care" in lowered or "childcare" in lowered:
        return False
    if any(term in lowered for term in ["link", "links", "resource", "resources"]):
        return False
    return any(re.search(pattern, lowered) for pattern in DESE_APR_LOOKUP_PATTERNS)


def asks_about_dese_finance_lookup(question: str) -> bool:
    lowered = question.lower()
    if "child care" in lowered or "childcare" in lowered:
        return False
    if any(term in lowered for term in ["link", "links", "resource", "resources"]) and not any(
        term in lowered for term in ["amount", "highest", "largest", "indexed", "coverage", "what data"]
    ):
        return False
    return any(re.search(pattern, lowered) for pattern in DESE_FINANCE_LOOKUP_PATTERNS)


def asks_about_dese_special_education_lookup(question: str) -> bool:
    lowered = question.lower()
    if any(term in lowered for term in ["child care", "childcare"]):
        return False
    if any(term in lowered for term in ["link", "links", "resource", "resources"]) and not any(
        term in lowered
        for term in [
            "incidence",
            "child count",
            "count",
            "counts",
            "rate",
            "rates",
            "autism",
            "learning",
            "speech",
            "language",
            "enrollment",
            "indexed",
            "coverage",
            "what data",
        ]
    ):
        return False
    return any(re.search(pattern, lowered) for pattern in DESE_SPECIAL_EDUCATION_LOOKUP_PATTERNS)


def asks_about_dese_school_data_lookup(question: str) -> bool:
    lowered = question.lower()
    if "child care" in lowered or "childcare" in lowered:
        return False
    if any(term in lowered for term in ["connected", "source", "sources", "available"]) and not any(
        term in lowered
        for term in [
            "indexed",
            "lookup",
            "resource",
            "resources",
            "link",
            "links",
            "apr",
            "msip",
            "finance",
            "file layout",
            "code set",
        ]
    ):
        return False
    return any(re.search(pattern, lowered) for pattern in DESE_SCHOOL_DATA_LOOKUP_PATTERNS)


def asks_about_health_lookup(question: str) -> bool:
    lowered = question.lower()
    if "dhss" in lowered and any(term in lowered for term in ["connected", "source", "sources", "available"]):
        return False
    return any(re.search(pattern, lowered) for pattern in HEALTH_LOOKUP_PATTERNS)


def asks_about_hospital_profile_lookup(question: str) -> bool:
    lowered = question.lower()
    if any(term in lowered for term in ["mophims", "mica", "patient abstract", "pas", "hospitalization", "hospitalizations", "inpatient"]):
        return False
    if any(term in lowered for term in ["dataset", "datasets", "catalog", "mention"]) and "profile of hospitals" not in lowered:
        return False
    return any(re.search(pattern, lowered) for pattern in HOSPITAL_PROFILE_LOOKUP_PATTERNS)


def asks_about_dhss_health_sources_lookup(question: str) -> bool:
    lowered = question.lower()
    if any(term in lowered for term in ["child care", "childcare", "wic", "long-term care", "long term care", "ltc", "cannabis"]):
        return False
    if "dhss" not in lowered and not any(
        term in lowered
        for term in [
            "resource",
            "resources",
            "link",
            "links",
            "source",
            "sources",
            "brfss",
            "mica",
            "mophims",
            "profile",
            "profiles",
            "birth",
            "death",
            "hospital",
            "patient abstract",
            "pas",
            "vital",
            "focus",
        ]
    ):
        return False
    if "connected" in lowered and not any(term in lowered for term in ["indexed", "resource", "resources", "link", "links"]):
        return False
    return any(re.search(pattern, lowered) for pattern in DHSS_HEALTH_SOURCE_LOOKUP_PATTERNS)


def asks_about_dhss_brfss_lookup(question: str) -> bool:
    lowered = question.lower()
    if "brfss" not in lowered and "behavioral risk factor" not in lowered:
        return False
    if any(term in lowered for term in ["link", "links", "resource", "resources", "source", "sources"]) and not any(
        term in lowered
        for term in [
            "percent",
            "percentage",
            "prevalence",
            "rate",
            "estimate",
            "value",
            "indexed",
            "highest",
            "lowest",
            "obesity",
            "diabetes",
            "asthma",
            "smoking",
            "coverage",
            "binge",
            "drinking",
        ]
    ):
        return False
    return any(re.search(pattern, lowered) for pattern in DHSS_BRFSS_LOOKUP_PATTERNS)


def asks_about_dhss_vital_stats_lookup(question: str) -> bool:
    lowered = question.lower()
    if "focus report" in lowered or "focus reports" in lowered:
        return False
    if any(term in lowered for term in ["crash", "traffic", "fatal crash", "injury", "injuries", "fatality"]):
        return False
    has_measure = any(
        term in lowered
        for term in ["vital", "live birth", "birth", "births", "death", "deaths", "natural increase", "infant"]
    )
    has_scope = any(term in lowered for term in ["dhss", "missouri", "statewide", "vital"])
    has_fact_request = any(
        term in lowered
        for term in [
            "aggregate",
            "index",
            "indexed",
            "data",
            "count",
            "counts",
            "total",
            "totals",
            "reported",
            "latest",
            "year",
            "source",
            "rate",
            "how many",
        ]
    )
    if not (has_measure and has_scope and has_fact_request):
        return False
    if any(term in lowered for term in ["link", "links", "resource", "resources"]) and not any(
        term in lowered for term in ["aggregate", "index", "indexed", "count", "counts", "total", "totals", "reported"]
    ):
        return False
    return True


def asks_about_dhss_mophims_profiles_lookup(question: str) -> bool:
    lowered = question.lower()
    if any(term in lowered for term in ["crash", "traffic", "mshp", "vehicle"]):
        return False
    if "brfss" in lowered or "behavioral risk factor" in lowered:
        return False
    if "focus report" in lowered or "vital statistics" in lowered:
        return False
    return any(re.search(pattern, lowered) for pattern in DHSS_MOPHIMS_PROFILES_LOOKUP_PATTERNS)


def asks_about_mec_resources_lookup(question: str) -> bool:
    lowered = question.lower()
    return any(re.search(pattern, lowered) for pattern in MEC_RESOURCES_LOOKUP_PATTERNS)


def asks_about_mec_annual_report_lookup(question: str) -> bool:
    lowered = question.lower()
    if any(term in lowered for term in ["search link", "search links", "resource link", "form", "forms", "advisory opinion"]):
        return False
    if "annual report" in lowered and not any(
        term in lowered
        for term in [
            "indexed",
            "coverage",
            "what data",
            "what metrics",
            "total",
            "count",
            "how many",
            "how much",
            "amount",
            "receipt",
            "expenditure",
            "registered",
            "lobbyist",
            "campaign finance",
            "large contribution",
            "pfd",
            "personal financial disclosure",
            "subdivision",
            "ordinance",
            "operating budget",
            "highest",
            "largest",
            "most",
            "top",
        ]
    ):
        return False
    return any(re.search(pattern, lowered) for pattern in MEC_ANNUAL_REPORT_LOOKUP_PATTERNS)


def asks_about_wic_lookup(question: str) -> bool:
    lowered = question.lower()
    if "mophims" in lowered and any(term in lowered for term in ["profile", "count", "rate", "participation"]):
        return False
    return any(re.search(pattern, lowered) for pattern in WIC_LOOKUP_PATTERNS)


def asks_about_food_pantry_lookup(question: str) -> bool:
    lowered = question.lower()
    if any(term in lowered for term in ["snap", "food stamp", "food stamps", "ebt"]) and not any(
        term in lowered for term in ["food pantry", "food pantries", "food bank"]
    ):
        return False
    return any(re.search(pattern, lowered) for pattern in FOOD_PANTRY_LOOKUP_PATTERNS)


def asks_about_farmers_market_lookup(question: str) -> bool:
    lowered = question.lower()
    if any(term in lowered for term in ["market report", "market reports", "agricultural market news", "ag market news"]):
        return False
    return any(re.search(pattern, lowered) for pattern in FARMERS_MARKET_LOOKUP_PATTERNS)


def asks_about_ltc_lookup(question: str) -> bool:
    lowered = question.lower()
    if any(term in lowered for term in ["connected", "source", "sources", "available", "reports"]) and not any(
        term in lowered
        for term in [
            "indexed",
            "exact",
            "lookup",
            "directory",
            "census",
            "capacity",
            "licensed beds",
            "occupancy",
            "how many",
        ]
    ):
        return False
    if "hospital" in lowered and "ltc" not in lowered and "long-term" not in lowered:
        return False
    return any(re.search(pattern, lowered) for pattern in LTC_LOOKUP_PATTERNS)


def asks_about_dhss_ltc_inspection_lookup(question: str) -> bool:
    lowered = question.lower()
    has_ltc_family = any(
        term in lowered
        for term in [
            "ltc",
            "long-term care",
            "long term care",
            "nursing home",
            "nursing homes",
            "show me long",
            "showme long",
        ]
    )
    if not has_ltc_family:
        return False
    has_inspection_scope = any(
        term in lowered
        for term in [
            "inspection",
            "inspections",
            "inspected",
            "survey",
            "complaint",
            "complaints",
            "scope",
            "severity",
            "class i",
            "class ii",
            "class iii",
            "show me",
            "showme",
            "county filter",
            "city filter",
            "facility type",
            "facility types",
            "resource",
            "resources",
            "link",
            "links",
        ]
    )
    if not has_inspection_scope:
        return False
    if any(
        term in lowered
        for term in [
            "directory row",
            "directory rows",
            "census occupancy",
            "occupancy ratio",
            "licensed beds",
            "capacity",
            "how many assisted living",
        ]
    ) and not any(term in lowered for term in ["inspection", "inspected", "survey", "complaint", "show me"]):
        return False
    return any(re.search(pattern, lowered) for pattern in DHSS_LTC_INSPECTION_LOOKUP_PATTERNS)


def asks_about_dnr_water_lookup(question: str) -> bool:
    lowered = question.lower()
    if any(
        term in lowered
        for term in [
            "permit",
            "permits",
            "certification",
            "registration",
            "license",
            "form",
            "application",
            "public notice",
            "impaired",
            "water quality",
            "gis",
            "map",
            "maps",
            "viewer",
            "mocwis",
            "mogem",
            "lims",
            "wims",
            "geostrat",
            "geoedge",
            "e-services",
            "resources",
            "links",
            "wastewater",
            "stormwater",
            "edmr",
        ]
    ):
        return False
    if any(term in lowered for term in ["connected", "source", "sources", "available"]) and not any(
        term in lowered for term in ["indexed", "exact", "lookup", "pwsid", "count", "how many"]
    ):
        return False
    return any(re.search(pattern, lowered) for pattern in DNR_WATER_LOOKUP_PATTERNS)


def asks_about_dnr_oil_gas_lookup(question: str) -> bool:
    lowered = question.lower()
    if any(term in lowered for term in ["utility", "utilities", "natural gas utility", "gas utility"]):
        return False
    if "oil" not in lowered and "gas" not in lowered and not re.search(r"\b\d{3}-\d{5}\b", lowered):
        return False
    return any(re.search(pattern, lowered) for pattern in DNR_OIL_GAS_LOOKUP_PATTERNS)


def asks_about_dnr_hazardous_waste_lookup(question: str) -> bool:
    lowered = question.lower()
    if any(term in lowered for term in ["drinking water", "impaired", "oil", "gas", "utility"]):
        return False
    has_scope = any(
        term in lowered
        for term in [
            "hazardous waste",
            "tsd",
            "treatment storage",
            "treatment, storage",
            "waste facility",
            "waste facilities",
        ]
    ) or re.search(r"\bMOD\d{9}\b", question.upper())
    if not has_scope:
        return False
    return any(re.search(pattern, lowered) for pattern in DNR_HAZARDOUS_WASTE_LOOKUP_PATTERNS)


def asks_about_dnr_impaired_waters_lookup(question: str) -> bool:
    lowered = question.lower()
    if any(term in lowered for term in ["resource", "resources", "link", "links", "where can i find"]):
        return False
    if any(term in lowered for term in ["drinking water system", "pwsid", "consumer confidence report"]):
        return False
    return any(re.search(pattern, lowered) for pattern in DNR_IMPAIRED_WATERS_LOOKUP_PATTERNS)


def asks_about_dnr_resources_lookup(question: str) -> bool:
    lowered = question.lower()
    resource_specific_terms = [
        "resource",
        "resources",
        "link",
        "links",
        "e-services",
        "permit",
        "certification",
        "registration",
        "license",
        "form",
        "application",
        "public notice",
        "impaired",
        "water quality",
        "gis",
        "map",
        "viewer",
        "mocwis",
        "mogem",
        "lims",
        "wims",
        "geostrat",
        "geoedge",
        "air",
        "emission",
        "waste",
        "recycling",
        "energy",
    ]
    if re.search(r"\bdnr\b.*\bwater\b.*\b(indexed|lookup|data)\b", lowered) and not any(
        term in lowered for term in resource_specific_terms
    ):
        return False
    has_dnr_context = "dnr" in lowered or any(
        term in lowered
        for term in [
            "impaired waters",
            "water quality",
            "mocwis",
            "mogem",
            "lims",
            "wims",
            "geostrat",
            "geoedge",
            "e-start",
            "drinking water viewer",
            "missouri clean water information",
        ]
    )
    if not has_dnr_context:
        return False
    if any(term in lowered for term in ["connected", "source", "sources", "available"]) and not any(
        term in lowered for term in ["indexed", "exact", "lookup", *resource_specific_terms]
    ):
        return False
    return any(re.search(pattern, lowered) for pattern in DNR_RESOURCES_LOOKUP_PATTERNS)


def asks_about_msdis_geospatial_lookup(question: str) -> bool:
    lowered = question.lower()
    if "msdis" not in lowered and "missouri spatial data information service" not in lowered and not re.search(
        r"\bmissouri\s+(?:gis|geospatial|spatial)\b", lowered
    ):
        return False
    if any(term in lowered for term in ["connected", "source", "sources", "available"]) and not any(
        term in lowered
        for term in [
            "indexed",
            "exact",
            "lookup",
            "resource",
            "resources",
            "link",
            "links",
            "dataset",
            "datasets",
            "arcgis",
            "service",
            "services",
            "boundary",
            "boundaries",
            "imagery",
            "lidar",
        ]
    ):
        return False
    return any(re.search(pattern, lowered) for pattern in MSDIS_GEOSPATIAL_LOOKUP_PATTERNS)


def asks_about_modot_aadt_lookup(question: str) -> bool:
    lowered = question.lower()
    if any(term in lowered for term in ["connected", "source", "sources", "available"]) and not any(
        term in lowered for term in ["indexed", "exact", "lookup", "aadt", "highest", "busiest", "route", "segment"]
    ):
        return False
    return any(re.search(pattern, lowered) for pattern in MODOT_AADT_LOOKUP_PATTERNS)


def asks_about_utility_lookup(question: str) -> bool:
    lowered = question.lower()
    if ("psc" in lowered or "public service commission" in lowered) and any(
        term in lowered for term in ["connected", "source", "sources", "available", "reports"]
    ):
        return False
    if any(term in lowered for term in ["connected", "source", "sources", "available"]) and not any(
        term in lowered for term in ["indexed", "exact", "lookup", "provider", "providers", "serve", "serves", "how many"]
    ):
        return False
    return any(re.search(pattern, lowered) for pattern in UTILITY_LOOKUP_PATTERNS)


def asks_about_agriculture_lookup(question: str) -> bool:
    lowered = question.lower()
    if any(term in lowered for term in ["connected", "source", "sources", "available", "reports"]) and not any(
        term in lowered for term in ["indexed", "exact", "lookup", "feed", "sample", "testing", "how many"]
    ):
        return False
    return any(re.search(pattern, lowered) for pattern in AGRICULTURE_LOOKUP_PATTERNS)


def asks_about_ag_market_news_lookup(question: str) -> bool:
    lowered = question.lower()
    if any(term in lowered for term in ["feed sample", "sample id", "feed testing", "protein values"]):
        return False
    return any(re.search(pattern, lowered) for pattern in AG_MARKET_NEWS_LOOKUP_PATTERNS)


def asks_about_ag_market_report_document_lookup(question: str) -> bool:
    lowered = question.lower()
    if any(term in lowered for term in ["feed sample", "sample id", "feed testing", "protein values"]):
        return False
    if any(term in lowered for term in ["link", "links", "url", "download", "where can i find"]) and not any(
        term in lowered
        for term in [
            "explain",
            "summarize",
            "summary",
            "plain english",
            "snippet",
            "document text",
            "pdf text",
            "inside",
            "price",
            "prices",
            "range",
            "receipts",
            "demand",
            "supply",
            "supplies",
        ]
    ):
        return False
    return any(re.search(pattern, lowered) for pattern in AG_MARKET_REPORT_DOCUMENT_LOOKUP_PATTERNS)


def asks_about_cannabis_lookup(question: str) -> bool:
    lowered = question.lower()
    if any(term in lowered for term in ["connected", "source", "sources", "available"]) and not any(
        term in lowered
        for term in [
            "indexed",
            "exact",
            "lookup",
            "dispensary",
            "dispensaries",
            "facility",
            "facilities",
            "annual",
            "report",
            "sales",
            "tax",
            "microbusiness",
            "license",
            "licenses",
            "how many",
            "most",
        ]
    ):
        return False
    return any(re.search(pattern, lowered) for pattern in CANNABIS_LOOKUP_PATTERNS)


def asks_about_child_care_lookup(question: str) -> bool:
    lowered = question.lower()
    if any(term in lowered for term in ["connected", "source", "sources", "available"]) and not any(
        term in lowered
        for term in [
            "indexed",
            "exact",
            "lookup",
            "dashboard",
            "dashboards",
            "slot",
            "slots",
            "pending",
            "inspection",
            "inspections",
            "complaint",
            "complaints",
            "licensed",
            "licensure",
            "facility",
            "facilities",
            "centers",
            "homes",
            "how many",
            "most",
        ]
    ):
        return False
    return any(re.search(pattern, lowered) for pattern in CHILD_CARE_LOOKUP_PATTERNS)


def asks_about_psc_reports_lookup(question: str) -> bool:
    lowered = question.lower()
    return any(re.search(pattern, lowered) for pattern in PSC_REPORTS_LOOKUP_PATTERNS)


def asks_about_psc_report_document_lookup(question: str) -> bool:
    lowered = question.lower()
    return any(re.search(pattern, lowered) for pattern in PSC_REPORT_DOCUMENT_LOOKUP_PATTERNS)


def asks_about_oa_budget_lookup(question: str) -> bool:
    lowered = question.lower()
    return any(re.search(pattern, lowered) for pattern in OA_BUDGET_LOOKUP_PATTERNS)


def asks_about_oa_revenue_detail_lookup(question: str) -> bool:
    lowered = question.lower()
    return any(re.search(pattern, lowered) for pattern in OA_REVENUE_DETAIL_LOOKUP_PATTERNS)


def asks_about_auditor_lookup(question: str) -> bool:
    lowered = question.lower()
    if any(term in lowered for term in ["connected", "source", "sources", "available"]) and not any(
        term in lowered
        for term in [
            "indexed",
            "exact",
            "lookup",
            "metadata",
            "latest",
            "recent",
            "released",
            "how many",
            "find",
            "link",
            "report 20",
            "mention",
            "about",
        ]
    ):
        return False
    return any(re.search(pattern, lowered) for pattern in AUDITOR_LOOKUP_PATTERNS)


def asks_about_auditor_document_lookup(question: str) -> bool:
    lowered = question.lower()
    return any(re.search(pattern, lowered) for pattern in AUDITOR_DOCUMENT_LOOKUP_PATTERNS)


def asks_about_sos_elections_lookup(question: str) -> bool:
    lowered = question.lower()
    if any(term in lowered for term in ["connected", "source", "sources", "available"]) and not any(
        term in lowered
        for term in [
            "indexed",
            "exact",
            "lookup",
            "results",
            "returns",
            "who won",
            "winner",
            "votes",
            "primary",
            "general",
        ]
    ):
        return False
    if "governor of missouri" in lowered and "election" not in lowered and "primary" not in lowered:
        return False
    return any(re.search(pattern, lowered) for pattern in SOS_ELECTION_LOOKUP_PATTERNS)


def asks_about_expanded_public_source(question: str) -> bool:
    lowered = question.lower()
    return any(re.search(pattern, lowered) for pattern in EXPANDED_SOURCE_PATTERNS)


def asks_about_mshp_crash_lookup(question: str) -> bool:
    lowered = question.lower()
    if any(word in lowered for word in ["connected", "source", "sources", "catalog", "available"]):
        return False
    if not years_in_question(question) and not any(term in lowered for term in ["latest", "most recent", "current", "newest"]):
        return False
    crash_terms = [
        "mshp",
        "crash",
        "crashes",
        "traffic safety",
        "fatal crash",
        "fatal crashes",
        "persons killed",
        "persons injured",
        "death rate",
        "injury rate",
        "alcohol involved",
        "speed involved",
        "motorcycle",
        "commercial vehicle",
        "school bus",
        "pedestrian",
        "pedalcycle",
        "bicycle",
        "work zone",
        "deer",
    ]
    return any(term in lowered for term in crash_terms)


def asks_about_dor_report_lookup(question: str) -> bool:
    lowered = question.lower()
    if any(word in lowered for word in ["connected", "source", "sources", "catalog", "available"]):
        return bool(re.search(r"\b(dor|department of revenue|revenue)\b", lowered))
    quarterly_tax_credit_question = (
        ("tax credit" in lowered or "tax credits" in lowered)
        and (
            "tax credit report" in lowered
            or "quarterly tax credit" in lowered
            or re.search(r"\bfy\s*'?\d{2,4}\b", lowered)
            or re.search(r"\bq[1-4]\b", lowered)
            or re.search(r"\b(first|second|third|fourth)\s+quarter\b", lowered)
        )
        or (
            (
                re.search(r"\bfy\s*'?\d{2,4}\b", lowered)
                or re.search(r"\bq[1-4]\b", lowered)
                or re.search(r"\b(first|second|third|fourth)\s+quarter\b", lowered)
            )
            and re.search(r"\b(issued|authorized|redemptions?|redeemed|fy\s*to\s*date|fytd|year\s*to\s*date|ytd)\b", lowered)
        )
    )
    if quarterly_tax_credit_question:
        return True
    vehicle_report_question = bool(
        re.search(
            r"\b(?:registered|titled)\b.*\b(?:vehicle|vehicles|passenger|truck|trucks|motorcycle|motorcycles|trailer|trailers|boat|boats|rv|atv)\b",
            lowered,
        )
        or re.search(
            r"\b(?:passenger|truck|trucks|motorcycle|motorcycles|trailer|trailers|boat|boats|rv|atv)\b.*\b(?:vehicle|vehicles)\b",
            lowered,
        )
    )
    if vehicle_report_question:
        return True
    dor_terms = [
        "dor",
        "department of revenue",
        "revenue report",
        "taxable sales",
        "food tax",
        "grocery tax",
        "working family tax credit",
        "working family tax credits",
        "wftc",
        "tax credit report",
        "quarterly tax credit",
        "business location",
        "business locations",
        "vehicle counts",
        "licensed drivers",
        "driver totals",
        "dealer count",
        "dealer counts",
        "motor vehicle dealers",
        "sic",
    ]
    return any(term in lowered for term in dor_terms)


def asks_about_meric_labor_lookup(question: str) -> bool:
    lowered = question.lower()
    if any(word in lowered for word in ["meric", "unemployment", "labor force", "labor market", "unemployed"]):
        return True
    return bool(
        "employment" in lowered
        and re.search(r"\b(missouri|mo|county|counties|st\.?\s+louis|boone|jackson|st\.?\s+charles)\b", lowered)
    )


def asks_about_map_inventory(question: str) -> bool:
    lowered = question.lower()
    return any(re.search(pattern, lowered) for pattern in MAP_INVENTORY_PATTERNS)


def asks_for_help(question: str) -> bool:
    lowered = question.lower()
    return any(re.search(pattern, lowered) for pattern in HELP_PATTERNS)


def asks_about_missouri_governor(question: str) -> bool:
    lowered = question.lower()
    if "election" in lowered or "primary" in lowered or "votes" in lowered:
        return False
    return any(re.search(pattern, lowered) for pattern in MISSOURI_GOVERNOR_PATTERNS)


def asks_about_missouri_capital(question: str) -> bool:
    lowered = question.lower()
    if "capital mall" in lowered or "capital paving" in lowered or "capital projects" in lowered:
        return False
    return any(re.search(pattern, lowered) for pattern in MISSOURI_CAPITAL_PATTERNS)


def asks_about_map_definition(question: str) -> bool:
    lowered = question.lower()
    if "map files" in lowered or "map categories" in lowered or "download" in lowered:
        return False
    return any(re.search(pattern, lowered) for pattern in MAP_DEFINITION_PATTERNS)


def asks_for_top(question: str) -> bool:
    lowered = question.lower()
    return any(re.search(pattern, lowered) for pattern in TOP_PATTERNS)


def asks_for_top_employee_pay(question: str) -> bool:
    lowered = question.lower()
    if not asks_about_salary_scope(question):
        return False
    return bool(
        asks_for_top(question)
        or re.search(r"\bpaid\s+the\s+most\b", lowered)
        or re.search(r"\bgets?\s+paid\s+the\s+most\b", lowered)
        or re.search(r"\bhighest[-\s]+paid\b", lowered)
        or re.search(r"\bmost[-\s]+paid\b", lowered)
    )


def asks_about_tax_credit(question: str) -> bool:
    lowered = question.lower()
    if "working family tax credit" in lowered or "working family tax credits" in lowered or "wftc" in lowered:
        return False
    if (
        ("tax credit report" in lowered or "quarterly tax credit" in lowered)
        or (
            ("tax credit" in lowered or "tax credits" in lowered)
            and (
                re.search(r"\bfy\s*'?\d{2,4}\b", lowered)
                or re.search(r"\bq[1-4]\b", lowered)
                or re.search(r"\b(first|second|third|fourth)\s+quarter\b", lowered)
            )
        )
        or (
            (
                re.search(r"\bfy\s*'?\d{2,4}\b", lowered)
                or re.search(r"\bq[1-4]\b", lowered)
                or re.search(r"\b(first|second|third|fourth)\s+quarter\b", lowered)
            )
            and re.search(r"\b(issued|authorized|redemptions?|redeemed|fy\s*to\s*date|fytd|year\s*to\s*date|ytd)\b", lowered)
        )
    ):
        return False
    return "tax credit" in lowered or "tax credits" in lowered


def asks_about_federal_grant(question: str) -> bool:
    lowered = question.lower()
    return "federal grant" in lowered or "federal grants" in lowered


def asks_about_budget_restriction(question: str) -> bool:
    lowered = question.lower()
    return "budget restriction" in lowered or "restricted amount" in lowered or "released amount" in lowered


def asks_about_bonds(question: str) -> bool:
    lowered = question.lower()
    return "bond" in lowered or "bonds" in lowered


def asks_about_expenditure_lookup(question: str) -> bool:
    lowered = question.lower()
    return (
        "expenditure" in lowered
        or "payment" in lowered
        or "paid" in lowered
        or " pay " in f" {lowered} "
        or "spent" in lowered
        or "spend" in lowered
        or "spending" in lowered
    )


def looks_like_public_data_question(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in PUBLIC_DATA_TERMS)


def asks_unsupported_scope(question: str) -> bool:
    lowered = question.lower()
    return any(re.search(pattern, lowered) for pattern in UNSUPPORTED_PATTERNS)


def requested_limit(question: str, default: int = 5, maximum: int = 25) -> int:
    lowered = question.lower()
    explicit = re.search(r"\b(?:top|first|show(?: me)?|list)\s+(\d{1,2})\b", lowered)
    if explicit:
        return max(1, min(maximum, int(explicit.group(1))))
    for word, value in NUMBER_WORDS.items():
        if re.search(rf"\b(?:top|first|show(?: me)?|list)\s+{word}\b", lowered):
            return max(1, min(maximum, value))
    if any(word in lowered for word in ["largest", "highest", "biggest", "smallest", "lowest", "most"]):
        return 1
    return default


def asks_reversed_vendor_payment(question: str) -> bool:
    match = re.search(r"\bpaid by\s+(.+?)\s+to\s+(.+?)(?:\s+in\b|\?|$)", question, flags=re.IGNORECASE)
    if not match:
        return False
    payer = match.group(1).lower()
    return bool(re.search(r"\b(llc|inc|corp|corporation|company|bank|na)\b", payer))


def asks_which_agency_paid_vendor(question: str) -> bool:
    lowered = question.lower()
    return bool(re.search(r"\b(which|what)\s+agenc(?:y|ies)\b.*\bpaid\b", lowered))


def asks_generic_agency_ranking(question: str) -> bool:
    lowered = question.lower()
    return asks_for_top(question) and bool(re.search(r"\bagenc(?:y|ies)\b", lowered))


def asks_year_peak(question: str) -> bool:
    lowered = question.lower()
    return "year" in lowered and any(word in lowered for word in ["highest", "largest", "biggest", "lowest", "smallest"])


def normalize_public_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Z0-9& ]+", " ", value.upper())
    return re.sub(r"\s+", " ", cleaned).strip()


def is_aggregate_employee_name(value: str) -> bool:
    normalized = normalize_public_name(value)
    return bool(re.search(r"\bPROTECTED\b", normalized) or re.search(r"\bCLIENT\s+PATIENT\s+WORKERS\b", normalized))


def parse_money(value: str | None) -> Decimal:
    if not value:
        return Decimal("0")
    try:
        return Decimal(value.replace(",", "").strip())
    except InvalidOperation:
        return Decimal("0")


def format_money(value: Decimal) -> str:
    return f"${value.quantize(Decimal('0.01')):,.2f}"


def format_lookup_money(value: Any) -> str:
    return f"${Decimal(str(value)).quantize(Decimal('0.01')):,.2f}"


def normalize_general_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def public_data_like_question(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in PUBLIC_DATA_LIKE_TERMS)


def current_fact_question(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in CURRENT_FACT_TERMS)


def arithmetic_expression(question: str) -> str | None:
    lowered = question.lower().strip()
    if re.search(r"\b(?:19|20)\d{2}-\d{2}\b", lowered):
        return None
    lowered = re.sub(r"^(what(?:'s| is)|how much is|calculate|compute|solve)\s+", "", lowered)
    lowered = lowered.rstrip("?.! ")
    for phrase, symbol in sorted(ARITHMETIC_OPERATOR_WORDS.items(), key=lambda item: -len(item[0])):
        lowered = re.sub(rf"\b{re.escape(phrase)}\b", f" {symbol} ", lowered)
    for phrase, number in sorted(ARITHMETIC_NUMBER_WORDS.items(), key=lambda item: -len(item[0])):
        lowered = re.sub(rf"\b{re.escape(phrase)}\b", number, lowered)
    if re.search(r"[a-z]", lowered):
        return None
    lowered = lowered.replace("^", "**")
    expression = re.sub(r"[^0-9+\-*/().\s]", "", lowered)
    expression = re.sub(r"\s+", " ", expression).strip()
    if not expression or not re.search(r"\d", expression) or not re.search(r"[+\-*/]", expression):
        return None
    if not re.fullmatch(r"[0-9+\-*/().\s]+", expression):
        return None
    return expression


def eval_arithmetic_node(node: ast.AST) -> float | int:
    if isinstance(node, ast.Expression):
        return eval_arithmetic_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.UnaryOp):
        operand = eval_arithmetic_node(node.operand)
        if isinstance(node.op, ast.UAdd):
            return operand
        if isinstance(node.op, ast.USub):
            return -operand
    if isinstance(node, ast.BinOp):
        left = eval_arithmetic_node(node.left)
        right = eval_arithmetic_node(node.right)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            if right == 0:
                raise ZeroDivisionError
            return left / right
        if isinstance(node.op, ast.Pow):
            if abs(right) > 8:
                raise ValueError("Exponent too large")
            return left**right
    raise ValueError("Unsupported arithmetic expression")


def format_arithmetic_result(value: float | int) -> str:
    if abs(float(value)) > 10**12:
        raise ValueError("Result too large")
    if isinstance(value, int) or float(value).is_integer():
        return str(int(value))
    return f"{float(value):,.8f}".rstrip("0").rstrip(".")


def arithmetic_answer_text(question: str) -> str | None:
    expression = arithmetic_expression(question)
    if expression is None:
        return None
    try:
        parsed = ast.parse(expression, mode="eval")
        result = eval_arithmetic_node(parsed)
        return f"{expression} = {format_arithmetic_result(result)}."
    except Exception:
        return "I can help with basic arithmetic, but I could not parse that expression safely."


def low_risk_general_answer_text(question: str) -> str | None:
    lowered = question.lower().strip()
    normalized = normalize_general_text(lowered.rstrip("?.! "))

    if re.fullmatch(r"(what is|what's|tell me)?\s*(the\s+)?capital\s+(city\s+)?of\s+france", normalized):
        return "Paris."

    if re.fullmatch(r"(how many\s+)?days\s+(are\s+)?(there\s+)?in\s+a\s+week", normalized):
        return "7."

    if re.fullmatch(r"(how many\s+)?hours\s+(are\s+)?(there\s+)?in\s+a\s+day", normalized):
        return "24."

    if re.fullmatch(r"(spell|how do you spell)\s+missouri", normalized):
        return "Missouri."

    if re.search(r"\bwhat\s+color\s+is\s+the\s+sky\b", normalized):
        return "Usually blue."

    if re.search(r"\bwhy\s+is\s+the\s+sky\s+blue\b", normalized):
        return "The sky looks blue because air scatters shorter blue wavelengths of sunlight more than longer red wavelengths."

    if re.search(r"\bwho\s+wrote\s+hamlet\b", normalized):
        return "William Shakespeare wrote Hamlet."

    if re.search(r"\bwhat\s+is\s+water\b", normalized):
        return "Water is a chemical compound made of hydrogen and oxygen."

    if re.search(r"\bwhat\s+is\s+photosynthesis\b", normalized):
        return "Photosynthesis is how plants use sunlight, water, and carbon dioxide to make sugar and release oxygen."

    if re.search(r"\bwhat\s+is\s+an?\s+api\b", normalized):
        return "An API is a defined way for software systems to request data or actions from each other."

    if re.search(r"\bwhat\s+is\s+an?\s+algorithm\b", normalized):
        return "An algorithm is a step-by-step method for solving a problem or completing a task."

    if re.search(r"\b(write|draft|make)\b.*\b(one sentence|short)\b.*\bthank\s+you\b", normalized):
        return "Thank you for your time and help; I really appreciate it."

    return None


def canned_general_answer_text(question: str) -> str | None:
    lowered = question.lower().strip()
    normalized = normalize_general_text(lowered.rstrip("?.! "))

    if re.search(r"\bwhat\s+is\s+a\s+chatbot\b", normalized):
        return "A chatbot is software that answers questions or carries on a conversation using rules, retrieved information, a language model, or a mix of those methods."

    if (
        "lora" in normalized
        or "low rank adaptation" in normalized
        or ("fine tune" in normalized and "local model" in normalized)
        or ("fine-tune" in normalized and "local model" in normalized)
    ):
        return (
            "Fine-tuning with LoRA means keeping most of a small local model unchanged and training a small set of adapter weights. "
            "It is cheaper and lighter than retraining the whole model, and it lets the project save a compact adapter as evidence of the experiment."
        )

    if re.search(r"\bwhat\s+is\s+machine\s+learning\b", normalized):
        return "Machine learning is a way to build software that learns patterns from examples instead of only following hand-written rules."

    if re.search(r"\bwhat\s+is\s+(a\s+)?county\b", normalized):
        return "A county is a local government area within a state, often used for courts, elections, public health, roads, property records, and other local services."

    if re.search(r"\bwhat\s+is\s+public\s+data\b", normalized):
        return "Public data is information a government or public body makes available for people to inspect, download, or use, usually with source context and limits."

    if re.search(r"\bwhat\s+is\s+(a\s+)?dataset\b", normalized):
        return "A dataset is an organized collection of records, such as rows in a table, that can be searched, analyzed, or downloaded."

    if re.search(r"\bwhat\s+is\s+(a\s+)?citation\b", normalized) or re.search(r"\bwhat\s+does\s+cited\s+mean\b", normalized):
        return "A citation tells you where an answer came from, so you can open the source and check the evidence yourself."

    if re.search(r"\bwhat\s+is\s+(a\s+)?vendor\b", normalized):
        return "A vendor is a person or organization that sells goods or services; in this project it usually means an entity paid by a Missouri public agency."

    if re.search(r"\bwhat\s+is\s+an?\s+expenditure\b", normalized):
        return "An expenditure is money spent. In Missouri public finance data, it usually means a payment by an agency to a vendor, program, or category."

    if re.search(r"\bwhat\s+is\s+(a\s+)?contract\b", normalized):
        return "A contract is an agreement that sets out what will be provided, who is responsible, key dates, pricing, and other terms."

    if any(
        phrase in normalized
        for phrase in [
            "what is this project",
            "what does this project do",
            "what do we do in this project",
            "what is the project",
        ]
    ):
        return (
            "This project builds a local Missouri public-data chatbot case study. "
            "It combines a tiny fine-tuned model experiment with deterministic source-backed lookups so simple questions stay brief and public-record answers show citations."
        )

    return None


def tidy_general_answer(text: str, max_sentences: int = 2, max_chars: int = 220) -> str:
    answer = concise_sentences(text, max_sentences=max_sentences)
    answer = re.sub(r"\s*(?:source|evidence|citation)\s*:\s*$", "", answer, flags=re.IGNORECASE).strip()
    if len(answer) <= max_chars:
        return answer
    clipped = answer[:max_chars].rsplit(" ", 1)[0].rstrip(" ,;:")
    return f"{clipped}."


def concise_sentences(text: str, max_sentences: int = 3) -> str:
    cleaned = normalize_general_text(text)
    if not cleaned:
        return cleaned
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    return " ".join(parts[:max_sentences]).strip()


def retrieval_tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 2}


def sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_map_vendor_totals(path: Path = MAP_EXPENDITURE_FILE) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}

    totals: defaultdict[str, Decimal] = defaultdict(Decimal)
    display_names: dict[str, str] = {}
    row_counts: defaultdict[str, int] = defaultdict(int)
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="|")
        for row in reader:
            vendor = (row.get("Vendor Name") or "").strip()
            normalized = normalize_public_name(vendor)
            if not normalized:
                continue
            display_names.setdefault(normalized, vendor)
            totals[normalized] += parse_money(row.get("Payments Total"))
            row_counts[normalized] += 1

    return {
        normalized: {
            "display_name": display_names[normalized],
            "payments_total": total,
            "row_count": row_counts[normalized],
        }
        for normalized, total in totals.items()
    }


def find_vendor_in_question(question: str, vendor_totals: dict[str, dict[str, Any]]) -> tuple[str, dict[str, Any]] | None:
    normalized_question = normalize_public_name(question)
    matches = [
        (vendor_name, vendor_record)
        for vendor_name, vendor_record in vendor_totals.items()
        if vendor_name and vendor_name in normalized_question
    ]
    if not matches:
        return None
    matches.sort(key=lambda item: len(item[0]), reverse=True)
    return matches[0]


def load_model(model_id: str, adapter_path: Path | None, use_base: bool = False) -> tuple[Any, Any, Any]:
    try:
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as exc:
        raise ImportError(
            "Model generation requires the optional ML dependencies in requirements.txt. "
            "Deterministic public-data lookup can run without them."
        ) from exc

    tokenizer = AutoTokenizer.from_pretrained(model_id)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    dtype = torch.float16 if device.type == "cuda" else torch.float32
    model = AutoModelForCausalLM.from_pretrained(model_id, dtype=dtype, low_cpu_mem_usage=True)
    if not use_base and adapter_path is not None and adapter_path.exists():
        model = PeftModel.from_pretrained(model, adapter_path)
    model.to(device)
    model.eval()
    return tokenizer, model, device


class AskEngine:
    def __init__(
        self,
        model_id: str = DEFAULT_MODEL,
        adapter_path: Path = DEFAULT_ADAPTER,
        use_base: bool = False,
        max_new_tokens: int = 48,
        synthesis_mode: str = "off",
        synthesis_max_new_tokens: int = 160,
    ) -> None:
        self.model_id = model_id
        self.adapter_path = adapter_path
        self.use_base = use_base
        self.max_new_tokens = max_new_tokens
        self.synthesis_mode = synthesis_mode
        self.synthesis_max_new_tokens = synthesis_max_new_tokens
        self.rows = load_knowledge_rows()
        corpus = [f"{row['question']} {row['context']} {row['answer']}" for row in self.rows]
        self.vectorizer: Any | None = None
        self.matrix: Any | None = None
        self._cosine_similarity: Any | None = None
        self._fallback_corpus_tokens = [retrieval_tokens(text) for text in corpus]
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity

            self.vectorizer = TfidfVectorizer(stop_words="english")
            self.matrix = self.vectorizer.fit_transform(corpus)
            self._cosine_similarity = cosine_similarity
        except ImportError:
            # Exact MAP lookup paths should remain usable on machines that have not
            # installed the optional model-training dependency stack.
            self.vectorizer = None
            self.matrix = None
            self._cosine_similarity = None
        self.tokenizer: Any | None = None
        self.model: Any | None = None
        self.device: Any | None = None
        self._vendor_totals: dict[str, dict[str, Any]] | None = None
        self.map_index = MapPublicIndex()
        self.contract_index = ContractIndex()
        self.contract_document_index = ContractDocumentIndex()
        self.cannabis_index = CannabisIndex()
        self.child_care_index = ChildCareIndex()
        self.data_mo_agriculture_index = DataMoAgricultureIndex()
        self.data_mo_catalog_index = DataMoCatalogIndex()
        self.data_mo_education_index = DataMoEducationIndex()
        self.dese_apr_index = DeseAprIndex()
        self.dese_directory_index = DeseDirectoryIndex()
        self.dese_finance_index = DeseFinanceIndex()
        self.dese_school_data_index = DeseSchoolDataIndex()
        self.dese_special_education_index = DeseSpecialEducationIndex()
        self.dhss_brfss_index = DhssBrfssIndex()
        self.dhss_health_sources_index = DhssHealthSourcesIndex()
        self.dhss_ltc_inspection_index = DhssLtcInspectionIndex()
        self.dhss_mophims_profiles_index = DhssMophimsProfilesIndex()
        self.dhss_vital_stats_index = DhssVitalStatsIndex()
        self.data_mo_dnr_oil_gas_index = DataMoDnrOilGasIndex()
        self.data_mo_dnr_hazardous_waste_index = DataMoDnrHazardousWasteIndex()
        self.dnr_impaired_waters_index = DnrImpairedWatersIndex()
        self.dnr_resources_index = DnrResourcesIndex()
        self.mec_annual_report_index = MecAnnualReportIndex()
        self.mec_resources_index = MecResourcesIndex()
        self.msdis_geospatial_index = MsdisGeospatialIndex()
        self.data_mo_farmers_market_index = DataMoFarmersMarketIndex()
        self.data_mo_food_pantry_index = DataMoFoodPantryIndex()
        self.data_mo_health_index = DataMoHealthIndex()
        self.data_mo_hospital_index = DataMoHospitalIndex()
        self.data_mo_wic_index = DataMoWicIndex()
        self.data_mo_ltc_index = DataMoLtcIndex()
        self.data_mo_utility_index = DataMoUtilityIndex()
        self.data_mo_water_index = DataMoWaterIndex()
        self.public_source_index = PublicSourceIndex()
        self.modot_aadt_index = ModotAadtIndex()
        self.mshp_crash_index = MshpCrashIndex()
        self.dor_reports_index = DorReportsIndex()
        self.state_auditor_document_index = StateAuditorDocumentIndex()
        self.state_auditor_index = StateAuditorIndex()
        self.sos_elections_index = SosElectionsIndex()
        self.meric_labor_index = MericLaborIndex()
        self.psc_report_document_index = PscReportDocumentIndex()
        self.psc_reports_index = PscReportsIndex()
        self.oa_budget_index = OaBudgetIndex()
        self.oa_revenue_detail_index = OaRevenueDetailIndex()
        self.ag_market_news_index = AgMarketNewsIndex()
        self.ag_market_report_document_index = AgMarketReportDocumentIndex()

    def vendor_totals(self) -> dict[str, dict[str, Any]]:
        if self._vendor_totals is None:
            self._vendor_totals = load_map_vendor_totals()
        return self._vendor_totals

    def retrieve_context(self, question: str) -> dict[str, Any]:
        if not self.rows:
            return {"id": "no_rows", "source": "none", "question": question, "context": "", "answer": "", "score": 0.0}
        if self.vectorizer is not None and self.matrix is not None and self._cosine_similarity is not None:
            query = self.vectorizer.transform([question])
            scores = self._cosine_similarity(query, self.matrix).flatten()
            best_idx = int(scores.argmax())
            score = float(scores[best_idx])
        else:
            query_tokens = retrieval_tokens(question)
            scores = []
            for row_tokens in self._fallback_corpus_tokens:
                if not query_tokens or not row_tokens:
                    scores.append(0.0)
                    continue
                scores.append(len(query_tokens & row_tokens) / ((len(query_tokens) * len(row_tokens)) ** 0.5))
            best_idx = max(range(len(scores)), key=scores.__getitem__)
            score = float(scores[best_idx])
        best = dict(self.rows[best_idx])
        best["score"] = score
        return best

    def ensure_model(self) -> tuple[Any, Any, Any]:
        if self.tokenizer is None or self.model is None or self.device is None:
            self.tokenizer, self.model, self.device = load_model(
                self.model_id,
                self.adapter_path,
                use_base=self.use_base,
            )
        return self.tokenizer, self.model, self.device

    def citation_summary_for_prompt(self, result: dict[str, Any]) -> str:
        lines: list[str] = []
        for citation in result.get("citations", []):
            files = ", ".join(file.get("file_name", "") for file in citation.get("source_files", [])[:4])
            scope = citation.get("year") or citation.get("year_range") or "indexed range"
            matched = citation.get("matched_rows")
            matched_text = f", matched rows: {matched}" if matched is not None else ""
            lines.append(
                f"- {citation.get('category', 'Public data')} / {citation.get('kind', citation.get('lookup_table', 'lookup'))}; "
                f"scope: {scope}{matched_text}; files: {files}"
            )
        return "\n".join(lines) if lines else "- No citation metadata."

    def should_synthesize_answer(self, result: dict[str, Any]) -> bool:
        if self.synthesis_mode != "local":
            return False
        if result.get("model") in {"public_data_boundary", "unsupported_scope_guardrail", "retrieval_guardrail"}:
            return False
        if result.get("retrieved_source") in {
            "missouri_contract_metadata_index",
            "data_mo_catalog_lookup_index",
            "data_mo_education_lookup_index",
            "dese_apr_lookup_index",
            "dese_directory_lookup_index",
            "dese_finance_lookup_index",
            "dese_school_data_lookup_index",
            "dhss_brfss_lookup_index",
            "dhss_health_sources_lookup_index",
            "dhss_ltc_inspection_lookup_index",
            "dhss_mophims_profiles_lookup_index",
            "dhss_vital_stats_lookup_index",
            "data_mo_dnr_oil_gas_lookup_index",
            "data_mo_dnr_hazardous_waste_lookup_index",
            "dnr_impaired_waters_lookup_index",
            "dnr_resources_lookup_index",
            "mec_annual_report_lookup_index",
            "msdis_geospatial_lookup_index",
            "mec_resources_lookup_index",
            "data_mo_food_pantry_lookup_index",
            "data_mo_farmers_market_lookup_index",
            "data_mo_health_lookup_index",
            "data_mo_hospital_lookup_index",
            "data_mo_wic_lookup_index",
            "data_mo_ltc_lookup_index",
            "data_mo_utility_lookup_index",
            "data_mo_water_lookup_index",
            "modot_aadt_lookup_index",
            "data_mo_agriculture_lookup_index",
            "cannabis_lookup_index",
            "child_care_lookup_index",
            "missouri_public_source_catalog",
            "missouri_public_source_index",
            "map_employee_public_lookup_index",
            "mshp_crash_lookup_index",
            "dor_reports_lookup_index",
            "state_auditor_document_lookup_index",
            "state_auditor_lookup_index",
            "sos_elections_lookup_index",
            "meric_labor_lookup_index",
            "psc_report_document_lookup_index",
            "psc_reports_lookup_index",
            "oa_budget_lookup_index",
            "oa_revenue_detail_lookup_index",
            "ag_market_news_lookup_index",
            "ag_market_report_document_lookup_index",
        }:
            return False
        return bool(result.get("citations"))

    def synthesize_answer(self, question: str, result: dict[str, Any]) -> dict[str, Any]:
        raw_answer = str(result.get("answer", "")).strip()
        if not raw_answer:
            return result
        try:
            import torch
        except ImportError:
            return {**result, "synthesis_error": "torch is not installed; returned raw deterministic answer"}

        try:
            tokenizer, model, device = self.ensure_model()
            prompt = (
                "You are a grounded Missouri public-data chatbot.\n"
                "Rewrite the raw source answer into a concise, helpful response for the user.\n"
                "Rules:\n"
                "- Use only the raw source answer and citation summary.\n"
                "- Preserve every dollar amount, name, year, and row count exactly.\n"
                "- Do not add facts, judgments, recommendations, or speculation.\n"
                "- If the raw answer is already clear, make only light wording improvements.\n"
                "- End with one sentence beginning 'Source:' that names the cited public file or lookup.\n\n"
                f"User question: {question}\n\n"
                f"Raw source answer:\n{raw_answer}\n\n"
                f"Citation summary:\n{self.citation_summary_for_prompt(result)}\n\n"
                "Grounded answer:"
            )
            if getattr(tokenizer, "chat_template", None):
                text = tokenizer.apply_chat_template(
                    [{"role": "user", "content": prompt}],
                    tokenize=False,
                    add_generation_prompt=True,
                )
            else:
                text = prompt
            inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=1400).to(device)
            with torch.inference_mode():
                generated = model.generate(
                    **inputs,
                    max_new_tokens=self.synthesis_max_new_tokens,
                    do_sample=False,
                    pad_token_id=tokenizer.eos_token_id,
                )
            new_tokens = generated[0, inputs["input_ids"].shape[-1] :]
            synthesized = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
            if not synthesized:
                return result
            updated = dict(result)
            updated["raw_answer"] = raw_answer
            updated["answer"] = synthesized
            updated["used_model"] = True
            updated["synthesis_model"] = self.model_id
            updated["synthesis_mode"] = self.synthesis_mode
            updated["source_note"] = (
                str(result.get("source_note", "")).strip()
                + " Grounded local-model synthesis rewrote the cited lookup answer."
            ).strip()
            return updated
        except Exception as exc:
            updated = dict(result)
            updated["synthesis_error"] = str(exc)
            updated["raw_answer"] = raw_answer
            return updated

    def general_model_answer_text(self, question: str) -> str:
        tokenizer, model, device = self.ensure_model()
        prompt = (
            "You are a concise local chatbot inside a Missouri public-data demo.\n"
            "Answer ordinary low-risk questions briefly.\n"
            "Do not pretend to have a source. Do not answer current, legal, medical, financial, or public-record questions without a source.\n"
            "Keep the answer under three short sentences.\n\n"
            f"User question: {question}\n"
            "Answer:"
        )
        if getattr(tokenizer, "chat_template", None):
            text = tokenizer.apply_chat_template(
                [{"role": "user", "content": prompt}],
                tokenize=False,
                add_generation_prompt=True,
            )
        else:
            text = prompt
        inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=700).to(device)
        try:
            import torch
        except ImportError as exc:
            raise ImportError("torch is not installed") from exc
        with torch.inference_mode():
            generated = model.generate(
                **inputs,
                max_new_tokens=min(max(32, self.max_new_tokens), 96),
                do_sample=False,
                pad_token_id=tokenizer.eos_token_id,
            )
        new_tokens = generated[0, inputs["input_ids"].shape[-1] :]
        answer = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
        answer = re.split(r"\n\s*(?:User|Question|Context)\s*:", answer, maxsplit=1)[0].strip()
        return concise_sentences(answer, max_sentences=3)

    def general_chat_answer(self, question: str) -> dict[str, Any] | None:
        arithmetic = arithmetic_answer_text(question)
        if arithmetic:
            return {
                "question": question,
                "answer": arithmetic,
                "retrieved_context_id": "general_chat:arithmetic",
                "retrieved_source": None,
                "retrieval_score": 1.0,
                "used_model": False,
                "model": "general_chat",
                "source_note": "No external source used; answered as a simple general arithmetic question.",
                "citations": [],
                "source_rows": [],
            }

        lowered = question.lower().strip()
        if re.fullmatch(r"(hi|hello|hey|howdy)[!. ]*", lowered):
            return {
                "question": question,
                "answer": "Hi. Ask me a normal short question, or ask for a Missouri public-data lookup with sources.",
                "retrieved_context_id": "general_chat:greeting",
                "retrieved_source": None,
                "retrieval_score": 1.0,
                "used_model": False,
                "model": "general_chat",
                "source_note": "No external source used for this greeting.",
                "citations": [],
                "source_rows": [],
            }
        if any(phrase in lowered for phrase in ["who are you", "what are you", "what can you do"]):
            return {
                "question": question,
                "answer": (
                    "I am a local Missouri public-data chatbot prototype. I can answer simple general questions briefly, "
                    "and I use source links when I answer from public datasets."
                ),
                "retrieved_context_id": "general_chat:identity",
                "retrieved_source": None,
                "retrieval_score": 1.0,
                "used_model": False,
                "model": "general_chat",
                "source_note": "No external source used for this general chatbot description.",
                "citations": [],
                "source_rows": [],
            }

        canned_answer = canned_general_answer_text(question)
        if canned_answer:
            return {
                "question": question,
                "answer": canned_answer,
                "retrieved_context_id": "general_chat:canned",
                "retrieved_source": None,
                "retrieval_score": 1.0,
                "used_model": False,
                "model": "general_chat",
                "source_note": "No external source used; answered as a simple general question.",
                "citations": [],
                "source_rows": [],
            }

        low_risk_answer = low_risk_general_answer_text(question)
        if low_risk_answer:
            return {
                "question": question,
                "answer": low_risk_answer,
                "retrieved_context_id": "general_chat:low_risk",
                "retrieved_source": None,
                "retrieval_score": 1.0,
                "used_model": False,
                "model": "general_chat",
                "source_note": "No external source used; answered as a low-risk general question.",
                "citations": [],
                "source_rows": [],
            }

        if public_data_like_question(question) or current_fact_question(question):
            return None

        try:
            answer = self.general_model_answer_text(question)
        except Exception:
            answer = (
                "I can answer simple general questions, but I could not produce a reliable local answer for that one. "
                "For Missouri public-data questions, ask for a specific sourced lookup."
            )
            used_model = False
            synthesis_model = None
        else:
            used_model = bool(answer)
            synthesis_model = self.model_id if used_model else None
            if not answer:
                answer = (
                    "I can answer simple general questions, but I could not produce a reliable local answer for that one. "
                    "For Missouri public-data questions, ask for a specific sourced lookup."
                )
                used_model = False
                synthesis_model = None
            else:
                answer = tidy_general_answer(answer)

        result: dict[str, Any] = {
            "question": question,
            "answer": answer,
            "retrieved_context_id": "general_chat:local",
            "retrieved_source": None,
            "retrieval_score": 1.0,
            "used_model": used_model,
            "model": "general_chat",
            "source_note": "No external source used; answered in general-chat mode.",
            "citations": [],
            "source_rows": [],
        }
        if synthesis_model:
            result["synthesis_model"] = synthesis_model
        return result

    def amount_citations(
        self,
        kind: str,
        year: int | None = None,
        entity_rows: int | None = None,
        year_range: str | None = None,
    ) -> list[dict[str, Any]]:
        return [
            self.map_index.citation_for_kind(
                kind,
                year=year,
                lookup_table="public_amount_lookup",
                entity_rows=entity_rows,
                year_range=year_range,
            )
        ]

    def agency_vendor_citations(self, year: int | None = None, matched_rows: int | None = None) -> list[dict[str, Any]]:
        return [self.map_index.citation_for_agency_vendor(year=year, matched_rows=matched_rows)]

    def employee_citations(self, year: int | None = None, matched_rows: int | None = None) -> list[dict[str, Any]]:
        return [self.map_index.citation_for_employee(year=year, matched_rows=matched_rows)]

    def local_file_citation(self, source: str) -> list[dict[str, Any]]:
        path = LOCAL_SOURCE_FILES.get(source)
        if path is None or not path.exists():
            return []
        return [
            {
                "dataset": "Local processed Missouri public data",
                "category": source.replace("_", " ").title(),
                "kind": "retrieved QA source file",
                "lookup_table": "jsonl_training_or_eval_source",
                "year": None,
                "year_range": None,
                "source_files": [
                    {
                        "category": source,
                        "category_label": source.replace("_", " ").title(),
                        "file_name": str(path.relative_to(PROJECT_ROOT)),
                        "source_url": LOCAL_SOURCE_URLS.get(source),
                        "row_count": None,
                        "bytes": path.stat().st_size,
                        "sha256": sha256_file(path),
                    }
                ],
                "source_file_count": 1,
                "source_rows": None,
                "matched_rows": None,
            }
        ]

    def retrieved_row_citations(self, row: dict[str, Any]) -> list[dict[str, Any]]:
        source = row.get("source", "")
        question = row.get("question", "")
        years = years_in_question(question)
        year = years[0] if years else None
        if source == "map_expenditures":
            return self.amount_citations("expenditure_agency", year=year)
        if source == "map_federal_grants":
            return self.amount_citations("federal_grant_agency", year=year)
        if source == "map_tax_credits":
            return self.amount_citations("tax_credit_customer", year=year)
        if source == "map_budget_restrictions":
            return self.amount_citations("budget_restricted_agency", year=year)
        if source in LOCAL_SOURCE_FILES:
            return self.local_file_citation(source)
        return []

    def missouri_governor_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": "Mike Kehoe is the governor of Missouri.",
            "retrieved_context_id": "missouri_civic_facts:governor:2026-05-23",
            "retrieved_source": "missouri_civic_fact_lookup",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": (
                "Curated from an official Missouri public web source. For time-sensitive officeholder facts, "
                "verify the linked source if using this after the snapshot date."
            ),
            "citations": [
                {
                    "dataset": "Official Missouri public web source",
                    "category": "Missouri Civic Facts",
                    "kind": "current governor fact",
                    "lookup_table": "curated_official_web_fact",
                    "year": 2026,
                    "year_range": None,
                    "source_files": [
                        {
                            "category": "governor",
                            "category_label": "Governor of Missouri",
                            "file_name": "https://governor.mo.gov/",
                            "source_url": "https://governor.mo.gov/",
                            "row_count": None,
                            "bytes": None,
                            "sha256": None,
                        }
                    ],
                    "source_file_count": 1,
                    "source_rows": None,
                    "matched_rows": 1,
                }
            ],
        }

    def missouri_capital_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": "Missouri's state capital is Jefferson City.",
            "retrieved_context_id": "missouri_civic_facts:capital:2026-05-24",
            "retrieved_source": "missouri_civic_fact_lookup",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Curated from the official Missouri state website's Learn About Missouri page.",
            "citations": [
                {
                    "dataset": "Official Missouri public web source",
                    "category": "Missouri Civic Facts",
                    "kind": "state capital fact",
                    "lookup_table": "curated_official_web_fact",
                    "year": 2026,
                    "year_range": None,
                    "source_files": [
                        {
                            "category": "state_facts",
                            "category_label": "Learn About Missouri",
                            "file_name": "https://www.mo.gov/education/learn-about-missouri",
                            "source_url": "https://www.mo.gov/education/learn-about-missouri",
                            "row_count": None,
                            "bytes": None,
                            "sha256": None,
                        }
                    ],
                    "source_file_count": 1,
                    "source_rows": None,
                    "matched_rows": 1,
                }
            ],
        }

    def map_definition_answer(self, question: str) -> dict[str, Any]:
        return {
            "question": question,
            "answer": (
                "MAP means the Missouri Accountability Portal. In this project, MAP is used as a public source for "
                "Missouri state expenditure, employee-pay, tax-credit, federal-grant, budget-restriction, and bond lookup files."
            ),
            "retrieved_context_id": "missouri_civic_facts:map_definition:2026-05-24",
            "retrieved_source": "missouri_civic_fact_lookup",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Linked to the public Missouri Accountability Portal and its download page.",
            "citations": [
                {
                    "dataset": "Missouri Accountability Portal",
                    "category": "Missouri Civic Facts",
                    "kind": "public portal definition",
                    "lookup_table": "curated_official_web_fact",
                    "year": 2026,
                    "year_range": None,
                    "source_files": [
                        {
                            "category": "map",
                            "category_label": "Missouri Accountability Portal",
                            "file_name": "https://mapyourtaxes.mo.gov/",
                            "source_url": "https://mapyourtaxes.mo.gov/",
                            "row_count": None,
                            "bytes": None,
                            "sha256": None,
                        },
                        {
                            "category": "map_downloads",
                            "category_label": "Missouri Accountability Portal downloads",
                            "file_name": "https://mapyourtaxes.mo.gov/MAP/Download/",
                            "source_url": "https://mapyourtaxes.mo.gov/MAP/Download/",
                            "row_count": None,
                            "bytes": None,
                            "sha256": None,
                        },
                    ],
                    "source_file_count": 2,
                    "source_rows": None,
                    "matched_rows": 1,
                }
            ],
        }

    def contract_citations(self, contract: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        source_files = [
            {
                "category": "contracts",
                "category_label": "MissouriBUYS Contract Board",
                "file_name": "https://missouribuys.mo.gov/contractboard",
                "source_url": "https://missouribuys.mo.gov/contractboard",
                "row_count": None,
                "bytes": None,
                "sha256": None,
            },
            {
                "category": "contracts",
                "category_label": "Office of Administration Contract Search",
                "file_name": "https://archive.oa.mo.gov/purch/contracts/",
                "source_url": "https://archive.oa.mo.gov/purch/contracts/",
                "row_count": None,
                "bytes": None,
                "sha256": None,
            },
        ]
        if contract:
            source_files.append(
                {
                    "category": "contracts",
                    "category_label": "Contract Detail",
                    "file_name": contract.get("detail_url", ""),
                    "source_url": contract.get("detail_url", ""),
                    "row_count": None,
                    "bytes": None,
                    "sha256": None,
                }
            )
            for document in contract.get("document_links", [])[:3]:
                source_files.append(
                    {
                        "category": "contracts",
                        "category_label": document.get("label", "Contract document"),
                        "file_name": document.get("url", ""),
                        "source_url": document.get("url", ""),
                        "row_count": None,
                        "bytes": None,
                        "sha256": None,
                    }
                )
        return [
            {
                "dataset": "Missouri public contract metadata",
                "category": "Missouri Contracts",
                "kind": "contract metadata lookup",
                "lookup_table": "local_contract_metadata_index",
                "year": None,
                "year_range": None,
                "source_files": source_files,
                "source_file_count": len(source_files),
                "source_rows": None,
                "matched_rows": 1 if contract else None,
            }
        ]

    def public_source_catalog_answer(self, question: str) -> dict[str, Any]:
        grouped = catalog_by_status()
        indexed = grouped.get("indexed", [])
        source_indexed = grouped.get("source indexed", [])
        planned = grouped.get("planned", [])
        optional = grouped.get("local optional extraction", [])
        watchlist = grouped.get("watchlist", [])
        lines = [
            "Best public-data expansion targets for this chatbot:",
            "",
            "Already connected:",
        ]
        for source in indexed:
            lines.append(f"- {source['label']}: {source['use_case']}")
        lines.append("")
        lines.append("Source-indexed additions:")
        for source in source_indexed:
            lines.append(f"- {source['label']}: {source['use_case']}")
        lines.append("")
        lines.append("High-value next additions:")
        for source in [*optional, *planned[:5]]:
            lines.append(f"- {source['label']}: {source['use_case']}")
        if watchlist:
            lines.append("")
            lines.append("Watchlist:")
            for source in watchlist:
                lines.append(f"- {source['label']}: {source['use_case']} Access note: {source['access']}")
        lines.append("")
        lines.append(
            "Product direction: prioritize contracts first because the bot can combine contract metadata, document links, "
            "plain-English document summaries, and MAP payment totals into one cited answer."
        )
        return {
            "question": question,
            "answer": "\n".join(lines),
            "retrieved_context_id": "missouri_public_source_catalog:curated",
            "retrieved_source": "missouri_public_source_catalog",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Curated registry of official Missouri public-data sources checked during project research.",
            "citations": [
                {
                    "dataset": "Missouri public-data source catalog",
                    "category": "Public Data Source Registry",
                    "kind": "curated source registry",
                    "lookup_table": "public_source_catalog",
                    "year": 2026,
                    "year_range": None,
                    "source_files": [
                        {
                            "category": source["domain"],
                            "category_label": source["label"],
                            "file_name": source["url"],
                            "row_count": None,
                            "bytes": None,
                            "sha256": None,
                        }
                        for source in PUBLIC_SOURCE_CATALOG
                    ],
                    "source_file_count": len(PUBLIC_SOURCE_CATALOG),
                    "source_rows": None,
                    "matched_rows": len(PUBLIC_SOURCE_CATALOG),
                }
            ],
            "suggestions": [
                "Explain contract CC221256001 in simple terms.",
                "What public data sources can this project add next?",
                "Find contract CC221256001 and show its document links.",
                "What can I ask?",
            ],
        }

    def contract_document_text_summary_answer(self, question: str) -> dict[str, Any]:
        summary = self.contract_document_index.summary()
        if not summary.get("available"):
            answer = (
                "The contract document text index has not been built yet. Run "
                "`python scripts/build_contract_document_index.py --limit 25 --max-mb 25` to download a capped local "
                "sample of public contract PDFs and extract text for plain-English lookup."
            )
            examples: list[dict[str, Any]] = []
        else:
            examples = list(summary.get("examples") or [])
            example_text = "; ".join(
                f"{item.get('contract_number')} {item.get('description') or item.get('label')}"
                for item in examples[:3]
                if item.get("contract_number")
            )
            answer = (
                "The contract document text layer indexes capped text from public OA contract PDFs. "
                f"It currently has {summary.get('document_count', 0):,} PDF(s) extracted from "
                f"{summary.get('candidate_pdf_count', 0):,} candidate PDF link(s), with "
                f"{summary.get('downloaded_mb', 0)} MB downloaded locally and up to "
                f"{summary.get('max_chars_per_document', 0):,} extracted characters per document. "
                "It supports plain-English contract explanations and targeted snippet searches such as renewal, "
                "expiration, scope, purpose, and public-use language. "
                f"Indexed examples: {example_text or 'examples unavailable'}."
            )
        return {
            "question": question,
            "answer": answer,
            "retrieved_context_id": "missouri_contract_documents:summary",
            "retrieved_source": "missouri_contract_document_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Capped local text extraction from public OA contract PDFs; downloaded PDFs are ignored by Git.",
            "citations": self.contract_citations(),
            "source_rows": [{"source_file": item.get("url"), "values": item} for item in examples[:3]],
        }

    def contract_document_query_terms(self, question: str) -> list[str]:
        lowered = question.lower()
        phrase_terms = [
            "contract period",
            "renewal",
            "expiration",
            "termination",
            "scope of work",
            "purpose",
            "pricing",
            "delivery",
            "insurance",
            "public use",
            "cooperative",
            "award",
        ]
        terms = [term for term in phrase_terms if term in lowered]
        if terms:
            return list(dict.fromkeys(terms))[:6]
        if re.search(r"\b(document text|pdf text|extracted text)\b", lowered):
            return ["contract period"]
        stop_terms = {
            "contract",
            "contracts",
            "find",
            "search",
            "show",
            "snippet",
            "language",
            "mention",
            "mentions",
            "inside",
            "document",
            "text",
            "pdf",
            "for",
            "from",
            "that",
            "this",
            "what",
            "does",
            "mean",
            "about",
        }
        for token in retrieval_tokens(question):
            if token in stop_terms:
                continue
            if not re.fullmatch(r"cc\d+[a-z0-9]*", token):
                terms.append(token)
        return list(dict.fromkeys(terms))[:6]

    def contract_document_snippet_answer(self, question: str, contract: dict[str, Any]) -> dict[str, Any]:
        document = self.contract_document_index.find_by_contract_number(contract["contract_number"])
        if not document:
            return {
                "question": question,
                "answer": (
                    f"Contract {contract['contract_number']} is indexed, but its PDF text is not in the capped local "
                    "contract document text index yet. I can still cite the contract detail page and document links."
                ),
                "retrieved_context_id": f"missouri_contract_documents:not_indexed:{contract['contract_number']}",
                "retrieved_source": "missouri_contract_document_index",
                "retrieval_score": 0.5,
                "used_model": False,
                "model": "deterministic_public_lookup",
                "source_note": "Contract metadata is available, but capped PDF text extraction has not indexed this contract document.",
                "citations": self.contract_citations(contract),
                "source_rows": [{"source_file": contract.get("detail_url"), "values": contract}],
            }
        terms = self.contract_document_query_terms(question)
        snippets = self.contract_document_index.search_snippets(contract["contract_number"], terms)
        if not snippets and document.get("text"):
            snippets = [clean_answer_text(str(document.get("text") or "")[:500])]
        snippet_text = " | ".join(snippets[:3]) if snippets else "No matching text snippet was found in the extracted document text."
        return {
            "question": question,
            "answer": (
                f"Contract document text for {contract['contract_number']} ({contract.get('description')}): "
                f"{snippet_text} Source document: {document.get('url')}."
            ),
            "retrieved_context_id": f"missouri_contract_documents:snippet:{contract['contract_number']}",
            "retrieved_source": "missouri_contract_document_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": (
                "Snippet from capped local extraction of a public OA contract PDF. Use the official linked document "
                "for full legal terms."
            ),
            "citations": self.contract_citations(contract),
            "source_rows": [
                {
                    "source_file": document.get("url"),
                    "values": {
                        "contract_number": document.get("contract_number"),
                        "label": document.get("label"),
                        "page_count": document.get("page_count"),
                        "text_chars": document.get("text_chars"),
                        "query_terms": terms,
                        "snippets": snippets[:3],
                    },
                }
            ],
        }

    def plain_language_contract_answer(self, question: str, contract: dict[str, Any]) -> dict[str, Any]:
        documents = contract.get("document_links", [])
        document = self.contract_document_index.find_by_contract_number(contract["contract_number"])
        lines = [
            f"Plain-English contract summary for {contract['contract_number']}:",
            f"- What it is: {contract.get('description') or 'The indexed metadata does not include a description.'}",
            f"- Vendor: {contract.get('contractor') or 'Not listed in the indexed metadata.'}",
        ]
        if contract.get("contract_type"):
            lines.append(f"- Contract type: {contract['contract_type']}")
        if contract.get("category"):
            lines.append(f"- Category: {contract['category']}")
        if contract.get("contract_period"):
            lines.append(f"- Term: {contract['contract_period']}")
        elif contract.get("expiration_date"):
            lines.append(f"- Expiration: {contract['expiration_date']}")
        if contract.get("renewable"):
            lines.append(f"- Renewable flag: {contract['renewable']}")
        if contract.get("coop"):
            lines.append(f"- Cooperative purchasing flag: {contract['coop']}")
        if documents:
            lines.append("- Source documents: " + "; ".join(f"{doc['label']}: {doc['url']}" for doc in documents[:3]))
        if document and document.get("text"):
            text = str(document["text"])
            snippets = []
            for pattern in [
                r"(?i)(?:contract period|effective date|expiration date|renewal).*?(?:\.|$)",
                r"(?i)(?:scope of work|purpose|description).*?(?:\.|$)",
                r"(?i)(?:all purchases made under this contract).*?(?:\.|$)",
            ]:
                match = re.search(pattern, text)
                if match:
                    snippets.append(clean_answer_text(match.group(0)))
            if snippets:
                lines.append("- Document text signals: " + " ".join(snippets[:3]))
            else:
                excerpt = clean_answer_text(text[:500])
                if excerpt:
                    lines.append(f"- Document text excerpt: {excerpt}")
            lines.append(
                f"- Local document index: extracted {document.get('text_chars', 0):,} text characters "
                f"from {document.get('page_count', '?')} PDF page(s)."
            )
        else:
            lines.append(
                "- Document text: not extracted in the local document index yet. Run "
                "`python scripts/build_contract_document_index.py --limit 25 --max-mb 25` to enable document-text snippets."
            )
        payment_context = self.payment_context_for_contractor(contract.get("contractor", ""), contract.get("contract_period"))
        if payment_context:
            lines.append(f"- MAP payment context: {payment_context}")
        else:
            lines.append("- MAP payment context: no confident vendor-payment match found in the local MAP index.")
        lines.append(
            "- Bottom line: this is a public procurement record; use the linked documents for legal terms and the MAP context for payment history."
        )
        return {
            "question": question,
            "answer": "\n".join(lines),
            "retrieved_context_id": f"missouri_contracts:explain:{contract['contract_number']}",
            "retrieved_source": "missouri_contract_metadata_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": (
                "Plain-English summary from indexed contract metadata, optional local PDF text extraction, "
                "and MAP vendor-payment context when available."
            ),
            "citations": self.contract_citations(contract),
        }

    def payment_context_for_contractor(self, contractor: str, contract_period: str | None = None) -> str | None:
        if not contractor or not self.map_index.available():
            return None
        row = self.map_index.find_amount(contractor, ["expenditure_vendor", "stimulus_vendor"])
        if row is None:
            return None
        period_years = [int(year) for year in re.findall(r"\b(19\d{2}|20\d{2})\b", contract_period or "")]
        if period_years:
            year_rows = self.map_index.amount_year_rows(row["kind"], row["name_norm"])
            min_year = min(period_years)
            max_year = max(period_years)
            matching_rows = [item for item in year_rows if min_year <= item["year"] <= max_year]
            if not matching_rows:
                return (
                    f"I found likely matching MAP vendor {row['display_name']}, but no indexed MAP payment total "
                    f"for that vendor during contract-period years {min_year}-{max_year}."
                )
            amount = sum(Decimal(str(item["amount"])) for item in matching_rows)
            row_count = sum(int(item["row_count"]) for item in matching_rows)
            years = (
                str(matching_rows[0]["year"])
                if matching_rows[0]["year"] == matching_rows[-1]["year"]
                else f"{min(item['year'] for item in matching_rows)}-{max(item['year'] for item in matching_rows)}"
            )
            return (
                f"Indexed MAP payments to likely matching vendor {row['display_name']} total "
                f"{format_lookup_money(amount)} across {years} ({row_count:,} payment row(s))."
            )
        aggregate = self.map_index.aggregate_amount(row["kind"], row["name_norm"])
        if not aggregate:
            return None
        years = (
            str(aggregate["min_year"])
            if aggregate["min_year"] == aggregate["max_year"]
            else f"{aggregate['min_year']}-{aggregate['max_year']}"
        )
        return (
            f"Indexed MAP payments to likely matching vendor {aggregate['display_name']} total "
            f"{format_lookup_money(aggregate['amount'])} across {years} "
            f"({aggregate['row_count']:,} payment row(s))."
        )

    def contract_period_years(self, contract: dict[str, Any]) -> tuple[int, int] | None:
        years = [int(year) for year in re.findall(r"\b(19\d{2}|20\d{2})\b", contract.get("contract_period") or "")]
        if not years:
            return None
        return min(years), max(years)

    def contract_vendor_payment_context(self, contract: dict[str, Any]) -> dict[str, Any] | None:
        contractor = contract.get("contractor") or ""
        vendor_norm = normalize_public_name(contractor)
        if not vendor_norm or not self.map_index.available():
            return None
        period = self.contract_period_years(contract)
        with self.map_index.connect() as conn:
            if period:
                min_year, max_year = period
                summary = conn.execute(
                    """
                    select sum(amount) as amount, sum(row_count) as row_count,
                           min(year) as min_year, max(year) as max_year
                    from public_amount_lookup
                    where kind = 'expenditure_vendor'
                      and name_norm = ?
                      and year between ? and ?
                    """,
                    [vendor_norm, min_year, max_year],
                ).fetchone()
                top_rows = conn.execute(
                    """
                    select agency_norm, agency_name, year, amount, row_count
                    from expenditure_agency_vendor
                    where vendor_norm = ?
                      and year between ? and ?
                    order by amount desc
                    limit 5
                    """,
                    [vendor_norm, min_year, max_year],
                ).fetchall()
            else:
                summary = conn.execute(
                    """
                    select sum(amount) as amount, sum(row_count) as row_count,
                           min(year) as min_year, max(year) as max_year
                    from public_amount_lookup
                    where kind = 'expenditure_vendor'
                      and name_norm = ?
                    """,
                    [vendor_norm],
                ).fetchone()
                top_rows = conn.execute(
                    """
                    select agency_norm, agency_name, year, amount, row_count
                    from expenditure_agency_vendor
                    where vendor_norm = ?
                    order by amount desc
                    limit 5
                    """,
                    [vendor_norm],
                ).fetchall()
        if summary is None or summary["amount"] is None:
            any_year = self.map_index.find_amount_any_year(contractor, ["expenditure_vendor"])
            return {
                "vendor_norm": vendor_norm,
                "vendor_name": contractor,
                "period": period,
                "summary": None,
                "top_rows": [],
                "any_year": dict(any_year) if any_year else None,
            }
        return {
            "vendor_norm": vendor_norm,
            "vendor_name": contractor,
            "period": period,
            "summary": dict(summary),
            "top_rows": [dict(row) for row in top_rows],
            "any_year": None,
        }

    def contract_payment_answer(self, question: str, contract: dict[str, Any]) -> dict[str, Any]:
        context = self.contract_vendor_payment_context(contract)
        citations = self.contract_citations(contract)
        source_rows: list[dict[str, Any]] = []
        matched_rows = None
        if context is None:
            answer = (
                f"Contract {contract['contract_number']} is indexed, but I could not compute MAP vendor-payment context "
                "because the local MAP lookup index is unavailable or the contractor name is missing."
            )
        elif context.get("summary"):
            summary = context["summary"]
            period = context.get("period")
            if period:
                period_text = f"contract-period years {period[0]}-{period[1]}"
                year_range = f"{period[0]}-{period[1]}"
            else:
                period_text = f"indexed years {summary.get('min_year')}-{summary.get('max_year')}"
                year_range = f"{summary.get('min_year')}-{summary.get('max_year')}"
            total = format_lookup_money(summary["amount"])
            top_rows = context.get("top_rows", [])
            top_text = "; ".join(
                f"{index}. {row['agency_name']} in {row['year']}: {format_lookup_money(row['amount'])}"
                for index, row in enumerate(top_rows[:5], start=1)
            )
            matched_rows = summary.get("row_count")
            answer = (
                f"Contract {contract['contract_number']} is with {contract.get('contractor')}. "
                f"MAP lists {total} paid to matching vendor {context['vendor_norm']} across {period_text} "
                f"({int(matched_rows or 0):,} MAP row(s)). "
                "This is vendor payment context matched by contractor name, not proof that every payment was made under this exact contract number."
            )
            if top_text:
                answer += f" Top paying agencies in that window: {top_text}."
            citations.extend(self.amount_citations("expenditure_vendor", entity_rows=matched_rows, year_range=year_range))
            for row in top_rows[:3]:
                source_rows.extend(
                    self.map_index.agency_vendor_source_rows(
                        int(row["year"]),
                        row["agency_norm"],
                        context["vendor_norm"],
                        limit=1,
                    )
                )
        else:
            any_year = context.get("any_year")
            period = context.get("period")
            if any_year and period:
                answer = (
                    f"Contract {contract['contract_number']} is with {contract.get('contractor')}. "
                    f"I found matching MAP vendor {any_year['display_name']}, but no indexed MAP expenditure total "
                    f"for that vendor during contract-period years {period[0]}-{period[1]}. "
                    f"Outside that period, the closest indexed MAP expenditure row is {format_lookup_money(any_year['amount'])} "
                    f"in {any_year['year']}. This is vendor payment context, not contract-specific disbursement proof."
                )
            elif any_year:
                answer = (
                    f"Contract {contract['contract_number']} is with {contract.get('contractor')}. "
                    f"The closest indexed MAP vendor payment row is {format_lookup_money(any_year['amount'])} "
                    f"for {any_year['display_name']} in {any_year['year']}. "
                    "This is vendor payment context, not contract-specific disbursement proof."
                )
            else:
                answer = (
                    f"Contract {contract['contract_number']} is with {contract.get('contractor')}, but I could not find "
                    "a confident MAP expenditure-vendor match for that contractor name."
                )
            citations.extend(self.amount_citations("expenditure_vendor", entity_rows=0))
            matched_rows = 0
        return {
            "question": question,
            "answer": answer,
            "retrieved_context_id": f"missouri_contracts:payment_context:{contract['contract_number']}",
            "retrieved_source": "missouri_contract_metadata_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": (
                "Computed from public contract metadata plus MAP expenditure-vendor aggregates. "
                "The MAP match is by contractor/vendor name and should not be treated as a contract-number accounting ledger."
            ),
            "citations": citations,
            "source_rows": source_rows[:5],
            "matched_rows": matched_rows,
        }

    def contract_answer(self, question: str) -> dict[str, Any]:
        summary = self.contract_index.summary()
        if asks_about_contract_document_index(question) and not self.contract_index.find_by_number(question):
            return self.contract_document_text_summary_answer(question)
        if not self.contract_index.available():
            return {
                "question": question,
                "answer": (
                    "The contract metadata index has not been built yet. Run "
                    "`python scripts/build_contract_index.py --detail-limit 200` to index MissouriBUYS/OA "
                    "public contract metadata without downloading contract documents."
                ),
                "retrieved_context_id": "missouri_contracts:index_missing",
                "retrieved_source": "missouri_contract_metadata_index",
                "retrieval_score": 0.0,
                "used_model": False,
                "model": "deterministic_public_lookup",
                "source_note": "Contract source registry is available, but the local ignored contract index is missing.",
                "citations": self.contract_citations(),
            }

        contract = self.contract_index.find_by_number(question)
        if contract is None:
            matches = self.contract_index.search(question, limit=requested_limit(question, default=5, maximum=10))
            if not matches:
                return {
                    "question": question,
                    "answer": (
                        f"The local contract index has {summary['contract_count']:,} public contract records, "
                        "but I could not match this question to a contract number, contractor, or contract description."
                    ),
                    "retrieved_context_id": "missouri_contracts:no_match",
                    "retrieved_source": "missouri_contract_metadata_index",
                    "retrieval_score": 0.0,
                    "used_model": False,
                    "model": "deterministic_public_lookup",
                    "source_note": "Try a contract number, contractor name, or contract category from the Contract Board.",
                    "citations": self.contract_citations(),
                }
            lines = []
            for index, match in enumerate(matches, start=1):
                period = f"; period {match['contract_period']}" if match.get("contract_period") else ""
                lines.append(
                    f"{index}. {match['contract_number']} - {match['description']} - "
                    f"{match['contractor']} (expires {match['expiration_date']}{period})"
                )
            return {
                "question": question,
                "answer": (
                    f"Top contract matches from {summary['contract_count']:,} indexed public contract records:\n"
                    + "\n".join(lines)
                ),
                "retrieved_context_id": "missouri_contracts:search",
                "retrieved_source": "missouri_contract_metadata_index",
                "retrieval_score": 1.0,
                "used_model": False,
                "model": "deterministic_public_lookup",
                "source_note": "Contract metadata is indexed locally from public MissouriBUYS/OA pages.",
                "citations": self.contract_citations(matches[0]),
            }

        if asks_for_contract_payment_context(question):
            return self.contract_payment_answer(question, contract)

        if asks_for_contract_document_snippet(question):
            return self.contract_document_snippet_answer(question, contract)

        if asks_for_contract_explanation(question):
            return self.plain_language_contract_answer(question, contract)

        lines = [
            f"Contract {contract['contract_number']}: {contract['description']}.",
            f"Contractor: {contract['contractor']}.",
        ]
        if contract.get("contract_type"):
            lines.append(f"Type: {contract['contract_type']}.")
        if contract.get("category"):
            lines.append(f"Category: {contract['category']}.")
        if contract.get("contract_period"):
            lines.append(f"Contract period: {contract['contract_period']}.")
        elif contract.get("expiration_date"):
            lines.append(f"Expiration date: {contract['expiration_date']}.")
        lines.append(f"Detail page: {contract['detail_url']}.")
        documents = contract.get("document_links", [])
        if documents:
            doc_text = "; ".join(f"{doc['label']}: {doc['url']}" for doc in documents[:3])
            lines.append(f"Documents: {doc_text}.")
        payment_context = self.payment_context_for_contractor(contract.get("contractor", ""), contract.get("contract_period"))
        if payment_context:
            lines.append(payment_context)
        else:
            lines.append("I did not find a confident MAP vendor-payment match for this contractor name.")
        return {
            "question": question,
            "answer": " ".join(lines),
            "retrieved_context_id": f"missouri_contracts:{contract['contract_number']}",
            "retrieved_source": "missouri_contract_metadata_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": (
                "Contract metadata comes from public MissouriBUYS/OA pages. Payment totals, when present, "
                "come from the separate local MAP expenditure index."
            ),
            "citations": self.contract_citations(contract),
        }

    def public_amount_answer(self, question: str, kinds: list[str], label: str) -> dict[str, Any] | None:
        years = years_in_question(question)
        row = self.map_index.find_amount(question, kinds)
        if row is None:
            if years:
                any_year_row = self.map_index.find_amount_any_year(question, kinds)
                if any_year_row is not None:
                    aggregate = self.map_index.aggregate_amount(any_year_row["kind"], any_year_row["name_norm"])
                    requested_years = ", ".join(str(year) for year in years)
                    available = ""
                    if aggregate:
                        available = f" Available indexed years for {aggregate['display_name']} are {aggregate['min_year']}-{aggregate['max_year']}."
                    return {
                        "question": question,
                        "answer": (
                            f"I found {any_year_row['display_name']} in the indexed MAP {label} data, "
                            f"but not for requested year(s) {requested_years}.{available}"
                        ),
                        "retrieved_context_id": f"map_public_index:no_year_match:{any_year_row['kind']}:{any_year_row['name_norm']}",
                        "retrieved_source": "map_public_lookup_index",
                        "retrieval_score": 1.0,
                        "used_model": False,
                        "model": "deterministic_public_lookup",
                        "source_note": "No row matched the requested year filter in the local MAP index.",
                        "citations": self.amount_citations(
                            any_year_row["kind"],
                            year_range=(
                                f"{aggregate['min_year']}-{aggregate['max_year']}" if aggregate else None
                            ),
                        ),
                    }
            return None
        if not years:
            aggregate = self.map_index.aggregate_amount(row["kind"], row["name_norm"])
            if aggregate is not None and aggregate.get("year_count", 0) > 1:
                min_year = aggregate.get("min_year")
                max_year = aggregate.get("max_year")
                year_text = f"{min_year}-{max_year}" if min_year and max_year else "all indexed years"
                return {
                    "question": question,
                    "answer": (
                        f"The indexed MAP {label} data lists {format_lookup_money(aggregate['amount'])} "
                        f"for {aggregate['display_name']} across {aggregate['row_count']:,} row(s) "
                        f"for {year_text}."
                    ),
                    "retrieved_context_id": f"map_public_index:{row['kind']}:{row['name_norm']}",
                    "retrieved_source": "map_public_lookup_index",
                    "retrieval_score": 1.0,
                    "used_model": False,
                    "model": "deterministic_public_lookup",
                    "source_note": "Computed from the local SQLite index built from public MAP downloads.",
                    "citations": self.amount_citations(
                        row["kind"],
                        entity_rows=aggregate["row_count"],
                        year_range=year_text,
                    ),
                    "source_rows": [],
                }
        year_text = str(row["year"]) if row["year"] else "the indexed cumulative file"
        return {
            "question": question,
            "answer": (
                f"The indexed MAP {label} data lists {format_lookup_money(row['amount'])} "
                f"for {row['display_name']} in {year_text} across {row['row_count']:,} row(s)."
            ),
            "retrieved_context_id": f"map_public_index:{row['kind']}:{row['year']}:{row['name_norm']}",
            "retrieved_source": "map_public_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local SQLite index built from public MAP downloads.",
            "citations": self.amount_citations(row["kind"], year=row["year"], entity_rows=row["row_count"]),
            "source_rows": self.map_index.amount_source_rows(row["kind"], row["year"], row["name_norm"]),
        }

    def employee_answer(self, question: str) -> dict[str, Any] | None:
        row = self.map_index.find_employee(question)
        if row is None:
            return None
        lowered = question.lower()
        if "where" in lowered or "work" in lowered or "agency" in lowered:
            answer = (
                f"The indexed MAP employee data lists {row['employee_name']} under agency "
                f"{row['agency_name']} in calendar year {row['calendar_year']}. "
                f"Position: {row['position_title']}."
            )
        elif "position" in lowered or "title" in lowered:
            answer = (
                f"The indexed MAP employee data lists {row['employee_name']} as "
                f"{row['position_title']} in calendar year {row['calendar_year']}. "
                f"Agency: {row['agency_name']}."
            )
        else:
            answer = (
                f"The indexed MAP employee data lists {format_lookup_money(row['ytd_gross_pay'])} "
                f"in YTD gross pay for {row['employee_name']} in calendar year {row['calendar_year']}. "
                f"Agency: {row['agency_name']}. Position: {row['position_title']}."
            )
        return {
            "question": question,
            "answer": answer,
            "retrieved_context_id": f"map_employee_lookup:{row['calendar_year']}:{row['employee_norm']}",
            "retrieved_source": "map_employee_public_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from indexed public MAP employee files.",
            "citations": self.employee_citations(year=row["calendar_year"], matched_rows=row["row_count"]),
            "source_rows": [],
        }

    def top_employee_pay_answer(self, question: str) -> dict[str, Any] | None:
        limit = requested_limit(question, default=1, maximum=25)
        rows = self.map_index.top_employees(question, limit=max(limit, 25))
        if not rows:
            return None

        year = rows[0]["calendar_year"]
        display_rows = rows[:limit]
        top_row = rows[0]
        top_named = next((row for row in rows if not is_aggregate_employee_name(row["employee_name"])), None)
        matched_rows = sum(int(row["row_count"]) for row in display_rows)

        if limit == 1:
            answer = (
                f"The highest indexed MAP employee-pay entry for {year} is {top_row['employee_name']} "
                f"under {top_row['agency_name']} with {format_lookup_money(top_row['ytd_gross_pay'])} "
                f"in YTD gross pay across {top_row['row_count']:,} source row(s). "
                f"Position: {top_row['position_title']}."
            )
            if is_aggregate_employee_name(top_row["employee_name"]) and top_named is not None:
                answer += (
                    f" That top entry appears to be a protected or aggregate public record rather than one named person. "
                    f"The highest named individual in the same indexed year is {top_named['employee_name']} "
                    f"under {top_named['agency_name']} with {format_lookup_money(top_named['ytd_gross_pay'])} "
                    f"in YTD gross pay. Position: {top_named['position_title']}."
                )
        else:
            rendered = []
            for index, row in enumerate(display_rows, start=1):
                aggregate_note = " (protected/aggregate entry)" if is_aggregate_employee_name(row["employee_name"]) else ""
                rendered.append(
                    f"{index}. {row['employee_name']}{aggregate_note} - {row['agency_name']} - "
                    f"{row['position_title']} - {format_lookup_money(row['ytd_gross_pay'])} "
                    f"across {row['row_count']:,} row(s)"
                )
            answer = f"Top indexed MAP employee-pay entries for {year}:\n" + "\n".join(rendered)
            answer += "\nEntries marked protected/aggregate should not be interpreted as one named person's pay."

        return {
            "question": question,
            "answer": answer,
            "retrieved_context_id": f"map_employee_lookup:top_pay:{year}",
            "retrieved_source": "map_employee_public_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed by ranking indexed public MAP employee pay records.",
            "citations": self.employee_citations(year=year, matched_rows=matched_rows),
            "source_rows": [],
        }

    def agency_vendor_answer(self, question: str) -> dict[str, Any] | None:
        row = self.map_index.find_agency_vendor_payment(question)
        if row is None:
            return None
        return {
            "question": question,
            "answer": (
                f"The indexed MAP expenditure data lists {format_lookup_money(row['amount'])} paid by "
                f"{row['agency_name']} to {row['vendor_name']} in {row['year']} across {row['row_count']:,} row(s)."
            ),
            "retrieved_context_id": f"map_agency_vendor:{row['year']}:{row['agency_norm']}:{row['vendor_norm']}",
            "retrieved_source": "map_expenditure_agency_vendor_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local MAP expenditure agency-vendor aggregate index.",
            "citations": self.agency_vendor_citations(year=row["year"], matched_rows=row["row_count"]),
            "source_rows": self.map_index.agency_vendor_source_rows(row["year"], row["agency_norm"], row["vendor_norm"]),
        }

    def top_vendors_for_agency_answer(self, question: str) -> dict[str, Any] | None:
        limit = requested_limit(question)
        rows = self.map_index.top_vendors_for_agency(question, limit=limit)
        if not rows:
            return None
        first = rows[0]
        year_text = (
            str(first["min_year"])
            if first["min_year"] == first["max_year"]
            else f"{first['min_year']}-{first['max_year']}"
        )
        lines = [
            f"{index}. {row['label']}: {row['amount']} ({row['row_count']:,} row(s))"
            for index, row in enumerate(rows, 1)
        ]
        return {
            "question": question,
            "answer": f"Top indexed MAP vendors for {first['agency']} in {year_text}:\n" + "\n".join(lines),
            "retrieved_context_id": f"map_agency_vendor_top:{first['agency']}:{year_text}",
            "retrieved_source": "map_expenditure_agency_vendor_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local MAP expenditure agency-vendor aggregate index.",
            "citations": self.agency_vendor_citations(
                year=first["min_year"] if first["min_year"] == first["max_year"] else None,
                matched_rows=sum(row["row_count"] for row in rows),
            ),
        }

    def top_agencies_for_vendor_answer(self, question: str) -> dict[str, Any] | None:
        limit = requested_limit(question)
        rows = self.map_index.top_agencies_for_vendor(question, limit=limit)
        if not rows:
            return None
        first = rows[0]
        year_text = (
            str(first["min_year"])
            if first["min_year"] == first["max_year"]
            else f"{first['min_year']}-{first['max_year']}"
        )
        lines = [
            f"{index}. {row['label']}: {row['amount']} ({row['row_count']:,} row(s))"
            for index, row in enumerate(rows, 1)
        ]
        return {
            "question": question,
            "answer": f"Indexed MAP agencies paying {first['vendor']} in {year_text}:\n" + "\n".join(lines),
            "retrieved_context_id": f"map_agency_vendor_top_agencies:{first['vendor']}:{year_text}",
            "retrieved_source": "map_expenditure_agency_vendor_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local MAP expenditure agency-vendor aggregate index.",
            "citations": self.agency_vendor_citations(
                year=first["min_year"] if first["min_year"] == first["max_year"] else None,
                matched_rows=sum(row["row_count"] for row in rows),
            ),
        }

    def help_answer(self, question: str) -> dict[str, Any]:
        coverage = self.map_index.coverage()
        categories = coverage.get("categories", [])
        category_text = ", ".join(item["label"] for item in categories) if categories else "MAP lookup index unavailable"
        examples = [
            "What was the aggregate MAP expenditure total for TRANSPORTATION in 2025?",
            "How much was paid to CAPITAL MALL JC 1 LLC in 2025?",
            "What was Kory Hubbard's YTD gross pay in 2026?",
            "What tax credit amount was issued to CARTWRIGHT HOLDINGS in 2026?",
            "How much federal grant money did ECONOMIC DEVELOPMENT receive in 2026?",
            "What are the top expenditure agencies in 2025?",
            "How many licensed hospital beds are in the processed hospital profile source?",
            "How many high school seniors are listed for Rock Bridge Sr. High in 2026?",
            "How many WIC household rows are listed for Boone County?",
            "What percent of Missouri adults had obesity in BRFSS?",
            "How many inpatient hospitalizations for septicemia are listed in MOPHIMS?",
            "Which MOPHIMS leading cause of death has the highest count?",
            "Give me the BRFSS link.",
            "Give me the DHSS MICA link for inpatient hospitalizations.",
            "How many LTC directory rows are listed for Boone County?",
            "Where can I look up LTC inspections for Boone County?",
            "What are the latest Missouri Auditor reports?",
            "Explain Auditor report 2026-044 in simple terms.",
            "What is the latest PSC report volume?",
            "What is the latest OA executive budget link?",
            "Give me the link for the Joplin Regional Stockyards feeder cattle report.",
            "Give me the link for 2025 APR Ranking - LEAs.",
            "What is the APR score for Atlas Public Schools?",
            "What is Columbia 93's DESE 7% transfer amount?",
            "Which district has the highest DESE 7% transfer amount?",
            "How many Missouri students were in the Autism special-education category in 2024-25?",
            "Which DESE special-education disability category had the highest count in 2024-25?",
            "Who won the 2024 Missouri governor election?",
            "What are the protein values for sample D202500550?",
            "How many verified cannabis dispensaries are in Boone County?",
            "How much adult-use cannabis retail sales were recorded in PY24?",
            "How many child care slots are listed in 2025 Q4?",
            "What is the highest AADT on I-70 eastbound?",
            "Who is the governor of Missouri?",
            "Find contract CC221256001 and show its document links.",
        ]
        return {
            "question": question,
            "answer": (
                "I can answer source-backed questions over the local Missouri public-data index. "
                f"Indexed MAP categories: {category_text}. I can also answer the case-study hospital profile "
                "and LTC aggregate questions, selected data.mo.gov education questions, a small set of sourced Missouri civic facts, "
                "selected DHSS WIC aggregate questions, selected long-term-care directory and census questions, "
                "selected DHSS BRFSS statewide prevalence questions, "
                "selected DHSS statewide vital-statistics aggregate questions, "
                "selected DHSS MOPHIMS statewide profile aggregate questions, "
                "selected DHSS public-health resource-link questions, "
                "selected DHSS long-term-care inspection resource and search-filter questions, "
                "selected data.mo.gov food pantry service-location questions, "
                "selected data.mo.gov farmers-market directory questions, "
                "selected Missouri State Auditor report metadata questions, "
                "selected Missouri State Auditor report PDF explanation questions, "
                "selected SOS official election-return questions, "
                "selected Missouri Public Service Commission report metadata questions, "
                "selected Office of Administration Budget and Planning metadata questions, "
                "selected Missouri Agricultural Market News report-link questions, "
                "selected DESE School Data resource-link questions, "
                "selected DESE APR ranking score/rank questions, "
                "selected DESE school-finance transfer amount questions, "
                "selected DESE special-education statewide incidence and child-count questions, "
                "selected data.mo.gov agriculture feed-sample questions, "
                "selected DHSS cannabis verified-dispensary and annual-report metric questions, "
                "selected DESE child-care dashboard aggregate questions, "
                "selected MoDOT latest-year AADT traffic-volume questions, "
                "and indexed Missouri contract metadata when the local contract index has been built. Exact row-level public records come from "
                "deterministic lookup, not model memory."
            ),
            "retrieved_context_id": "map_public_index:coverage",
            "retrieved_source": "map_public_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "capability_summary",
            "suggestions": examples,
            "coverage": coverage,
        }

    def top_amount_answer(self, question: str, kind: str, label: str) -> dict[str, Any] | None:
        years = years_in_question(question)
        year = years[0] if years else None
        limit = requested_limit(question)
        rows = self.map_index.top_amounts(kind, year=year, limit=limit)
        if not rows:
            if year is not None:
                span = self.map_index.kind_year_span(kind)
                if span:
                    return {
                        "question": question,
                        "answer": (
                            f"I do not have indexed MAP {label} rows for {year}. "
                            f"Available indexed years for this lookup are {span['min_year']}-{span['max_year']}."
                        ),
                        "retrieved_context_id": f"map_public_index:no_top_year:{kind}:{year}",
                        "retrieved_source": "map_public_lookup_index",
                        "retrieval_score": 1.0,
                        "used_model": False,
                        "model": "deterministic_public_lookup",
                        "source_note": "No row matched the requested year filter in the local MAP index.",
                        "citations": self.amount_citations(kind, year_range=f"{span['min_year']}-{span['max_year']}"),
                    }
            return None
        scope = f"in {year}" if year else "across all indexed years"
        lines = [f"{index}. {row['label']}: {row['amount']} ({row['row_count']:,} row(s))" for index, row in enumerate(rows, 1)]
        return {
            "question": question,
            "answer": f"Top indexed MAP {label} {scope}:\n" + "\n".join(lines),
            "retrieved_context_id": f"map_public_index:top:{kind}:{year or 'all'}",
            "retrieved_source": "map_public_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed from the local SQLite index built from public MAP downloads.",
            "citations": self.amount_citations(
                kind,
                year=year,
                entity_rows=sum(row["row_count"] for row in rows),
                year_range=scope.replace("across all indexed years", "all indexed years"),
            ),
        }

    def year_peak_amount_answer(self, question: str, kinds: list[str], label: str) -> dict[str, Any] | None:
        row = self.map_index.find_amount_any_year(question, kinds)
        if row is None:
            return None
        yearly_rows = self.map_index.amount_year_rows(row["kind"], row["name_norm"])
        if not yearly_rows:
            return None
        lowest = any(word in question.lower() for word in ["lowest", "smallest"])
        ordered = sorted(yearly_rows, key=lambda item: Decimal(str(item["amount"])), reverse=not lowest)
        best = ordered[0]
        direction = "lowest" if lowest else "highest"
        comparison = ""
        if len(ordered) > 1:
            runner_up = ordered[1]
            difference = abs(Decimal(str(best["amount"])) - Decimal(str(runner_up["amount"])))
            comparison = (
                f" The next {'lowest' if lowest else 'highest'} indexed year is {runner_up['year']} "
                f"at {runner_up['amount_label']}, a difference of {format_lookup_money(difference)}."
            )
        return {
            "question": question,
            "answer": (
                f"The {direction} indexed MAP {label} for {best['display_name']} is {best['year']}: "
                f"{best['amount_label']} across {best['row_count']:,} row(s).{comparison}"
            ),
            "retrieved_context_id": f"map_public_index:year_peak:{row['kind']}:{row['name_norm']}",
            "retrieved_source": "map_public_lookup_index",
            "retrieval_score": 1.0,
            "used_model": False,
            "model": "deterministic_public_lookup",
            "source_note": "Computed by ranking annual rows in the local MAP lookup index.",
            "citations": self.amount_citations(row["kind"], year=best["year"], entity_rows=best["row_count"]),
            "source_rows": self.map_index.amount_source_rows(row["kind"], best["year"], row["name_norm"]),
        }

    def missing_lookup_answer(
        self,
        question: str,
        source: str,
        message: str,
        suggestions: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "question": question,
            "answer": message,
            "source": source,
            "used_model": False,
            "model": "deterministic_public_lookup",
        }
        if suggestions:
            rendered = []
            for suggestion in suggestions:
                year = f" ({suggestion['year']})" if suggestion.get("year") else ""
                amount = f": {suggestion['amount']}" if suggestion.get("amount") else ""
                rendered.append(f"{suggestion['label']}{year}{amount}")
            payload["answer"] += "\n\nClosest indexed matches:\n" + "\n".join(f"- {item}" for item in rendered)
            payload["suggestions"] = suggestions
        return payload

    def route_question(self, question: str) -> dict[str, Any]:
        if contains_private_identifier_request(question):
            return {
                "question": question,
                "answer": "I cannot help with private identifiers. This demo only answers facts from indexed public datasets.",
                "source": "public_data_boundary",
                "used_model": False,
                "model": "public_data_boundary",
            }

        if asks_unsupported_scope(question):
            return {
                "question": question,
                "answer": (
                    "I do not have indexed source support for that request. This chatbot does not forecast, verify active contracts or endorsements, "
                    "or dump full raw tables. Ask for a specific indexed MAP total, public employee pay record, "
                    "tax-credit record, federal-grant record, budget restriction, bond amount, contract record, MERIC labor-market metric, "
                    "education count, food pantry listing, farmers-market directory listing, DNR drinking-water system, DNR oil-and-gas permit, DNR hazardous-waste facility, DNR impaired-water listing, SOS election-return result, PSC report metadata or selected report-PDF snippet, OA Budget metadata, OA general-revenue detail value, agriculture market-report link, cannabis dispensary/annual-report fact, child-care dashboard fact, hospital aggregate, or LTC aggregate."
                ),
                "source": "unsupported_scope_guardrail",
                "used_model": False,
                "model": "unsupported_scope_guardrail",
                "suggestions": self.help_answer(question)["suggestions"],
            }

        general_result = self.general_chat_answer(question)
        if general_result is not None and general_result.get("retrieved_context_id") != "general_chat:local":
            return general_result

        if asks_about_ag_market_report_document_lookup(question):
            ag_market_document_result = self.ag_market_report_document_index.answer(question)
            if ag_market_document_result is not None:
                return ag_market_document_result

        if asks_about_ag_market_news_lookup(question):
            ag_market_result = self.ag_market_news_index.answer(question)
            if ag_market_result is not None:
                return ag_market_result

        if asks_about_agriculture_lookup(question):
            agriculture_result = self.data_mo_agriculture_index.answer(question)
            if agriculture_result is not None:
                return agriculture_result

        if asks_about_cannabis_lookup(question):
            cannabis_result = self.cannabis_index.answer(question)
            if cannabis_result is not None:
                return cannabis_result

        if asks_about_child_care_lookup(question):
            child_care_result = self.child_care_index.answer(question)
            if child_care_result is not None:
                return child_care_result

        if asks_about_psc_report_document_lookup(question):
            psc_document_result = self.psc_report_document_index.answer(question)
            if psc_document_result is not None:
                return psc_document_result

        if asks_about_psc_reports_lookup(question):
            psc_result = self.psc_reports_index.answer(question)
            if psc_result is not None:
                return psc_result

        if asks_about_oa_revenue_detail_lookup(question):
            oa_revenue_detail_result = self.oa_revenue_detail_index.answer(question)
            if oa_revenue_detail_result is not None:
                return oa_revenue_detail_result

        if asks_about_oa_budget_lookup(question):
            oa_budget_result = self.oa_budget_index.answer(question)
            if oa_budget_result is not None:
                return oa_budget_result

        if asks_about_auditor_document_lookup(question):
            auditor_document_result = self.state_auditor_document_index.answer(question)
            if auditor_document_result is not None:
                return auditor_document_result

        if asks_about_dese_directory_lookup(question):
            return self.dese_directory_index.answer(question)

        if asks_about_dese_apr_lookup(question):
            dese_apr_result = self.dese_apr_index.answer(question)
            if dese_apr_result is not None:
                return dese_apr_result

        if asks_about_dese_finance_lookup(question):
            dese_finance_result = self.dese_finance_index.answer(question)
            if dese_finance_result is not None:
                return dese_finance_result

        if asks_about_dese_special_education_lookup(question):
            dese_special_education_result = self.dese_special_education_index.answer(question)
            if dese_special_education_result is not None:
                return dese_special_education_result

        if asks_about_dese_school_data_lookup(question):
            dese_school_data_result = self.dese_school_data_index.answer(question)
            if dese_school_data_result is not None:
                return dese_school_data_result

        if asks_about_education_lookup(question):
            education_result = self.data_mo_education_index.answer(question)
            if education_result is not None:
                return education_result

        if asks_about_wic_lookup(question):
            wic_result = self.data_mo_wic_index.answer(question)
            if wic_result is not None:
                return wic_result

        if asks_about_food_pantry_lookup(question):
            food_pantry_result = self.data_mo_food_pantry_index.answer(question)
            if food_pantry_result is not None:
                return food_pantry_result

        if asks_about_farmers_market_lookup(question):
            farmers_market_result = self.data_mo_farmers_market_index.answer(question)
            if farmers_market_result is not None:
                return farmers_market_result

        if asks_about_dhss_brfss_lookup(question):
            brfss_result = self.dhss_brfss_index.answer(question)
            if brfss_result is not None:
                return brfss_result

        if asks_about_dhss_vital_stats_lookup(question):
            vital_stats_result = self.dhss_vital_stats_index.answer(question)
            if vital_stats_result is not None:
                return vital_stats_result

        if asks_about_dhss_mophims_profiles_lookup(question):
            mophims_result = self.dhss_mophims_profiles_index.answer(question)
            if mophims_result is not None:
                return mophims_result

        if asks_about_dhss_ltc_inspection_lookup(question):
            dhss_ltc_result = self.dhss_ltc_inspection_index.answer(question)
            if dhss_ltc_result is not None:
                return dhss_ltc_result

        if asks_about_hospital_profile_lookup(question):
            hospital_result = self.data_mo_hospital_index.answer(question)
            if hospital_result is not None:
                return hospital_result

        if asks_about_ltc_lookup(question):
            ltc_result = self.data_mo_ltc_index.answer(question)
            if ltc_result is not None:
                return ltc_result

        if asks_about_dhss_health_sources_lookup(question):
            health_sources_result = self.dhss_health_sources_index.answer(question)
            if health_sources_result is not None:
                return health_sources_result

        if asks_about_mec_annual_report_lookup(question):
            mec_annual_result = self.mec_annual_report_index.answer(question)
            if mec_annual_result is not None:
                return mec_annual_result

        if asks_about_mec_resources_lookup(question):
            mec_result = self.mec_resources_index.answer(question)
            if mec_result is not None:
                return mec_result

        if asks_about_health_lookup(question):
            health_result = self.data_mo_health_index.answer(question)
            if health_result is not None:
                return health_result

        if asks_about_dnr_water_lookup(question):
            water_result = self.data_mo_water_index.answer(question)
            if water_result is not None:
                return water_result

        if asks_about_dnr_oil_gas_lookup(question):
            oil_gas_result = self.data_mo_dnr_oil_gas_index.answer(question)
            if oil_gas_result is not None:
                return oil_gas_result

        if asks_about_dnr_hazardous_waste_lookup(question):
            hazardous_waste_result = self.data_mo_dnr_hazardous_waste_index.answer(question)
            if hazardous_waste_result is not None:
                return hazardous_waste_result

        if asks_about_dnr_impaired_waters_lookup(question):
            impaired_waters_result = self.dnr_impaired_waters_index.answer(question)
            if impaired_waters_result is not None:
                return impaired_waters_result

        if asks_about_dnr_resources_lookup(question):
            dnr_result = self.dnr_resources_index.answer(question)
            if dnr_result is not None:
                return dnr_result

        if asks_about_msdis_geospatial_lookup(question):
            msdis_result = self.msdis_geospatial_index.answer(question)
            if msdis_result is not None:
                return msdis_result

        if asks_about_modot_aadt_lookup(question):
            modot_result = self.modot_aadt_index.answer(question)
            if modot_result is not None:
                return modot_result

        if asks_about_utility_lookup(question):
            utility_result = self.data_mo_utility_index.answer(question)
            if utility_result is not None:
                return utility_result

        if asks_about_data_mo_catalog_lookup(question):
            data_mo_result = self.data_mo_catalog_index.answer(question)
            if data_mo_result is not None:
                return data_mo_result

        if asks_about_public_source_catalog(question):
            return self.public_source_catalog_answer(question)

        if asks_for_help(question):
            return self.help_answer(question)

        if asks_about_contract_lookup(question):
            return self.contract_answer(question)

        if asks_reversed_vendor_payment(question):
            return {
                "question": question,
                "answer": (
                    "The local MAP expenditure index tracks payments by Missouri state agencies to vendors. "
                    "It does not support vendor-to-agency payment direction. Try asking how much a state agency paid a vendor."
                ),
                "source": "unsupported_scope_guardrail",
                "used_model": False,
                "model": "unsupported_scope_guardrail",
                "suggestions": [
                    "How much did OFFICE OF ADMINISTRATION pay CAPITAL MALL JC 1 LLC in 2025?",
                    "Which agencies paid CAPITAL MALL JC 1 LLC in 2025?",
                ],
            }

        if asks_about_missouri_governor(question):
            return self.missouri_governor_answer(question)

        if asks_about_missouri_capital(question):
            return self.missouri_capital_answer(question)

        if asks_about_map_definition(question):
            return self.map_definition_answer(question)

        if asks_about_map_inventory(question):
            summary = self.map_index.summary()
            if summary:
                file_count = sum(item["file_count"] for item in summary.values())
                row_count = sum(item["row_count"] or 0 for item in summary.values())
                categories = ", ".join(sorted(summary))
                return {
                    "question": question,
                    "answer": (
                        f"The local MAP lookup index covers {file_count} text files across {len(summary)} categories "
                        f"with {row_count:,} parsed rows. Categories: {categories}. Two downloaded cumulative "
                        f"self-extracting files are kept as raw artifacts and not executed."
                    ),
                    "retrieved_context_id": "map_public_index:summary",
                    "retrieved_source": "map_public_lookup_index",
                    "retrieval_score": 1.0,
                    "used_model": False,
                    "model": "deterministic_public_lookup",
                    "source_note": "Computed from local MAP file_summary metadata.",
                }

        if asks_about_salary_scope(question):
            if asks_for_top_employee_pay(question):
                top_employee_result = self.top_employee_pay_answer(question)
                if top_employee_result is not None:
                    return top_employee_result
            employee_result = self.employee_answer(question)
            if employee_result is not None:
                return employee_result
            return self.missing_lookup_answer(
                question,
                "map_employee_public_lookup_index",
                "I can answer MAP employee pay questions when the public employee name and indexed year are identifiable. I could not identify a matching employee record.",
                self.map_index.employee_suggestions(question),
            )

        if asks_which_agency_paid_vendor(question):
            agency_result = self.top_agencies_for_vendor_answer(question)
            if agency_result is not None:
                return agency_result
            return self.missing_lookup_answer(
                question,
                "map_expenditure_agency_vendor_lookup_index",
                "I can answer which MAP agencies paid a named vendor when the vendor and year are identifiable in the local expenditure index.",
                self.map_index.amount_suggestions(question, ["expenditure_vendor"]),
            )

        if asks_about_expenditure_lookup(question):
            if asks_year_peak(question):
                peak_result = self.year_peak_amount_answer(question, ["expenditure_agency", "expenditure_category"], "expenditure")
                if peak_result is not None:
                    return peak_result
            if asks_for_top(question) and asks_about_vendor_lookup(question):
                top_vendor_result = self.top_vendors_for_agency_answer(question)
                if top_vendor_result is not None:
                    return top_vendor_result
            agency_vendor_result = self.agency_vendor_answer(question)
            if agency_vendor_result is not None:
                return agency_vendor_result
            if asks_about_vendor_lookup(question):
                vendor_result = self.public_amount_answer(question, ["expenditure_vendor", "stimulus_vendor"], "expenditure/vendor")
                if vendor_result is not None:
                    return vendor_result
                return self.missing_lookup_answer(
                    question,
                    "map_public_lookup_index",
                    "I can answer named MAP expenditure vendor totals when the vendor name appears in the local public MAP lookup index. I could not identify a matching vendor name.",
                    self.map_index.amount_suggestions(question, ["expenditure_vendor", "stimulus_vendor"]),
                )
            if asks_for_top(question):
                lowered = question.lower()
                kind = "expenditure_category" if "categor" in lowered else "expenditure_agency"
                top_result = self.top_amount_answer(question, kind, "expenditure totals")
                if top_result is not None:
                    return top_result
            public_result = self.public_amount_answer(
                question,
                ["expenditure_agency", "expenditure_category"],
                "expenditure",
            )
            if public_result is not None:
                return public_result
            return self.missing_lookup_answer(
                question,
                "map_public_lookup_index",
                "I can answer expenditure questions when the agency, category, vendor, and year are identifiable in the MAP expenditure files.",
                self.map_index.amount_suggestions(question, ["expenditure_agency", "expenditure_category", "expenditure_vendor"]),
            )

        if asks_about_vendor_lookup(question):
            if asks_for_top(question):
                top_result = self.top_vendors_for_agency_answer(question)
                if top_result is not None:
                    return top_result
                top_result = self.top_amount_answer(question, "expenditure_vendor", "vendors by expenditure total")
                if top_result is not None:
                    return top_result
            agency_vendor_result = self.agency_vendor_answer(question)
            if agency_vendor_result is not None:
                return agency_vendor_result
            public_result = self.public_amount_answer(question, ["expenditure_vendor", "stimulus_vendor"], "expenditure/vendor")
            if public_result is not None:
                return public_result
            return self.missing_lookup_answer(
                question,
                "map_public_lookup_index",
                "I can answer named MAP expenditure vendor totals when the vendor name appears in the local public MAP lookup index. I could not identify a matching vendor name.",
                self.map_index.amount_suggestions(question, ["expenditure_vendor", "stimulus_vendor"]),
            )

        if asks_about_tax_credit(question):
            if asks_for_top(question):
                top_result = self.top_amount_answer(question, "tax_credit_customer", "tax-credit customers by issued amount")
                if top_result is not None:
                    return top_result
            public_result = self.public_amount_answer(
                question,
                ["tax_credit_customer", "tax_credit_program", "tax_credit_category"],
                "tax credit",
            )
            if public_result is not None:
                return public_result
            return self.missing_lookup_answer(
                question,
                "map_public_lookup_index",
                "I can answer tax-credit questions when the customer, program, or category is identifiable in the MAP tax-credit files.",
                self.map_index.amount_suggestions(question, ["tax_credit_customer", "tax_credit_program", "tax_credit_category"]),
            )

        if asks_about_federal_grant(question):
            if asks_for_top(question):
                top_result = self.top_amount_answer(question, "federal_grant_agency", "state agencies by federal grant amount")
                if top_result is not None:
                    return top_result
            public_result = self.public_amount_answer(
                question,
                ["federal_grant_agency", "federal_grant_federal_agency"],
                "federal grant",
            )
            if public_result is not None:
                return public_result
            return self.missing_lookup_answer(
                question,
                "map_public_lookup_index",
                "I can answer federal-grant questions when the state agency or federal agency is identifiable in the MAP federal-grant files.",
                self.map_index.amount_suggestions(question, ["federal_grant_agency", "federal_grant_federal_agency"]),
            )

        if asks_about_budget_restriction(question):
            if asks_for_top(question):
                kind = "budget_released_agency" if "released" in question.lower() else "budget_restricted_agency"
                top_result = self.top_amount_answer(question, kind, "agencies by budget restriction amount")
                if top_result is not None:
                    return top_result
            kind = "budget_released_agency" if "released" in question.lower() else "budget_restricted_agency"
            public_result = self.public_amount_answer(question, [kind], "budget restriction")
            if public_result is not None:
                return public_result
            return self.missing_lookup_answer(
                question,
                "map_public_lookup_index",
                "I can answer budget-restriction questions when the agency and year are identifiable in the MAP budget restriction files.",
                self.map_index.amount_suggestions(question, [kind]),
            )

        if asks_about_bonds(question):
            if asks_for_top(question):
                kind = "bond_subdivision_outstanding" if "outstanding" in question.lower() else "bond_subdivision_face"
                top_result = self.top_amount_answer(question, kind, "political subdivisions by bond amount")
                if top_result is not None:
                    return top_result
            kind = "bond_subdivision_outstanding" if "outstanding" in question.lower() else "bond_subdivision_face"
            public_result = self.public_amount_answer(question, [kind], "bond")
            if public_result is not None:
                return public_result
            return self.missing_lookup_answer(
                question,
                "map_public_lookup_index",
                "I can answer bond questions when the political subdivision is identifiable in the MAP bond file.",
                self.map_index.amount_suggestions(question, [kind]),
            )

        if asks_generic_agency_ranking(question):
            top_result = self.top_amount_answer(question, "expenditure_agency", "expenditure totals")
            if top_result is not None:
                return top_result

        if asks_about_mshp_crash_lookup(question):
            crash_result = self.mshp_crash_index.answer(question)
            if crash_result is not None:
                return crash_result

        if asks_about_dor_report_lookup(question):
            dor_result = self.dor_reports_index.answer(question)
            if dor_result is not None:
                return dor_result

        if asks_about_meric_labor_lookup(question):
            meric_result = self.meric_labor_index.answer(question)
            if meric_result is not None:
                return meric_result

        if asks_about_auditor_lookup(question):
            auditor_result = self.state_auditor_index.answer(question)
            if auditor_result is not None:
                return auditor_result

        if asks_about_sos_elections_lookup(question):
            sos_result = self.sos_elections_index.answer(question)
            if sos_result is not None:
                return sos_result

        if self.dese_directory_index.can_answer(question):
            return self.dese_directory_index.answer(question)

        if asks_about_expanded_public_source(question):
            source_result = self.public_source_index.answer(question)
            if source_result is not None:
                return source_result

        retrieved = self.retrieve_context(question)
        retrieved_citations = self.retrieved_row_citations(retrieved)
        if retrieved["score"] < RETRIEVED_QA_MIN_SCORE or not retrieved_citations:
            general_result = self.general_chat_answer(question)
            if general_result is not None:
                return general_result
            return {
                "question": question,
                "answer": (
                    "I do not have enough indexed source support to answer that question reliably. "
                    "Try asking about MAP expenditures, employee pay, tax credits, federal grants, budget restrictions, "
                    "bonds, contracts, SOS election returns, cannabis dispensary/annual-report facts, hospital beds, "
                    "child-care dashboard facts, farmers-market directory listings, DHSS vital statistics, PSC report metadata or selected report-PDF snippets, OA Budget metadata, OA general-revenue detail values, agriculture market-report links, LTC census aggregates, or basic sourced Missouri civic facts."
                ),
                "source": "unsupported_or_low_retrieval_confidence",
                "retrieval_score": round(retrieved["score"], 4),
                "used_model": False,
                "model": "retrieval_guardrail",
                "suggestions": self.help_answer(question)["suggestions"],
            }
        return {
            "question": question,
            "answer": retrieved["answer"],
            "retrieved_context_id": retrieved["id"],
            "retrieved_source": retrieved["source"],
            "retrieval_score": round(retrieved["score"], 4),
            "used_model": False,
            "model": "retrieved_public_qa",
            "source_note": "Returned from the closest generated public-data QA row instead of free-form generation.",
            "citations": retrieved_citations,
        }

    def ask(self, question: str) -> dict[str, Any]:
        result = self.route_question(question)
        if self.should_synthesize_answer(result):
            return self.synthesize_answer(question, result)
        return result


def ask(
    question: str,
    model_id: str,
    adapter_path: Path,
    use_base: bool,
    max_new_tokens: int,
    synthesis_mode: str = "off",
    synthesis_max_new_tokens: int = 160,
) -> dict[str, Any]:
    engine = AskEngine(
        model_id=model_id,
        adapter_path=adapter_path,
        use_base=use_base,
        max_new_tokens=max_new_tokens,
        synthesis_mode=synthesis_mode,
        synthesis_max_new_tokens=synthesis_max_new_tokens,
    )
    return engine.ask(question)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("question")
    parser.add_argument("--model-id", default=DEFAULT_MODEL)
    parser.add_argument("--adapter-path", default=str(DEFAULT_ADAPTER.relative_to(PROJECT_ROOT)))
    parser.add_argument("--base", action="store_true")
    parser.add_argument("--max-new-tokens", type=int, default=48)
    parser.add_argument("--synthesis", choices=["off", "local"], default="off")
    parser.add_argument("--synthesis-max-new-tokens", type=int, default=160)
    args = parser.parse_args()

    if args.max_new_tokens < 1 or args.max_new_tokens > 96:
        raise SystemExit("--max-new-tokens must be between 1 and 96")
    if args.synthesis_max_new_tokens < 16 or args.synthesis_max_new_tokens > 256:
        raise SystemExit("--synthesis-max-new-tokens must be between 16 and 256")

    result = ask(
        question=args.question,
        model_id=args.model_id,
        adapter_path=PROJECT_ROOT / args.adapter_path,
        use_base=args.base,
        max_new_tokens=args.max_new_tokens,
        synthesis_mode=args.synthesis,
        synthesis_max_new_tokens=args.synthesis_max_new_tokens,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
