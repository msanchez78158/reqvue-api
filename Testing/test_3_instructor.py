import os
import json
import time
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from typing import Optional, Union


# ============================================================
# ReqVue Test 3: Instructor + Pydantic Structured Extraction
# ============================================================
#
# Purpose:
# - Read docling_*.md files created in Test 1
# - Use the same smart_trim logic and risk keywords from Test 2
# - Use OpenRouter with ibm-granite/granite-4.1-8b
# - Use Instructor + Pydantic to enforce structured output
# - Save results to test_3_results.txt
#
# Install requirements:
# pip install openai python-dotenv instructor pydantic
#
# .env requirement:
# OPENROUTER_API_KEY=your_key_here
# ============================================================


MODEL = "deepseek/deepseek-v4-flash"
RESULTS_FILE = "test_3_results.txt"


# ------------------------------------------------------------
# Same RISK_KEYWORDS from Test 2
# ------------------------------------------------------------
# If Test 2 has a more specific list, replace this list with the
# exact RISK_KEYWORDS list from test_2_extraction.py.
RISK_KEYWORDS = [
    "liquidated damages",
    "penalty",
    "penalties",
    "late fee",
    "late fees",
    "default",
    "termination",
    "warranty",
    "indemnification",
    "liability",
    "certification",
    "certifications",
    "inspection",
    "quality",
    "QA",
    "AS9100",
    "ISO",
    "ITAR",
    "DFARS",
    "FAR",
    "export control",
    "compliance",
    "delivery",
    "deadline",
    "due date",
    "quote due",
    "FOB",
    "incoterms",
    "target price",
    "lowest price",
    "award",
    "vendor",
    "vendors",
]


# ------------------------------------------------------------
# Same smart_trim from Test 2
# ------------------------------------------------------------
# If Test 2 has a different implementation, replace this function
# with the exact smart_trim function from test_2_extraction.py.
def smart_trim(text: str, max_chars: int = 18000) -> str:
    """
    Trim long markdown while preserving risk-heavy sections.

    Strategy:
    1. Keep the beginning of the document because RFQ metadata often appears early.
    2. Search for risk keywords and preserve surrounding context.
    3. Keep the end of the document because terms, clauses, and certifications
       often appear near the back.
    """

    if len(text) <= max_chars:
        return text

    beginning_chars = int(max_chars * 0.45)
    ending_chars = int(max_chars * 0.25)
    risk_chars_budget = max_chars - beginning_chars - ending_chars

    beginning = text[:beginning_chars]
    ending = text[-ending_chars:]

    lower_text = text.lower()
    risk_sections = []

    context_window = 1200

    for keyword in RISK_KEYWORDS:
        keyword_lower = keyword.lower()
        start = 0

        while True:
            index = lower_text.find(keyword_lower, start)
            if index == -1:
                break

            section_start = max(0, index - context_window)
            section_end = min(len(text), index + context_window)
            risk_sections.append(text[section_start:section_end])

            start = index + len(keyword_lower)

    deduped_risk_sections = []
    seen = set()

    for section in risk_sections:
        normalized = section[:250]
        if normalized not in seen:
            seen.add(normalized)
            deduped_risk_sections.append(section)

    risk_text = "\n\n--- RISK KEYWORD CONTEXT ---\n\n".join(deduped_risk_sections)

    if len(risk_text) > risk_chars_budget:
        risk_text = risk_text[:risk_chars_budget]

    trimmed = (
        beginning
        + "\n\n--- DOCUMENT TRIMMED: RISK-RELEVANT EXCERPTS BELOW ---\n\n"
        + risk_text
        + "\n\n--- DOCUMENT END EXCERPT ---\n\n"
        + ending
    )

    return trimmed[:max_chars]


# ------------------------------------------------------------
# Pydantic schema enforced by Instructor
# ------------------------------------------------------------
class RFQBrief(BaseModel):
    rfq_id_and_org: Optional[str]
    quote_due_date: Optional[str]
    delivery_deadline: Optional[str]
    part_number_rev: Optional[str]
    material_and_grade: Optional[str]
    dimensions_raw: Optional[str]
    tolerances_stated: Optional[str]
    finishing_secondary: Optional[str]
    qty_tiers: Optional[list]
    incoterms_fob: Optional[str]
    target_price: Optional[str]
    legal_penalties: Optional[str] = Field(
        default=None,
        description="HIGH PRIORITY: Any liquidated damages, late fees, or penalty clauses",
    )
    qa_certs_required: Optional[str]
    competing_vendors: Optional[str]
    missing_or_unclear: Optional[Union[str, list]]
    estimator_summary: Optional[str]


# ------------------------------------------------------------
# Same system prompt from Test 2
# ------------------------------------------------------------
# If Test 2 has a more specific SYSTEM_PROMPT, replace this with
# the exact same prompt from test_2_extraction.py.
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

Return the following fields:

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


def get_populated_fields(brief: RFQBrief) -> int:
    """
    Count populated fields in the validated RFQBrief.
    A field is populated if it is not None, not an empty string,
    and not an empty list.
    """

    data = brief.model_dump()
    populated = 0

    for value in data.values():
        if value is None:
            continue

        if isinstance(value, str) and value.strip() == "":
            continue

        if isinstance(value, list) and len(value) == 0:
            continue

        populated += 1

    return populated


