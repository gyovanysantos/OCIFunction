"""JDE Orchestration API — FastAPI wrapper for v2.0 multi-agent workflow.

Exposes the same API contract as v1.0 func.py so JDE Orchestration can call
this endpoint and get back {checkerResponse, analysisResponse}.

Under the hood it runs:
  1. ExtractorAgent — downloads PDF from OCI, extracts structured data
  2. AnalyzerAgent  — cross-references findings against live JDE via MCP

Endpoints:
  POST /v1/analyze  — main analysis endpoint
  GET  /health      — health check

Usage:
  Local:   python api.py
  Docker:  docker run -p 8080:8080 jde-api
"""
import json
import logging
import os
import re
import time
from datetime import datetime, timezone

from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv(override=False)

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from azure.identity.aio import DefaultAzureCredential
from azure.core.credentials import AccessToken
from agent_framework.azure import AzureAIClient
import markdown as md_lib

from extractor.agent import download_and_extract_pdf, EXTRACTOR_INSTRUCTIONS
from analyzer.agent import MCP_TOOL, ANALYZER_INSTRUCTIONS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# API key → TokenCredential adapter
# ──────────────────────────────────────────────────────────────

class _ApiKeyCredential:
    """Wraps an API key as an async TokenCredential for the Agent Framework SDK.

    Uses the key as a Bearer token. Works with Azure AI Services resources
    that have local auth (API keys) enabled.
    """

    def __init__(self, key: str):
        self._key = key

    async def get_token(self, *scopes, **kwargs) -> AccessToken:
        return AccessToken(self._key, int(time.time()) + 86400)

    async def close(self):
        pass


class _StaticTokenCredential:
    """Wraps a pre-fetched Azure AD token as an async TokenCredential.

    Useful for testing when RBAC assignment is not available.
    Token must be refreshed externally before expiry (~1 hour).
    """

    def __init__(self, token: str):
        self._token = token

    async def get_token(self, *scopes, **kwargs) -> AccessToken:
        return AccessToken(self._token, int(time.time()) + 3600)

    async def close(self):
        pass


# ──────────────────────────────────────────────────────────────
# Request / Response models (matches v1.0 contract)
# ──────────────────────────────────────────────────────────────


class AnalyzeRequest(BaseModel):
    object_name: str


class AnalyzeResponse(BaseModel):
    checkerResponse: str
    analysisResponse: str


# ──────────────────────────────────────────────────────────────
# Application state
# ──────────────────────────────────────────────────────────────

_credential = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize credential on startup, clean up on shutdown."""
    global _credential
    # Auth priority: static token > API key > DefaultAzureCredential
    static_token = os.getenv("FOUNDRY_TOKEN")
    api_key = os.getenv("FOUNDRY_API_KEY")
    if static_token:
        _credential = _StaticTokenCredential(static_token)
        logger.info("API ready — using static token credential")
    elif api_key:
        _credential = _ApiKeyCredential(api_key)
        logger.info("API ready — using API key credential")
    else:
        _credential = DefaultAzureCredential()
        logger.info("API ready — using DefaultAzureCredential")
    yield
    await _credential.close()


app = FastAPI(
    title="JDE Integrity Analyzer API",
    version="2.0",
    lifespan=lifespan,
)


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────


def _parse_has_data(extractor_text: str) -> bool:
    """Extract has_data from ExtractorAgent JSON output.

    Falls back to text-length heuristic if JSON parsing fails.
    """
    try:
        # Try to parse the full output as JSON
        data = json.loads(extractor_text)
        return bool(data.get("has_data", False))
    except (json.JSONDecodeError, TypeError):
        pass

    # Fallback: look for "has_data": true/false anywhere in the text
    match = re.search(r'"has_data"\s*:\s*(true|false)', extractor_text, re.IGNORECASE)
    if match:
        return match.group(1).lower() == "true"

    # Last resort: text length heuristic (same as v1.0's 300-char threshold)
    return len(extractor_text.strip()) > 300


def _parse_report_info(object_name: str) -> tuple[str, str]:
    """Extract report type and company code from the PDF filename.

    Example: 'R047001A_SCH0001_32188_PDF.pdf' → ('R047001A', 'SCH0001')
    """
    parts = object_name.replace(".pdf", "").replace(".PDF", "").split("_")
    report_type = parts[0] if len(parts) >= 1 else "Unknown"
    company = parts[1] if len(parts) >= 2 else "Unknown"
    return report_type, company


_HTML_TEMPLATE = """\
<table width="100%" cellpadding="0" cellspacing="0" bgcolor="#1a365d">
<tr>
<td>
  <table width="100%" cellpadding="8" cellspacing="0">
  <tr>
    <td><font color="#ffffff" size="5"><b>JDE Integrity Analysis</b></font><br>
      <font color="#bee3f8" size="2">{report_type} - {company}</font>
    </td>
    <td align="right" valign="top">
      {status_badge}
    </td>
  </tr>
  </table>
</td>
</tr>
</table>
<table width="100%" cellpadding="8" cellspacing="0" bgcolor="#ffffff">
<tr>
<td>
  {body_html}
</td>
</tr>
</table>
<table width="100%" cellpadding="4" cellspacing="0">
<tr>
<td><hr></td>
</tr>
<tr>
<td><font color="#a0aec0" size="1">
  Generated {timestamp} | JDE AI Integrity Analyzer v2.0
</font></td>
<td align="right"><font color="#a0aec0" size="1">
  Cantex, Inc.
