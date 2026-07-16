"""
ReqVue — Test 2: OpenRouter Extraction
----------------------------------------
Takes the Docling markdown output from Test 1 and sends
it to IBM Granite 4.1 via OpenRouter for raw field extraction.

Tests whether the model can find the 16 ReqVue fields
from a real government RFQ document.

Run from your ReqVue directory with .venv activated:
    python test_2_extraction.py

Requires:
    - .env file with OPENROUTER_API_KEY set
    - docling_*.md files from Test 1 in the same folder

Results saved to: test_2_results.txt
"""

import os
import json
import time
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

# ── Load environment ──────────────────────────────────────────
load_dotenv()
api_key = os.getenv("OPENROUTER_API_KEY")

if not api_key:
    print("❌ OPENROUTER_API_KEY not found in .env file")
    print("   Add this line to your .env file:")
    print("   OPENROUTER_API_KEY=your-key-here")
    exit(1)

# ── Config ────────────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).parent
MODEL        = "ibm-granite/granite-4.1-8b"
MAX_WORDS    = 4000       # Pre-processing trim limit
RISK_KEYWORDS = [         # Always extract paragraphs containing these
    "liquidated damages", "penalty", "late delivery",
    "FOB", "f.o.b", "revision", "rev.", "tolerance",
    "target price", "budget", "currently paying",
    "first article", "FAI", "NDT", "DFARS", "AS9100",
    "quote due", "bid due", "offers due", "closing date",
    "ASTM", "AMS", "MIL-", "MIL"
]

# ── OpenRouter client ─────────────────────────────────────────
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=api_key,
)

# ── Pre-processing: smart trim ────────────────────────────────
def smart_trim(markdown: str, max_words: int = MAX_WORDS) -> str:
    """
    Send the first max_words of the document plus any paragraphs
    containing risk keywords found anywhere in the full document.
    """
    words     = markdown.split()
    front     = " ".join(words[:max_words])
    paragraphs = markdown.split("\n\n")

    # Find risk keyword paragraphs from the full document
    risk_paras = []
    for para in paragraphs:
        para_lower = para.lower()
        for kw in RISK_KEYWORDS:
            if kw.lower() in para_lower:
                if para not in front:
                    risk_paras.append(f"[RISK SECTION — {kw.upper()}]\n{para}")
                break

    result = front
    if risk_paras:
        result += "\n\n--- RISK KEYWORD SECTIONS ---\n\n"
        result += "\n\n".join(risk_paras[:10])  # cap at 10 risk sections

    return result

# ── Extraction prompt ─────────────────────────────────────────
SYSTEM_PROMPT = """You are ReqVue, an expert manufacturing estimator's assistant.
Your job is to read RFQ and solicitation documents and extract key information
into a structured JSON object.

Extract ONLY what is explicitly stated in the document.
If a field is not found, set its value to null.
If a field is ambiguous or unclear, set it to the exact text found with a note.
Never guess or infer values that aren't clearly stated.

Return ONLY valid JSON. No explanation, no markdown, no preamble.
"""

USER_PROMPT_TEMPLATE = """Extract the following fields from this RFQ document and return as JSON:

{{
  "rfq_id_and_org": "Solicitation number, customer/agency name, and primary contact",
  "quote_due_date": "When the quote/bid paperwork is due back",
  "delivery_deadline": "When physical parts or goods must be delivered. May be expressed as 'X DAYS ADO' (Days After Date of Order). Include the exact string if present.",
  "part_number_rev": "Part number AND revision level if stated",
  "material_and_grade": "Exact material alloy and specification (e.g. Al 7075-T6, ASTM A36)",
  "dimensions_raw": "All stated dimensions — thickness, width, length, OD, etc.",
  "tolerances_stated": "All tolerance requirements. FLAG anything tighter than +/-0.001 inch",
  "finishing_secondary": "Any coating, plating, heat treatment, painting, or finishing requirements",
  "qty_tiers": "All requested quantities — return as array if multiple tiers",
  "incoterms_fob": "FOB Destination or FOB Shipping Point — exact terms stated",
  "target_price": "Any historical pricing, budget ceiling, or target price mentioned",
  "legal_penalties": "ANY liquidated damages, late fees, penalty clauses — FLAG as HIGH PRIORITY if found",
  "qa_certs_required": "Material certs, FAI, CoC, NDT, AS9100, ISO, DFARS compliance requirements",
  "competing_vendors": "Any mention of other vendors being solicited or bid count",
  "missing_or_unclear": "List specific information gaps the estimator needs to resolve",
  "estimator_summary": "One paragraph: job description + top risk factor + recommended next action"
}}

Note: All dates should be normalized to ISO 8601 format (YYYY-MM-DD). If a delivery deadline is given as 'X DAYS ADO', include that exact string.

RFQ DOCUMENT:
{document}
"""

# ── Find markdown files from Test 1 ──────────────────────────
def find_markdown_files() -> list[Path]:
    files = list(SCRIPT_DIR.glob("docling_*.md"))
    return sorted(files)

