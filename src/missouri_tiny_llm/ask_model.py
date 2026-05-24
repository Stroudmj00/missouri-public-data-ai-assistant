"""Ask the fine-tuned model with sanitized retrieved context."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from missouri_tiny_llm.contract_documents import ContractDocumentIndex
from missouri_tiny_llm.contract_lookup import ContractIndex
from missouri_tiny_llm.data_mo_catalog_index import DataMoCatalogIndex
from missouri_tiny_llm.data_mo_education_index import DataMoEducationIndex
from missouri_tiny_llm.data_mo_health_index import DataMoHealthIndex
from missouri_tiny_llm.data_mo_utility_index import DataMoUtilityIndex
from missouri_tiny_llm.data_mo_water_index import DataMoWaterIndex
from missouri_tiny_llm.dor_reports_index import DorReportsIndex
from missouri_tiny_llm.expanded_public_sources import PublicSourceIndex
from missouri_tiny_llm.map_public_index import MapPublicIndex, years_in_question
from missouri_tiny_llm.meric_labor_index import MericLaborIndex
from missouri_tiny_llm.mshp_crash_index import MshpCrashIndex
from missouri_tiny_llm.public_source_catalog import PUBLIC_SOURCE_CATALOG, catalog_by_status


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL = "HuggingFaceTB/SmolLM2-135M-Instruct"
DEFAULT_ADAPTER = PROJECT_ROOT / "checkpoints" / "smollm2_135m_lora_run_002"
MAP_EXPENDITURE_FILE = PROJECT_ROOT / "data" / "raw_public" / "MAP_EXP_2026.txt"
RETRIEVED_QA_MIN_SCORE = 0.42
LOCAL_SOURCE_FILES = {
    "hospital_profile": PROJECT_ROOT / "data" / "raw_public" / "data_mo_hospital_profile.json",
    "ltc_census": PROJECT_ROOT / "data" / "raw_public" / "data_mo_ltc_census.json",
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
DNR_WATER_LOOKUP_PATTERNS = [
    r"\bconsumer\s+confidence\s+report\b",
    r"\bpublic\s+drinking\s+water\b",
    r"\bdrinking\s+water\s+systems?\b",
    r"\b(?:public\s+)?water\s+systems?\b",
    r"\bwater\s+systems?\b.*\b(indexed|lookup|count|pwsid)\b",
    r"\bpwsid\b",
    r"\bdnr\b.*\bwater\b.*\b(indexed|lookup|count|systems?)\b",
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
    return any(re.search(pattern, lowered) for pattern in EDUCATION_LOOKUP_PATTERNS)


def asks_about_health_lookup(question: str) -> bool:
    lowered = question.lower()
    if "dhss" in lowered and any(term in lowered for term in ["connected", "source", "sources", "available"]):
        return False
    return any(re.search(pattern, lowered) for pattern in HEALTH_LOOKUP_PATTERNS)


def asks_about_dnr_water_lookup(question: str) -> bool:
    lowered = question.lower()
    if any(term in lowered for term in ["connected", "source", "sources", "available"]) and not any(
        term in lowered for term in ["indexed", "exact", "lookup", "pwsid", "count", "how many"]
    ):
        return False
    return any(re.search(pattern, lowered) for pattern in DNR_WATER_LOOKUP_PATTERNS)


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


def asks_about_expanded_public_source(question: str) -> bool:
    lowered = question.lower()
    return any(re.search(pattern, lowered) for pattern in EXPANDED_SOURCE_PATTERNS)


def asks_about_mshp_crash_lookup(question: str) -> bool:
    lowered = question.lower()
    if any(word in lowered for word in ["connected", "source", "sources", "catalog", "available"]):
        return False
    if not years_in_question(question):
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
    ]
    return any(term in lowered for term in crash_terms)


def asks_about_dor_report_lookup(question: str) -> bool:
    lowered = question.lower()
    if any(word in lowered for word in ["connected", "source", "sources", "catalog", "available"]):
        return bool(re.search(r"\b(dor|department of revenue|revenue)\b", lowered))
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
    return any(re.search(pattern, lowered) for pattern in MISSOURI_GOVERNOR_PATTERNS)


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
        self.data_mo_catalog_index = DataMoCatalogIndex()
        self.data_mo_education_index = DataMoEducationIndex()
        self.data_mo_health_index = DataMoHealthIndex()
        self.data_mo_utility_index = DataMoUtilityIndex()
        self.data_mo_water_index = DataMoWaterIndex()
        self.public_source_index = PublicSourceIndex()
        self.mshp_crash_index = MshpCrashIndex()
        self.dor_reports_index = DorReportsIndex()
        self.meric_labor_index = MericLaborIndex()

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
            "data_mo_health_lookup_index",
            "data_mo_utility_lookup_index",
            "data_mo_water_lookup_index",
            "missouri_public_source_catalog",
            "missouri_public_source_index",
            "map_employee_public_lookup_index",
            "mshp_crash_lookup_index",
            "dor_reports_lookup_index",
            "meric_labor_lookup_index",
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
            "answer": (
                "The governor of Missouri is Mike Kehoe. The fact snapshot used by this case study was verified "
                "from the official Missouri Governor site on 2026-05-23; that source says Mike Kehoe was sworn "
                "in as Missouri's 58th Governor on January 13, 2025."
            ),
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

    def contract_citations(self, contract: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        source_files = [
            {
                "category": "contracts",
                "category_label": "MissouriBUYS Contract Board",
                "file_name": "https://missouribuys.mo.gov/contractboard",
                "row_count": None,
                "bytes": None,
                "sha256": None,
            },
            {
                "category": "contracts",
                "category_label": "Office of Administration Contract Search",
                "file_name": "https://archive.oa.mo.gov/purch/contracts/",
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

    def contract_answer(self, question: str) -> dict[str, Any]:
        summary = self.contract_index.summary()
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
            "Who is the governor of Missouri?",
            "Find contract CC221256001 and show its document links.",
        ]
        return {
            "question": question,
            "answer": (
                "I can answer source-backed questions over the local Missouri public-data index. "
                f"Indexed MAP categories: {category_text}. I can also answer the case-study hospital profile "
                "and LTC aggregate questions, selected data.mo.gov education questions, a small set of sourced Missouri civic facts, "
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
                    "education count, hospital aggregate, or LTC aggregate."
                ),
                "source": "unsupported_scope_guardrail",
                "used_model": False,
                "model": "unsupported_scope_guardrail",
                "suggestions": self.help_answer(question)["suggestions"],
            }

        if asks_about_data_mo_catalog_lookup(question):
            data_mo_result = self.data_mo_catalog_index.answer(question)
            if data_mo_result is not None:
                return data_mo_result

        if asks_about_education_lookup(question):
            education_result = self.data_mo_education_index.answer(question)
            if education_result is not None:
                return education_result

        if asks_about_health_lookup(question):
            health_result = self.data_mo_health_index.answer(question)
            if health_result is not None:
                return health_result

        if asks_about_dnr_water_lookup(question):
            water_result = self.data_mo_water_index.answer(question)
            if water_result is not None:
                return water_result

        if asks_about_utility_lookup(question):
            utility_result = self.data_mo_utility_index.answer(question)
            if utility_result is not None:
                return utility_result

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

        if asks_about_expanded_public_source(question):
            source_result = self.public_source_index.answer(question)
            if source_result is not None:
                return source_result

        retrieved = self.retrieve_context(question)
        retrieved_citations = self.retrieved_row_citations(retrieved)
        if retrieved["score"] < RETRIEVED_QA_MIN_SCORE or not retrieved_citations:
            return {
                "question": question,
                "answer": (
                    "I do not have enough indexed source support to answer that question reliably. "
                    "Try asking about MAP expenditures, employee pay, tax credits, federal grants, budget restrictions, "
                    "bonds, contracts, hospital beds, LTC census aggregates, or basic sourced Missouri civic facts."
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
