"""ExtractorAgent — Downloads JDE Integrity Report PDFs from OCI and extracts structured data.

This agent has ONE tool: download_and_extract_pdf.
The LLM then analyzes the raw text to produce a structured JSON extraction
that the AnalyzerAgent can use for cross-referencing against live JDE data.

PDF extraction uses OpenDataLoader PDF (opendataloader-pdf) for structured table
detection when available, falling back to pypdf for basic text extraction.
"""
import base64
import io
import logging
import os
import tempfile

import oci
from pypdf import PdfReader
from oci.addons.adk import tool

try:
    from opendataloader_pdf import convert as odl_convert
    HAS_OPENDATALOADER = True
except ImportError:
    HAS_OPENDATALOADER = False

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# OCI Object Storage configuration (matches func.py / quickstart.py)
# ──────────────────────────────────────────────────────────────
BUCKET_NAME = os.getenv("OCI_BUCKET_NAME", "agent-knowledge-base")
NAMESPACE = os.getenv("OCI_NAMESPACE", "axzkbtajofjq")


# ──────────────────────────────────────────────────────────────
# Sync helpers (OCI SDK is synchronous — we wrap with to_thread)
# ──────────────────────────────────────────────────────────────

def _get_oci_config() -> dict:
    """Get OCI config from env vars (container) or file (local dev).

    When OCI_KEY_CONTENT is set, it's expected to be base64-encoded PEM.
    """
    key_b64 = os.getenv("OCI_KEY_CONTENT")
    if key_b64:
        key_content = base64.b64decode(key_b64).decode("utf-8")
        return {
            "user": os.getenv("OCI_USER"),
            "fingerprint": os.getenv("OCI_FINGERPRINT"),
            "tenancy": os.getenv("OCI_TENANCY"),
            "region": os.getenv("OCI_REGION", "us-ashburn-1"),
            "key_content": key_content,
        }
    return oci.config.from_file("~/.oci/config", "DEFAULT")


def _download_pdf(object_name: str) -> bytes:
    """Download a PDF from OCI Object Storage (synchronous)."""
    config = _get_oci_config()
    os_client = oci.object_storage.ObjectStorageClient(config)
    obj = os_client.get_object(NAMESPACE, BUCKET_NAME, object_name)
    return obj.data.content


