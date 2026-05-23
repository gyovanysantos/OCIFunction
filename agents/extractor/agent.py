"""ExtractorAgent — Downloads JDE Integrity Report PDFs from OCI and extracts structured data.

This agent has ONE tool: download_and_extract_pdf.
The LLM then analyzes the raw text to produce a structured JSON extraction
that the AnalyzerAgent can use for cross-referencing against live JDE data.

PDF extraction uses opendataloader-pdf (AI-backed table detection) with a
pypdf fallback for environments where opendataloader-pdf is unavailable.
"""
import asyncio
import base64
import io
import logging
import os
import tempfile

import oci
from agent_framework import tool

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Optional: opendataloader-pdf (preferred) / pypdf (fallback)
# ──────────────────────────────────────────────────────────────

try:
    import opendataloader_pdf
    _HAS_OPENDATALOADER = True
    logger.info("PDF extractor: opendataloader-pdf")
except ImportError:
    _HAS_OPENDATALOADER = False
    logger.info("PDF extractor: pypdf (opendataloader-pdf not installed)")

try:
    from pypdf import PdfReader
    _HAS_PYPDF = True
except ImportError:
    _HAS_PYPDF = False

# ──────────────────────────────────────────────────────────────
# OCI Object Storage configuration
# ──────────────────────────────────────────────────────────────

BUCKET_NAME = os.getenv("OCI_BUCKET_NAME", "OBJECTSTORAGE")
NAMESPACE = os.getenv("OCI_NAMESPACE", "idxoqn0ijjyv")
LOCAL_PDF_DIR = os.getenv("LOCAL_PDF_DIR", "")


# ──────────────────────────────────────────────────────────────
# Sync helpers (OCI SDK is synchronous)
# ──────────────────────────────────────────────────────────────

def _get_oci_config() -> dict:
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
    return oci.config.from_file("~/.oci/config", "cantex")


def _download_pdf(object_name: str) -> bytes:
    """Download PDF from OCI, or read from LOCAL_PDF_DIR if set."""
    if LOCAL_PDF_DIR:
        local_path = os.path.join(LOCAL_PDF_DIR, object_name)
        if os.path.exists(local_path):
            logger.info(f"Using local PDF: {local_path}")
            with open(local_path, "rb") as f:
                return f.read()

    config = _get_oci_config()
    os_client = oci.object_storage.ObjectStorageClient(config)
    obj = os_client.get_object(NAMESPACE, BUCKET_NAME, object_name)
    return obj.data.content


def _extract_with_opendataloader(pdf_bytes: bytes) -> str:
    """Extract text and tables using opendataloader-pdf (AI-backed)."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name

    try:
        with tempfile.TemporaryDirectory() as out_dir:
            opendataloader_pdf.convert(
                input_path=[tmp_path],
                output_dir=out_dir,
                format="markdown",
            )
            base = os.path.splitext(os.path.basename(tmp_path))[0]
            md_path = os.path.join(out_dir, base + ".md")
            if os.path.exists(md_path):
                content = open(md_path, encoding="utf-8").read().strip()
                return content if content else "No text content found in PDF."
            return "No text content found in PDF."
    finally:
        os.unlink(tmp_path)


def _extract_with_pypdf(pdf_bytes: bytes) -> str:
    """Extract text using pypdf (basic, no table structure)."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if text.strip():
            pages.append(f"--- Page {i + 1} ---\n{text}")
    return "\n\n".join(pages) if pages else "No text content found in PDF."


def _extract_text(pdf_bytes: bytes) -> str:
    """Extract text from PDF, preferring opendataloader-pdf."""
    if _HAS_OPENDATALOADER:
        try:
            return _extract_with_opendataloader(pdf_bytes)
        except Exception as exc:
            logger.warning(f"opendataloader-pdf failed, falling back to pypdf: {exc}")
    if _HAS_PYPDF:
        return _extract_with_pypdf(pdf_bytes)
    raise RuntimeError("No PDF extraction library available (install opendataloader-pdf or pypdf)")


# ──────────────────────────────────────────────────────────────
# Function tool (called by the ExtractorAgent LLM)
# ──────────────────────────────────────────────────────────────

@tool
async def download_and_extract_pdf(object_name: str) -> str:
    """Download a PDF from OCI Object Storage and extract its full text and tables.

    Args:
        object_name: The name of the PDF file in the OCI bucket
                     (e.g. 'R047001A_ZJDE0001_588_PDF.pdf').

    Returns:
        Extracted text and table content from all pages of the PDF.
    """
    pdf_bytes = await asyncio.to_thread(_download_pdf, object_name)
    return _extract_text(pdf_bytes)


# ──────────────────────────────────────────────────────────────
# Agent instructions
# ──────────────────────────────────────────────────────────────

EXTRACTOR_INSTRUCTIONS = """You are the ExtractorAgent for JDE Integrity Report analysis.

Your job is to download a PDF report and produce a STRUCTURED extraction.

## Steps:

1. Call the `download_and_extract_pdf` tool with the provided object_name
2. Analyze the extracted text to identify:
   - Report type (e.g. R047001A = A/P to G/L Integrity)
   - Company code(s) mentioned in the report
   - Fiscal year and accounting periods covered
   - Whether the report has actual data (not just headers/footers)
   - Discrepancies or out-of-balance items listed
   - Account numbers (object accounts, subsidiaries)
   - GL offset codes (GLPT) if mentioned
   - Dollar amounts associated with mismatches

3. Return a VALID JSON response with exactly this schema:

```json
{
  "report_type": "R047001A",
  "report_description": "A/P to G/L Integrity Report",
  "has_data": true,
  "company": "00060",
  "fiscal_year": 25,
  "periods": [1, 2, 3],
  "discrepancies": [
    {
      "gl_offset": "PA",
      "account": "1110",
      "ap_amount": 123456.78,
      "gl_amount": 123400.00,
      "difference": 56.78,
      "description": "AP Trade offset out of balance by $56.78"
    }
  ],
  "extracted_text_length": 5000,
  "page_count": 3,
  "raw_text_summary": "Brief summary of the report content"
}
```

## Important Rules:
- ALWAYS return valid JSON — no markdown, no explanations outside JSON
- If the PDF has no data (just headers/footers), set `has_data: false` and empty arrays
- If you can't determine a field, use null
- The `discrepancies` array should contain ALL mismatches found in the report
- GLPT (GL Offset) is the key field that groups AP vouchers by GL posting code
"""
