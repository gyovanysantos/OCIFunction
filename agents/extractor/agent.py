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
BUCKET_NAME = os.getenv("OCI_BUCKET_NAME", "OBJECTSTORAGE")
NAMESPACE = os.getenv("OCI_NAMESPACE", "idxoqn0ijjyv")
LOCAL_PDF_DIR = os.getenv("LOCAL_PDF_DIR", "")


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
    """Download a PDF — from local dir if LOCAL_PDF_DIR is set and file exists, else OCI."""
    if LOCAL_PDF_DIR:
        local_path = os.path.join(LOCAL_PDF_DIR, os.path.basename(object_name))
        if os.path.isfile(local_path):
            with open(local_path, "rb") as f:
                return f.read()
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

    # Truncate to reduce LLM processing time
    if len(full_text) > 8000:
        full_text = full_text[:8000] + f"\n\n[... truncated, {len(full_text)} total chars ...]"
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
    # Truncate to reduce LLM processing time (keep first 6000 chars)
    if len(full_text) > 6000:
        full_text = full_text[:6000] + f"\n\n[... truncated, {len(full_text)} total chars, {len(reader.pages)} pages ...]"
    return full_text


# ──────────────────────────────────────────────────────────────
# Function tool (called by the ExtractorAgent LLM)
# ──────────────────────────────────────────────────────────────

# Cache to avoid re-downloading/re-extracting on repeated tool calls
_pdf_cache: dict[str, str] = {}

@tool
def download_and_extract_pdf(object_name: str) -> str:
    """Download a PDF from OCI Object Storage and extract its full text.

    Args:
        object_name: The name of the PDF file in the OCI bucket
                     (e.g. 'R047001A_ZJDE0001_588_PDF.pdf').
    """
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

IMPORTANT: Extract ALL values from the ACTUAL PDF text. Do NOT copy example values below.

```json
{
  "report_type": "R047001A",
  "report_description": "A/P to G/L Integrity Report",
  "report_version": "<from filename>",
  "has_data": true,
  "company": "<from PDF content, NOT filename>",
  "fiscal_year": 2026,
  "periods": [1, 2, 3],
  "discrepancies": [
    {
      "gl_offset": "<extract from PDF>",
      "account": "<extract from PDF>",
      "ap_amount": 0.00,
      "gl_amount": 0.00,
      "difference": 0.00,
      "description": "<describe the discrepancy from PDF data>"
    }
  ],
  "extracted_text_length": 0,
  "page_count": 0,
  "raw_text_summary": "Brief summary of what the report shows"
}
```

## Report Type: R007011 (Unposted Batches)

The R007011 report lists batches that have NOT been posted to the General Ledger.
Look for batch numbers, batch types, statuses, amounts, dates, and user IDs.

IMPORTANT: Extract ALL values from the ACTUAL PDF text. Do NOT copy the example values below.
The example uses placeholder values (NNNNNNN, XXXXX) — replace them with real data.

CRITICAL — BATCH TYPE vs STATUS (these are DIFFERENT columns):
- **batch_type** = The ICUT column. Describes WHAT the batch contains.
  Valid values: G (General Ledger), V (Voucher), W (Time Entry), K (Receipts), I (Invoice), M (Manual Payment)
  In the PDF, this column is usually labeled "Batch Type", "Ty", or "BT".
- **status** = The batch lifecycle state. Describes WHERE the batch is in processing.
  Valid values: blank/Pending, D (Approved), P (Posted), E (Error), A (In-Use)
  In the PDF, this column is usually labeled "Batch Status", "St", or "Status".
- "A" is a STATUS code (In-Use), NEVER a batch type.
- "D" is a STATUS code (Approved), NEVER a batch type.
- If you can only find one of the two, look at the column header to determine which it is.

```json
{
  "report_type": "R007011",
  "report_description": "Unposted Batches Report",
  "report_version": "<from filename>",
  "has_data": true,
  "company": "<5-digit numeric code from PDF, e.g. 00060>",
  "fiscal_year": 2026,
  "periods": [1, 2, 3],
  "unposted_batches": [
    {
      "batch_number": "NNNNNNN (extract real batch number from PDF)",
      "batch_type": "G (must be one of: G, V, W, K, I, M — NOT a status code)",
      "batch_type_description": "General Ledger, Voucher, Time Entry, Receipts, Invoice, or Manual Payment",
      "status": "D (must be one of: blank, D, P, E, A — the batch lifecycle state)",
      "status_description": "Pending, Approved, Posted, Error, or In-Use",
      "amount": 0.00,
      "transaction_count": 0,
      "gl_date": "YYYY-MM-DD",
      "user_id": "XXXXX (extract real user ID from PDF)",
      "program_id": "PXXXX"
    }
  ],
  "summary": {
    "total_unposted_batches": 0,
    "total_unposted_amount": 0.00,
    "batch_types_found": [],
    "date_range": "start to end"
  },
  "extracted_text_length": 0,
  "page_count": 0,
  "raw_text_summary": "Brief summary of what the report shows"
}
```

CRITICAL: Every value in unposted_batches MUST come from the actual PDF text.
Parse each line of the report to extract: batch number, type, status, amount, date, user.
```

### Batch Type Codes:
- G = General Ledger
- V = Voucher (Accounts Payable)
- W = Time Entry
- K = Receipts (Cash Receipts)
- I = Invoice Entry (Accounts Receivable)
- M = Manual Payment
- O = Other

### Batch Status Codes:
- blank = Pending
- D = Approved
- P = Posted
- E = Error
- A = In-Use

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
- For R007011: the `unposted_batches` array should contain ALL unposted batches found
- GLPT (GL Offset) is the key field for R047001A grouping
- Batch Number (ICU) is the key field for R007011
- fiscal_year MUST be a 4-digit number (e.g. 2026, not 26)
- report_version comes from the FILENAME (2nd segment), company comes from the PDF CONTENT
"""