# ── Run extraction on one document ───────────────────────────
def extract_fields(markdown_path: Path) -> dict:
    print(f"\n  Reading: {markdown_path.name}")

    with open(markdown_path, "r") as f:
        raw_markdown = f.read()

    # Smart trim
    trimmed  = smart_trim(raw_markdown)
    word_count_full    = len(raw_markdown.split())
    word_count_trimmed = len(trimmed.split())
    print(f"  Document: {word_count_full:,} words → trimmed to {word_count_trimmed:,} words")

    # Build prompt
    user_prompt = USER_PROMPT_TEMPLATE.format(document=trimmed)

    # Call OpenRouter
    print(f"  Calling {MODEL}...")
    start = time.time()

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_prompt}
            ],
            temperature=0.0,    # deterministic extraction
            max_tokens=2000,
        )
        elapsed = round(time.time() - start, 2)

        raw_response = response.choices[0].message.content.strip()

        # Clean JSON — strip markdown fences if model added them
        if raw_response.startswith("```"):
            lines = raw_response.split("\n")
            raw_response = "\n".join(
                l for l in lines
                if not l.startswith("```")
            )

        # Parse JSON
        extracted = json.loads(raw_response)

        # Count populated fields
        populated = sum(
            1 for v in extracted.values()
            if v is not None and v != "" and v != []
        )

        print(f"  ✅ Extracted {populated}/16 fields in {elapsed}s")

        return {
            "status":    "✅ PASSED",
            "file":      markdown_path.name,
            "elapsed":   elapsed,
            "populated": populated,
            "extracted": extracted,
            "raw":       raw_response
        }

    except json.JSONDecodeError as e:
        elapsed = round(time.time() - start, 2)
        print(f"  ⚠️  JSON parse error: {e}")
        print(f"  Raw response preview: {raw_response[:300]}")
        return {
            "status":  "⚠️  JSON PARSE ERROR",
            "file":    markdown_path.name,
            "elapsed": elapsed,
            "error":   str(e),
            "raw":     raw_response[:500]
        }

    except Exception as e:
        elapsed = round(time.time() - start, 2)
        print(f"  ❌ ERROR: {e}")
        return {
            "status":  f"❌ ERROR — {e}",
            "file":    markdown_path.name,
            "elapsed": elapsed,
            "error":   str(e)
        }

# ── Main ──────────────────────────────────────────────────────
def run_test():
    print("\n" + "="*60)
    print("ReqVue — Test 2: OpenRouter Extraction")
    print(f"Model: {MODEL}")
    print("="*60)

    md_files = find_markdown_files()

    if not md_files:
        print("\n❌ No docling_*.md files found.")
        print("   Run test_1_docling.py first to generate them.")
        return

    print(f"\nFound {len(md_files)} document(s) to test:")
    for f in md_files:
        print(f"  • {f.name}")

    results = []
    for md_file in md_files:
        print(f"\n{'─'*50}")
        result = extract_fields(md_file)
        results.append(result)

        # Print field-by-field preview for passed extractions
        if "extracted" in result:
            print("\n  Field preview:")
            for field, value in result["extracted"].items():
                if value and value != [] and value != "null":
                    display = str(value)[:80]
                    if len(str(value)) > 80:
                        display += "..."
                    print(f"    {field:<25} {display}")
                else:
                    print(f"    {field:<25} [not found]")

    # ── Write results file ────────────────────────────────────
    output_path = SCRIPT_DIR / "test_2_results.txt"
    with open(output_path, "w") as f:
        f.write("ReqVue — Test 2 Results: OpenRouter Extraction\n")
        f.write(f"Model: {MODEL}\n")
        f.write("="*60 + "\n\n")

        for r in results:
            f.write(f"FILE:      {r['file']}\n")
            f.write(f"STATUS:    {r['status']}\n")
            f.write(f"TIME:      {r.get('elapsed', 0)}s\n")
            f.write(f"POPULATED: {r.get('populated', 0)}/16 fields\n\n")

            if "extracted" in r:
                f.write("EXTRACTED FIELDS:\n")
                for field, value in r["extracted"].items():
                    f.write(f"  {field}: {value}\n")
            elif "error" in r:
                f.write(f"ERROR: {r['error']}\n")
                f.write(f"RAW RESPONSE:\n{r.get('raw','')}\n")

            f.write("\n" + "-"*60 + "\n\n")

    # ── Summary ───────────────────────────────────────────────
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    passed = sum(1 for r in results if "PASSED" in r.get("status",""))
    warned = sum(1 for r in results if "WARNING" in r.get("status","") or "PARSE" in r.get("status",""))
    failed = sum(1 for r in results if "ERROR"  in r.get("status",""))

    print(f"  ✅ Passed:   {passed}/{len(results)}")
    print(f"  ⚠️  Warnings: {warned}/{len(results)}")
    print(f"  ❌ Failed:   {failed}/{len(results)}")

    if passed > 0:
        avg_fields = sum(
            r.get("populated", 0) for r in results
            if "PASSED" in r.get("status","")
        ) / max(passed, 1)
        print(f"  📊 Avg fields populated: {avg_fields:.1f}/16")

    print(f"\n  Results saved to: test_2_results.txt")
    print("\nNext: If fields look accurate, move to Test 3 (Instructor + Pydantic validation)")
    print("="*60 + "\n")

if __name__ == "__main__":
    run_test()