</font></td>
</tr>
</table>"""

_BADGE_ISSUES = '<font color="#cc0000"><b>[ISSUES FOUND]</b></font>'
_BADGE_CLEAR = '<font color="#228B22"><b>[ALL CLEAR]</b></font>'


def _sanitize_html_for_jde(html: str) -> str:
    """Convert markdown-generated HTML to JDE-safe tags.

    JDE's CL001_SimpleEmailJob rejects style= attributes and many
    modern HTML tags. This converts to basic tags only:
    table, tr, td, th, p, b, i, br, hr, font, ul, ol, li.
    """
    import re as _re
    # Strip all style= attributes from any tag
    html = _re.sub(r'\s+style="[^"]*"', '', html)
    # Replace heading tags with bold font
    html = _re.sub(r'<h1[^>]*>(.*?)</h1>', r'<p><font size="4"><b>\1</b></font></p>', html)
    html = _re.sub(r'<h2[^>]*>(.*?)</h2>', r'<p><font size="3"><b>\1</b></font></p>', html)
    html = _re.sub(r'<h3[^>]*>(.*?)</h3>', r'<p><b>\1</b></p>', html)
    # Replace <strong> with <b>
    html = html.replace('<strong>', '<b>').replace('</strong>', '</b>')
    # Replace <em> with <i>
    html = html.replace('<em>', '<i>').replace('</em>', '</i>')
    # Strip <span> tags entirely (keep content)
    html = _re.sub(r'<span[^>]*>', '', html)
    html = html.replace('</span>', '')
    # Strip <code> tags (keep content)
    html = _re.sub(r'<code[^>]*>', '', html)
    html = html.replace('</code>', '')
    # Strip <pre> tags (keep content)
    html = _re.sub(r'<pre[^>]*>', '', html)
    html = html.replace('</pre>', '')
    return html


def _format_html_email(
    object_name: str,
    checker_response: str,
    analysis_markdown: str,
) -> str:
    """Convert the analyzer's markdown output into a styled HTML email."""
    report_type, company = _parse_report_info(object_name)

    is_issues = checker_response == "Yes"
    status_badge = _BADGE_ISSUES if is_issues else _BADGE_CLEAR

    body_html = md_lib.markdown(
        analysis_markdown,
        extensions=["tables", "fenced_code"],
    )
    body_html = _sanitize_html_for_jde(body_html)

    timestamp = datetime.now(timezone.utc).strftime("%B %d, %Y at %H:%M UTC")

    return _HTML_TEMPLATE.format(
        report_type=report_type,
        company=company,
        status_badge=status_badge,
        body_html=body_html,
        timestamp=timestamp,
    )


# ──────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────


@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0"}


@app.post("/v1/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest):
    """Run the ExtractorAgent → AnalyzerAgent pipeline.

    Returns {checkerResponse, analysisResponse} matching the v1.0 contract.
    """
    if not request.object_name or not request.object_name.strip():
        raise HTTPException(status_code=400, detail="Missing 'object_name' in request body")

    object_name = request.object_name.strip()
    endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT")
    model = os.getenv("FOUNDRY_MODEL_DEPLOYMENT_NAME")

    if not endpoint or not model:
        raise HTTPException(
            status_code=500,
            detail="Missing FOUNDRY_PROJECT_ENDPOINT or FOUNDRY_MODEL_DEPLOYMENT_NAME",
        )

    logger.info(f"Analyzing: {object_name}")

    try:
        # ── Step 1: ExtractorAgent ────────────────────────────
        extractor_client = AzureAIClient(
            project_endpoint=endpoint,
            model_deployment_name=model,
            credential=_credential,
        )
        async with extractor_client.as_agent(
            name="ExtractorAgent",
            instructions=EXTRACTOR_INSTRUCTIONS,
            tools=[download_and_extract_pdf],
        ) as extractor:
            extractor_result = await extractor.run(
                f"Please download and extract the PDF: {object_name}"
            )

        extractor_text = extractor_result.text
        logger.info(f"Extraction complete: {len(extractor_text)} chars")
        logger.info(f"Extractor output: {extractor_text[:1000]}")

        # ── Step 2: Determine checkerResponse ─────────────────
        has_data = _parse_has_data(extractor_text)

        if not has_data:
            logger.info(f"No data found in {object_name} (has_data={has_data})")
            html = _format_html_email(
                object_name, "No",
                "**No discrepancies found.** The integrity report contained no data requiring analysis.",
            )
            return AnalyzeResponse(
                checkerResponse="No",
                analysisResponse=html,
            )

        # ── Step 3: AnalyzerAgent (only if has_data) ──────────
        analyzer_client = AzureAIClient(
            project_endpoint=endpoint,
            model_deployment_name=model,
            credential=_credential,
        )
        async with analyzer_client.as_agent(
            name="AnalyzerAgent",
            instructions=ANALYZER_INSTRUCTIONS,
            tools=[MCP_TOOL],
        ) as analyzer:
            analyzer_result = await analyzer.run(
                f"Analyze this extraction from the JDE Integrity Report:\n\n{extractor_text}"
            )

        analysis_text = analyzer_result.text
        logger.info(f"Analysis complete: {len(analysis_text)} chars")

        html = _format_html_email(object_name, "Yes", analysis_text)

        return AnalyzeResponse(
            checkerResponse="Yes",
            analysisResponse=html,
        )

    except Exception as ex:
        logger.exception(f"Error analyzing {object_name}")
        raise HTTPException(status_code=500, detail=str(ex))


# ──────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")