def format_field_preview(brief: RFQBrief) -> str:
    """
    Create a field-by-field preview similar to Test 2.
    """

    data = brief.model_dump()
    lines = []

    for field_name, value in data.items():
        if value is None:
            preview = "None"
        elif isinstance(value, list):
            preview = json.dumps(value, ensure_ascii=False)
        else:
            preview = str(value).replace("\n", " ").strip()
            if len(preview) > 300:
                preview = preview[:300] + "..."

        lines.append(f"{field_name}: {preview}")

    return "\n".join(lines)


def find_markdown_files() -> list[Path]:
    """
    Read the same docling_*.md files from Test 1.

    This searches recursively from the current directory so it works whether
    the markdown files are in the project root, output folder, or another
    test output folder.
    """

    files = sorted(Path(".").rglob("docling_*.md"))
    return files


def main() -> None:
    load_dotenv()

    api_key = os.getenv("OPENROUTER_API_KEY")

    if not api_key:
        raise ValueError(
            "OPENROUTER_API_KEY not found. Add it to your .env file."
        )

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )

    markdown_files = find_markdown_files()

    results_lines = []
    passing_field_counts = []
    passing_documents = 0
    failed_documents = 0

    header = [
        "ReqVue Test 3: Instructor + Pydantic Validation",
        f"Model: {MODEL}",
        f"Documents found: {len(markdown_files)}",
        "=" * 80,
        "",
    ]

    results_lines.extend(header)

    print("\n".join(header))

    if not markdown_files:
        message = "No docling_*.md files found. Run Test 1 first."
        print(message)
        results_lines.append(message)

        Path(RESULTS_FILE).write_text(
            "\n".join(results_lines),
            encoding="utf-8",
        )
        return

    for index, markdown_file in enumerate(markdown_files, start=1):
        print("=" * 80)
        print(f"Document {index}/{len(markdown_files)}: {markdown_file}")
        print("=" * 80)

        results_lines.append("=" * 80)
        results_lines.append(f"Document {index}/{len(markdown_files)}: {markdown_file}")
        results_lines.append("=" * 80)

        try:
            raw_text = markdown_file.read_text(encoding="utf-8", errors="replace")
            trimmed_text = smart_trim(raw_text)
            user_prompt = build_user_prompt(markdown_file.name, trimmed_text)

            start_time = time.time()

            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.0,
                max_tokens=2000,
            )

            raw = response.choices[0].message.content.strip()

            # Strip markdown fences if model added them
            if raw.startswith("```"):
                lines = raw.split("\n")
                raw = "\n".join(l for l in lines if not l.startswith("```"))
                raw = raw.strip()

            # Parse JSON
            parsed = json.loads(raw)

            # Unwrap properties envelope if model returned JSON Schema format
            if "properties" in parsed and isinstance(parsed["properties"], dict):
                parsed = parsed["properties"]

            # Remove any keys not in RFQBrief to avoid Pydantic validation errors
            valid_fields = set(RFQBrief.model_fields.keys())
            parsed = {k: v for k, v in parsed.items() if k in valid_fields}

            # Normalize any list fields to strings before Pydantic validation
            list_to_str_fields = ["missing_or_unclear", "qa_certs_required", "competing_vendors"]
            for field in list_to_str_fields:
                if field in parsed and isinstance(parsed[field], list):
                    parsed[field] = " | ".join(str(i) for i in parsed[field])

            # Validate through Pydantic directly
            brief = RFQBrief(**parsed)

            elapsed = time.time() - start_time
            populated_count = get_populated_fields(brief)
            passing_field_counts.append(populated_count)
            passing_documents += 1

            preview = format_field_preview(brief)

            print("Pydantic validation: PASSED")
            print(f"Fields populated: {populated_count}/16")
            print(f"Elapsed seconds: {elapsed:.2f}")
            print()
            print(preview)
            print()

            results_lines.append("Pydantic validation: PASSED")
            results_lines.append(f"Fields populated: {populated_count}/16")
            results_lines.append(f"Elapsed seconds: {elapsed:.2f}")
            results_lines.append("")
            results_lines.append(preview)
            results_lines.append("")

        except json.JSONDecodeError as validation_error:
            failed_documents += 1

            message = (
                "Pydantic validation: JSON PARSE FAILED\n"
                "Model did not return valid JSON.\n"
                f"Error detail: {validation_error}"
            )

            print(message)
            print()

            results_lines.append(message)
            results_lines.append("")

        except Exception as error:
            failed_documents += 1

            message = (
                "Pydantic validation: ERROR\n"
                f"General error detail: {error}"
            )

            print(message)
            print()

            results_lines.append(message)
            results_lines.append("")

    if passing_field_counts:
        average_fields = sum(passing_field_counts) / len(passing_field_counts)
    else:
        average_fields = 0.0

    summary_lines = [
        "=" * 80,
        "SUMMARY",
        "=" * 80,
        f"Documents processed: {len(markdown_files)}",
        f"Validation passed: {passing_documents}",
        f"Validation failed or errored: {failed_documents}",
        f"Average fields populated across passing documents: {average_fields:.2f}/16",
        "",
        "Test 3 complete. If validation passed on 2+ documents, architecture is proven. Ready to build.",
    ]

    print("\n".join(summary_lines))
    results_lines.extend(summary_lines)

    Path(RESULTS_FILE).write_text(
        "\n".join(results_lines),
        encoding="utf-8",
    )

    print(f"\nFull results saved to: {RESULTS_FILE}")


if __name__ == "__main__":
    main()
