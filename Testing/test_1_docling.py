"""
ReqVue — Test 1: Docling Document Parser
-----------------------------------------
Automatically finds and tests ALL PDF, DOCX, and XLSX files
in the same folder as this script.

Run from your ReqVue directory with .venv activated:
    python test_1_docling.py

Results saved to: test_1_results.txt
"""

from docling.document_converter import DocumentConverter
from pathlib import Path
from docling.datamodel.pipeline_options import PipelineOptions, AcceleratorOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat
import time

# Force the execution loop onto the CPU to handle the float64 limitation
accelerator_options = AcceleratorOptions(device="cpu")
pipeline_options = PipelineOptions(accelerator_options=accelerator_options)

converter = DocumentConverter(
    format_options={
        InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
    }
)

# Now pass your RFQ document through the converter safely
# res = converter.convert("test_rfq.pdf")

# ── Auto-find documents ───────────────────────────────────────
# Looks in the same folder as this script
SCRIPT_DIR = Path(__file__).parent
SUPPORTED_EXTENSIONS = [".pdf", ".docx", ".xlsx", ".xls", ".doc"]

def find_documents(folder: Path) -> list[Path]:
    found = []
    for ext in SUPPORTED_EXTENSIONS:
        found.extend(folder.glob(f"*{ext}"))
        found.extend(folder.glob(f"*{ext.upper()}"))
    return sorted(set(found))

# ── Run Tests ─────────────────────────────────────────────────
def test_docling():
    converter = DocumentConverter()
    results = []

    print("\n" + "="*60)
    print("ReqVue — Test 1: Docling Parser")
    print("="*60)
    print(f"Scanning folder: {SCRIPT_DIR}")

    # Find all documents
    documents = find_documents(SCRIPT_DIR)

    if not documents:
        print("\n❌ No supported files found in this folder.")
        print("Drop your PDF, DOCX, or XLSX files into:")
        print(f"  {SCRIPT_DIR}")
        print("Then run this script again.")
        return

    print(f"Found {len(documents)} file(s) to test:\n")
    for doc in documents:
        print(f"  • {doc.name}")

    print()

    for filepath in documents:
        print(f"\nProcessing: {filepath.name}")
        print("-" * 40)

        try:
            start = time.time()
            result = converter.convert(str(filepath))
            elapsed = round(time.time() - start, 2)

            # Export to markdown
            markdown = result.document.export_to_markdown()

            # Basic stats
            word_count = len(markdown.split())
            line_count = len(markdown.splitlines())
            tables_found = markdown.count("|---")

            # Preview — first 300 chars
            preview = markdown[:300].replace("\n", " ").strip()

            # Determine status
            if word_count > 100:
                status = "✅ PASSED"
            elif word_count > 10:
                status = "⚠️  LOW OUTPUT — may be scanned or image-based"
            else:
                status = "❌ FAILED — no text extracted"

            print(f"  Status:          {status}")
            print(f"  Words extracted: {word_count:,}")
            print(f"  Lines:           {line_count:,}")
            print(f"  Tables detected: {tables_found}")
            print(f"  Process time:    {elapsed}s")
            print(f"  Preview:         {preview[:200]}...")

            # Save full markdown output per file
            safe_name = filepath.stem.replace("%", "").replace("+", "_")[:30]
            md_path = SCRIPT_DIR / f"docling_{safe_name}.md"
            with open(md_path, "w") as mdf:
                mdf.write(f"# Docling Output: {filepath.name}\n\n")
                mdf.write(markdown)
            print(f"  Markdown saved:  {md_path.name}")

            results.append({
                "file": filepath.name,
                "status": status,
                "word_count": word_count,
                "line_count": line_count,
                "tables_found": tables_found,
                "preview": preview,
                "md_file": md_path.name,
                "time_seconds": elapsed
            })

        except Exception as e:
            print(f"  ❌ ERROR — {str(e)}")
            results.append({
                "file": filepath.name,
                "status": f"❌ ERROR — {str(e)}",
                "word_count": 0,
                "tables_found": 0,
                "preview": "",
                "time_seconds": 0
            })

    # ── Write summary results file ────────────────────────────
    output_path = SCRIPT_DIR / "test_1_results.txt"
    with open(output_path, "w") as f:
        f.write("ReqVue — Test 1 Results: Docling Parser\n")
        f.write("="*60 + "\n\n")
        f.write(f"Folder scanned: {SCRIPT_DIR}\n")
        f.write(f"Files tested: {len(results)}\n\n")

        for r in results:
            f.write(f"FILE:    {r['file']}\n")
            f.write(f"STATUS:  {r['status']}\n")
            f.write(f"WORDS:   {r.get('word_count', 0):,}\n")
            f.write(f"TABLES:  {r.get('tables_found', 0)}\n")
            f.write(f"TIME:    {r.get('time_seconds', 0)}s\n")
            f.write(f"PREVIEW: {r.get('preview', '')[:300]}\n")
            if r.get("md_file"):
                f.write(f"OUTPUT:  {r['md_file']}\n")
            f.write("\n" + "-"*60 + "\n\n")

    # ── Final summary ─────────────────────────────────────────
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    passed  = sum(1 for r in results if "PASSED" in r.get("status", ""))
    warning = sum(1 for r in results if "LOW"    in r.get("status", ""))
    failed  = sum(1 for r in results if "ERROR"  in r.get("status", "") or "FAILED" in r.get("status",""))

    print(f"  ✅ Passed:   {passed}/{len(results)}")
    print(f"  ⚠️  Warnings: {warning}/{len(results)}")
    print(f"  ❌ Failed:   {failed}/{len(results)}")
    print(f"\n  Results saved to: test_1_results.txt")
    print(f"  Markdown files:   docling_*.md")
    print("\nNext: Review the .md files to see exactly what Claude will receive.")
    print("="*60 + "\n")

if __name__ == "__main__":
    test_docling()