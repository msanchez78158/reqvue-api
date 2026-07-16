import json
import os

from openai import APITimeoutError, OpenAI
from pydantic import ValidationError

from models import RFQBrief

MODEL = "deepseek/deepseek-v4-flash"
OPENROUTER_TIMEOUT_SECONDS = float(os.getenv("OPENROUTER_TIMEOUT_SECONDS", "90"))

SYSTEM_PROMPT = """
You are an expert RFQ/RFP extraction assistant for a manufacturing estimator.

Your job is to extract only facts that are directly supported by the provided document text.
Do not guess. Do not invent missing information. If a field is not present, unclear, or not applicable, return null.

Pay special attention to:
- quote due dates
- delivery deadlines
- part numbers and revisions
- materials and grades
- dimensions and tolerances
- finishing or secondary operations
- quantity price breaks
- FOB/incoterms
- target price
- legal penalties, liquidated damages, late fees, or penalty clauses
- QA and certification requirements
- competing vendors or incumbent vendors
- missing information that an estimator must clarify

Be conservative and precise.
"""


def build_user_prompt(document_name: str, document_text: str) -> str:
    """
    Same user prompt template from Test 2, with the required qty_tiers wording change.
    """

    return f"""
Extract an RFQ brief from the following document.

Document name:
{document_name}

Return ONLY a valid JSON object with exactly the following fields. No markdown
fences, no tables, no preamble, no commentary — the response must start with {{
and end with }}. Use null for any field not supported by the document.

rfq_id_and_org:
RFQ identifier, solicitation number, buyer, issuing organization, or customer.

quote_due_date:
Date and time quote is due.

delivery_deadline:
Required delivery date, lead time, period of performance, or delivery schedule.

part_number_rev:
Part number, drawing number, revision, NSN, SKU, or item identifier.

material_and_grade:
Material specification, alloy, grade, temper, or material standard.

dimensions_raw:
Raw stated dimensions, sizes, units, drawing dimensions, or dimensional requirements.

tolerances_stated:
Any stated tolerances, precision requirements, or drawing tolerance references.

finishing_secondary:
Finishing, coating, plating, heat treat, deburring, marking, packaging, or other secondary operations.

qty_tiers:
Pricing break quantities only — array of quantity numbers where price changes. Do not include contract minimums, annual estimates, or order counts.

incoterms_fob:
FOB terms, incoterms, shipping terms, destination/origin requirements, or freight responsibility.

target_price:
Target price, budgetary price, should-cost, ceiling price, or pricing guidance.

legal_penalties:
Any liquidated damages, late fees, penalty clauses, default clauses, or consequences for late/nonconforming delivery.

qa_certs_required:
Quality assurance, inspection, certification, C of C, ISO, AS9100, ITAR, DFARS, FAR, or compliance requirements.

competing_vendors:
Named competitors, incumbent vendors, approved sources, required sources, or vendor limitations.

missing_or_unclear:
Important missing, ambiguous, conflicting, or unclear information an estimator should clarify.

estimator_summary:
Brief plain-English summary for an estimator deciding whether to quote.

Document text:
{document_text}
"""


def _get_client() -> OpenAI:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY not found. Add it to your .env file.")

    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )


def _strip_markdown_fences(raw: str) -> str:
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(line for line in lines if not line.startswith("```"))
    return raw.strip()


def extract_rfq_brief(document_name: str, document_text: str) -> RFQBrief:
    client = _get_client()
    user_prompt = build_user_prompt(document_name, document_text)

    for attempt in range(2):
        try:
            try:
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.0,
                    # deepseek-v4-flash is a reasoning model: hidden reasoning tokens
                    # count toward this cap alongside the visible JSON (~600 tokens).
                    # 2000 truncated responses mid-string once richer trimmed content
                    # made reasoning longer.
                    max_tokens=6000,
                    timeout=OPENROUTER_TIMEOUT_SECONDS,
                )
            except APITimeoutError as exc:
                raise RuntimeError(
                    f"OpenRouter request timed out after {OPENROUTER_TIMEOUT_SECONDS} seconds"
                ) from exc

            raw = _strip_markdown_fences(response.choices[0].message.content or "")
            parsed = json.loads(raw)

            if "properties" in parsed and isinstance(parsed["properties"], dict):
                parsed = parsed["properties"]

            valid_fields = set(RFQBrief.model_fields.keys())
            parsed = {key: value for key, value in parsed.items() if key in valid_fields}

            for field_name in (
                "rfq_id_and_org",
                "quote_due_date",
                "delivery_deadline",
                "part_number_rev",
                "material_and_grade",
                "dimensions_raw",
                "tolerances_stated",
                "finishing_secondary",
                "incoterms_fob",
                "target_price",
                "legal_penalties",
                "qa_certs_required",
                "competing_vendors",
                "missing_or_unclear",
                "estimator_summary",
            ):
                if isinstance(parsed.get(field_name), list):
                    parsed[field_name] = "; ".join(str(item) for item in parsed[field_name])

            return RFQBrief.model_validate(parsed)
        except (json.JSONDecodeError, ValidationError):
            if attempt == 0:
                continue
            raise
