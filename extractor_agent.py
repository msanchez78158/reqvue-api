"""
extractor_agent.py — Agno-powered RFQ extraction agent.

Replaces the single LLM call in extractor.py with a two-pass reasoning agent:
  Pass 1: Classify document type and identify key sections
  Pass 2: Extract all fields with confidence scoring and clarification questions

Returns RFQBriefV2 — backward compatible with RFQBrief, adds confidence,
document_type, clarification_questions, and ready_to_quote.
"""

import json
import os

from dotenv import load_dotenv

load_dotenv()

from agno.agent import Agent
from agno.models.openrouter import OpenRouter

from models import RFQBriefV2

MODEL = os.getenv("EXTRACTION_MODEL", "deepseek/deepseek-v4-flash")

CLASSIFIER_INSTRUCTIONS = """
You are a procurement document classifier.

Given the text of a document, determine:
1. document_type: one of "manufacturing_rfq", "services_rfq", "insurance_rfq", "government_rfq", "other"
2. key_sections: a brief description of what sections are present and where critical data lives

Return ONLY a JSON object. No markdown fences. No preamble.

Example:
{
  "document_type": "manufacturing_rfq",
  "key_sections": "Header contains RFQ ID and due date. Page 2 has part number and material spec. Page 3 has qty breaks and FOB terms. Page 4 has legal penalties clause."
}
"""

EXTRACTOR_INSTRUCTIONS = """
You are an expert RFQ/RFP extraction assistant for a manufacturing estimator.

You will receive:
- document_type: what kind of document this is
- key_sections: a description of where critical data lives in the document
- document_text: the full document text

Your job:
1. Extract only facts directly supported by the document. Do not guess or invent.
2. For each field, if the information is present and clear, extract it precisely.
3. If a field is not applicable for this document type, return null.
4. If a field should be present but is missing or ambiguous, note it in missing_or_unclear.
5. Generate specific clarification_questions an estimator must answer before quoting.
6. Score confidence_score from 0.0 to 1.0 based on how complete and unambiguous the extraction is.
7. Set ready_to_quote to true only if all critical fields for this document type are present and clear.

Critical fields for manufacturing_rfq: part_number_rev, material_and_grade, dimensions_raw, quote_due_date
Critical fields for services_rfq or government_rfq: rfq_id_and_org, quote_due_date, qa_certs_required
Critical fields for insurance_rfq: rfq_id_and_org, quote_due_date, qa_certs_required

Return ONLY a valid JSON object with exactly these fields. No markdown fences. No preamble.

Fields:
- rfq_id_and_org (string or null)
- quote_due_date (string or null)
- delivery_deadline (string or null)
- part_number_rev (string or null)
- material_and_grade (string or null)
- dimensions_raw (string or null)
- tolerances_stated (string or null)
- finishing_secondary (string or null)
- qty_tiers (array of numbers or null)
- incoterms_fob (string or null)
- target_price (string or null)
- legal_penalties (string or null)
- qa_certs_required (string or null)
- competing_vendors (string or null)
- missing_or_unclear (string or null)
- estimator_summary (string or null)
- document_type (string)
- confidence_score (float 0.0-1.0)
- clarification_questions (array of strings)
- ready_to_quote (boolean)
"""


def _build_classifier() -> Agent:
    return Agent(
        name="RFQ Classifier",
        model=OpenRouter(id=MODEL),
        instructions=CLASSIFIER_INSTRUCTIONS,
        markdown=False,
    )


def _build_extractor() -> Agent:
    return Agent(
        name="RFQ Extractor",
        model=OpenRouter(id=MODEL),
        instructions=EXTRACTOR_INSTRUCTIONS,
        markdown=False,
    )


def _strip_fences(raw: str) -> str:
    if raw.strip().startswith("```"):
        lines = raw.strip().split("\n")
        raw = "\n".join(line for line in lines if not line.startswith("```"))
    return raw.strip()


def _run_agent(agent: Agent, prompt: str) -> str:
    """Run agent and return the text content of the response."""
    response = agent.run(prompt)
    if hasattr(response, "content") and isinstance(response.content, list):
        for block in response.content:
            if hasattr(block, "text"):
                return block.text
    if hasattr(response, "content") and isinstance(response.content, str):
        return response.content
    return str(response)


def extract_rfq_brief_v2(document_name: str, document_text: str) -> RFQBriefV2:
    """
    Two-pass Agno agent extraction.

    Pass 1 — Classifier: determines document type and identifies key sections.
    Pass 2 — Extractor: uses classification context to extract all fields accurately.
    """

    # Pass 1: classify
    classifier = _build_classifier()
    classifier_prompt = f"Classify this document and identify its key sections.\n\nDocument name: {document_name}\n\nDocument text:\n{document_text}"

    raw_classification = _run_agent(classifier, classifier_prompt)
    classification = json.loads(_strip_fences(raw_classification))

    document_type = classification.get("document_type", "unknown")
    key_sections = classification.get("key_sections", "No section analysis available.")

    # Pass 2: extract with classification context
    extractor = _build_extractor()
    extractor_prompt = (
        f"document_type: {document_type}\n"
        f"key_sections: {key_sections}\n\n"
        f"Document name: {document_name}\n\n"
        f"Document text:\n{document_text}"
    )

    raw_extraction = _run_agent(extractor, extractor_prompt)
    parsed = json.loads(_strip_fences(raw_extraction))

    # Normalize list fields that models sometimes return as strings
    list_fields = ["clarification_questions"]
    for field in list_fields:
        if isinstance(parsed.get(field), str):
            parsed[field] = [parsed[field]]

    str_fields = [
        "rfq_id_and_org", "quote_due_date", "delivery_deadline", "part_number_rev",
        "material_and_grade", "dimensions_raw", "tolerances_stated", "finishing_secondary",
        "incoterms_fob", "target_price", "legal_penalties", "qa_certs_required",
        "competing_vendors", "missing_or_unclear", "estimator_summary",
    ]
    for field in str_fields:
        if isinstance(parsed.get(field), list):
            parsed[field] = "; ".join(str(item) for item in parsed[field])

    return RFQBriefV2.model_validate(parsed)