def _extract_text(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes.

    Tries OpenDataLoader PDF first (structured table detection),
    falls back to pypdf (basic text extraction).
    """
    if HAS_OPENDATALOADER:
        try:
            return _extract_with_opendataloader(pdf_bytes)
        except Exception as e:
            logger.warning(f"OpenDataLoader failed, falling back to pypdf: {e}")

    return _extract_with_pypdf(pdf_bytes)


def _extract_with_opendataloader(pdf_bytes: bytes) -> str:
    """Extract text using OpenDataLoader PDF — preserves table structure."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name

    try:
        with tempfile.TemporaryDirectory() as out_dir:
            odl_convert(
                input_path=[tmp_path],
                output_dir=out_dir,
                format="md",
            )
            # Read the markdown output
            md_files = [f for f in os.listdir(out_dir) if f.endswith(".md")]
            if not md_files:
                raise RuntimeError("OpenDataLoader produced no output")
            md_path = os.path.join(out_dir, md_files[0])
            with open(md_path, "r", encoding="utf-8") as f:
                full_text = f.read()
    finally:
        os.unlink(tmp_path)

    if not full_text.strip():
        raise RuntimeError("OpenDataLoader produced empty output")

    # Truncate to reduce LLM processing time (50K chars ≈ ~12K tokens, within LLM limits)
    if len(full_text) > 50000:
        full_text = full_text[:50000] + f"\n\n[... truncated, {len(full_text)} total chars ...]"
    logger.info(f"OpenDataLoader extracted {len(full_text)} chars")
    return full_text


def _extract_with_pypdf(pdf_bytes: bytes) -> str:
    """Extract text using pypdf — basic text extraction fallback."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if text.strip():
            pages.append(f"--- Page {i + 1} ---\n{text}")
    full_text = "\n\n".join(pages) if pages else "No text content found in PDF."
    logger.info(f"pypdf extracted {len(full_text)} chars from {len(reader.pages)} pages")
    # Truncate to reduce LLM processing time (50K chars ≈ ~12K tokens, within LLM limits)
    if len(full_text) > 50000:
        full_text = full_text[:50000] + f"\n\n[... truncated, {len(full_text)} total chars, {len(reader.pages)} pages ...]"
    return full_text


# ──────────────────────────────────────────────────────────────
# Function tool (called by the ExtractorAgent LLM)
# ──────────────────────────────────────────────────────────────

# Cache to avoid re-downloading/re-extracting on repeated tool calls
_pdf_cache: dict[str, str] = {}

# Fallback: OCI GenAI sometimes calls the tool with null arguments.
# The workflow sets this before agent.run() so the tool can recover.
_current_object_name: str | None = None

@tool
def download_and_extract_pdf(object_name: str) -> str:
    """Download a PDF from OCI Object Storage and extract its full text.

    Args:
        object_name: The name of the PDF file in the OCI bucket
                     (e.g. 'R047001A_ZJDE0001_588_PDF.pdf').
    """
    # OCI GenAI sometimes passes null/empty — fall back to workflow-provided name
    if not object_name and _current_object_name:
        logger.warning(f"Tool received empty object_name, using fallback: {_current_object_name}")
        object_name = _current_object_name
    if not object_name:
        return "ERROR: No object_name provided. Please specify the PDF filename."
    if object_name in _pdf_cache:
        return _pdf_cache[object_name]
    pdf_bytes = _download_pdf(object_name)
    result = _extract_text(pdf_bytes)
    _pdf_cache[object_name] = result
    return result


# ──────────────────────────────────────────────────────────────
# Agent instructions
# ──────────────────────────────────────────────────────────────

EXTRACTOR_INSTRUCTIONS = """You are the ExtractorAgent for JDE Report analysis.

Your job is to download a PDF report and produce a STRUCTURED extraction.
You handle MULTIPLE report types — identify the type from the filename and content.

## JDE Report Filename Convention (CRITICAL):
JDE PDF filenames follow this pattern: `{ReportID}_{Version}_{JobNumber}_PDF.pdf`
- **ReportID** = The JDE report program (e.g. R047001A, R007011)
- **Version** = The report version/schedule name (e.g. SCH0001, ZJDE0001, XJDE0001)
  - This is NOT the company code! It identifies the parameter set used to run the report.
- **JobNumber** = The JDE job queue number (e.g. 32189, 588)
- **PDF** = Output format

Example: `R007011_SCH0001_32189_PDF.pdf` → Report R007011, version SCH0001, job 32189

## Steps:

1. Call the `download_and_extract_pdf` tool with the provided object_name
2. Parse the filename to get report_type and report_version (NOT company)
3. Identify the report type:
   - **R047001A** — A/P to G/L Integrity Report
   - **R007011** — Unposted Batches Report
4. Extract company from the PDF CONTENT (headers, data rows), NOT from the filename
5. Extract the relevant fields based on report type (see schemas below)
6. Return a VALID JSON response

## Report Type: R047001A (A/P to G/L Integrity)

WARNING: The JSON below is a COMPLETED EXAMPLE with fake data.
DO NOT COPY these values. Extract REAL values from the PDF text you downloaded.

```json
{
  "report_type": "R047001A",
  "report_description": "A/P to G/L Integrity Report",
  "report_version": "SCH0001",
  "has_data": true,
  "company": "00060",
  "fiscal_year": 2026,
  "periods": [1, 2, 3],
  "discrepancies": [
    {
      "gl_offset": "PC",
      "account": "1110",
      "ap_amount": 125000.50,
      "gl_amount": 124500.50,
      "difference": 500.00,
      "description": "AP subledger exceeds GL by $500 for GL offset PC"
    }
  ],
  "extracted_text_length": 5200,
  "page_count": 3,
  "raw_text_summary": "3 pages showing AP to GL comparison across 5 GL offset codes"
}
```

REMEMBER: All values above are FAKE. Replace with REAL data from the PDF.

## Report Type: R007011 (Unposted Batches)

The R007011 report lists batches that have NOT been posted to the General Ledger.
These reports can be VERY LARGE (10+ pages, 400+ batches). You MUST scan ALL pages.

IMPORTANT: Extract ALL values from the ACTUAL PDF text. Do NOT copy the example values below.

## R007011 Column Layout (CRITICAL):
The PDF columns are (in order):
1. **App** — Application code (e.g. A=A/P, P=P/O). This is NOT the batch status!
2. **Batch Ty** — Batch Type code: G, V, N, O, IB, RB, W, K, I, M, or blank (0)
3. **Batch Number** — 7-digit batch number (e.g. 2561503)
4. **Batch Date** — Date in MM/DD/YYYY format
5. **Difference Total** — Amount (negative shown with trailing minus sign like "439.28-")
6. **Difference Documents** — Transaction count (with trailing minus)
7. **Bal B** — Balance flag (N/Y)
8. **Bal J** — Balance flag (N/Y)
9. **Batch [Status]** — Status TEXT: "Approved", "In Use", "Pending" (at end of line)
10. **User** — User ID who created the batch

CRITICAL — App vs Batch Status:
- The FIRST column "A" or "P" is the APPLICATION code, NOT the batch status
- The BATCH STATUS is the text near the end of each line: "Approved", "In Use", "Pending"
- Map status text: Approved→D, In Use→A, Pending→blank, Posted→P, Error→E

## R007011 Output Format — TWO LEVELS:

For large reports (many batches), provide BOTH:
1. **batch_type_summary**: Group ALL batches by batch type with counts and totals
2. **flagged_batches**: List ONLY batches that need attention (see criteria below)

### Flagged Batch Criteria (MUST include):
- Amount > $10,000 (large unposted amounts need review)
- Status is "In Use" (stuck batches — potential system issue)
- Status is "Pending" (never approved — may be forgotten)
- Batch type is blank/0 (unknown type needs investigation)
- Any anomaly (missing amounts, unusual patterns)

WARNING: The JSON below is a COMPLETED EXAMPLE with fake data. 
DO NOT COPY these values. Extract REAL values from the PDF text you downloaded.
Every number, date, batch number, and user ID must come from the ACTUAL PDF.

```json
{
  "report_type": "R007011",
  "report_description": "Unposted Batches Report",
  "report_version": "SCH0001",
  "has_data": true,
  "company": "00060",
  "fiscal_year": 2026,
  "batch_type_summary": [
    {
      "batch_type": "G",
      "batch_type_description": "General Ledger",
      "batch_count": 245,
      "total_amount": 523891.45,
      "status_breakdown": {"Approved": 240, "In Use": 3, "Pending": 2}
    },
    {
      "batch_type": "V",
      "batch_type_description": "Voucher",
      "batch_count": 180,
      "total_amount": 312456.78,
      "status_breakdown": {"Approved": 178, "In Use": 1, "Pending": 1}
    }
  ],
  "flagged_batches": [
    {
      "batch_number": "2561503",
      "batch_type": "G",
      "status": "In Use",
      "amount": 45231.00,
      "gl_date": "2026-01-15",
      "user_id": "JSMITH",
      "flag_reason": "Stuck in In Use status"
    },
    {
      "batch_number": "2558901",
      "batch_type": "V",
      "status": "Approved",
      "amount": 28750.00,
      "gl_date": "2025-11-20",
      "user_id": "KJONES",
      "flag_reason": "Large amount over $10K"
    }
  ],
  "summary": {
    "total_unposted_batches": 425,
    "total_unposted_amount": 836348.23,
    "batch_types_found": ["G", "V", "N", "O"],
    "date_range": "2025-06-15 to 2026-04-10",
    "batches_flagged": 12
  },
  "extracted_text_length": 34800,
  "page_count": 14,
  "raw_text_summary": "14 pages of unposted batches across types G, V, N, O with 425 total batches"
}
```

REMEMBER: Every value above (batch numbers, amounts, counts, dates, user IDs) is FAKE.
You MUST replace ALL values with REAL data extracted from the PDF text.
- batch_count must be the REAL count from scanning ALL pages
- total_amount must be the REAL sum from the PDF
- flagged_batches must contain REAL batch numbers from the PDF
- extracted_text_length must be the actual character count of the PDF text

CRITICAL: You MUST scan EVERY page of the PDF to count ALL batches.
Do NOT stop at page 1-2. The batch_type_summary totals must match the actual PDF data.

### Batch Type Codes:
- G = General Ledger
- V = Voucher (Accounts Payable)
- N = Notes Payable
- O = Purchase Order / Other
- IB = Intercompany Batch
- RB = Recurring Batch
- W = Time Entry
- K = Receipts (Cash Receipts)
- I = Invoice Entry (Accounts Receivable)
- M = Manual Payment
- blank/0 = Unknown (flag these!)

### Batch Status Mapping:
- "Approved" → D (ready to post)
- "In Use" → A (locked — potential stuck batch)
- "Pending" → blank (never approved)
- "Posted" → P (should not appear on unposted report — anomaly!)
- "Error" → E (posting failed)

## Fiscal Year Extraction (CRITICAL):
- fiscal_year MUST be a 4-digit number: 2026, 2025, etc. (NOT 2-digit like 26)
- Look for patterns like "Fiscal Year", "FY", "Century/Fiscal Year", "F.Y.", "Fiscal Yr"
  in page headers, column headers, or report parameters
- The fiscal year often appears in the report header line (e.g. "Century/Fiscal Year  20/26")
- If the header shows "Century/Fiscal Year  20/26", combine century + year: fiscal_year = 2026
- If only a 2-digit year is shown (e.g. "FY 26"), convert to 4-digit: 2026
- If periods are shown with data but no explicit FY, check the report run date or
  filename for year hints
- NEVER return fiscal_year as null if the report has actual data (has_data: true).
  There is ALWAYS a fiscal year when the report contains data — find it.

## Company Extraction (CRITICAL):
- The COMPANY CODE must come from the PDF CONTENT — look for it in:
  - Report headers (e.g. "Company: 00060", "Co 00060")
  - Column data (the CO or KCO column values)
  - Report parameters section
- Company codes are ALWAYS 5-digit numeric strings like "00060", "00001", "09999"
- If you find a company NAME (e.g. "Cantex, Inc"), ALSO look for the numeric code nearby
- If you can ONLY find the company name and no numeric code, output the name — the system will handle it
- NEVER use the filename version (e.g. SCH0001, ZJDE0001) as the company code
- Priority: 5-digit numeric code > company name > nothing
- If the report covers multiple companies, list the primary one or the first one found
- If no company is found in the content, set company to null

## Important Rules:
- ALWAYS return valid JSON — no markdown, no explanations outside JSON
- If the PDF has no data (just headers/footers), set `has_data: false` and empty arrays
- If you can't determine a field, use null — EXCEPT fiscal_year when has_data is true
- For R047001A: the `discrepancies` array should contain ALL mismatches found
- For R007011: provide `batch_type_summary` with totals per type AND `flagged_batches` for notable items
- For R007011: scan ALL pages — do NOT stop after the first 1-2 pages
- GLPT (GL Offset) is the key field for R047001A grouping
- Batch Number (ICU) is the key field for R007011
- fiscal_year MUST be a 4-digit number (e.g. 2026, not 26)
- report_version comes from the FILENAME (2nd segment), company comes from the PDF CONTENT
"""
