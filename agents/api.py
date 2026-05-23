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

from azure.communication.email.aio import EmailClient as ACSEmailClient
from fastapi import BackgroundTasks, FastAPI, HTTPException
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
<table width="100%" cellpadding="0" cellspacing="0" bgcolor="#0d0e12">
<tr><td>
<table width="100%" cellpadding="0" cellspacing="0" bgcolor="#13151c">
<tr>
  <td width="4" bgcolor="#f47c2f">&nbsp;</td>
  <td>
    <table width="100%" cellpadding="12" cellspacing="0">
    <tr>
      <td valign="middle">
        <table cellpadding="0" cellspacing="0">
        <tr>
          <td bgcolor="#f47c2f" width="36" height="28" align="center" valign="middle">
            <font color="#ffffff" size="2"><b>CL</b></font>
          </td>
          <td width="10">&nbsp;</td>
          <td>
            <font color="#f47c2f" size="5"><b>JDE INTEGRITY ANALYSIS</b></font><br>
            <font color="#8a8a9a" size="2">{report_type} &nbsp;|&nbsp; {company}</font>
          </td>
        </tr>
        </table>
      </td>
      <td align="right" valign="middle">
        {status_badge}
      </td>
    </tr>
    </table>
  </td>
</tr>
</table>
<table width="100%" cellpadding="16" cellspacing="0" bgcolor="#1e2130">
<tr>
  <td>
    <font color="#e8e6de">{body_html}</font>
  </td>
</tr>
</table>
<table width="100%" cellpadding="8" cellspacing="0" bgcolor="#0d0e12">
<tr>
  <td>
    <font color="#8a8a9a" size="1">Generated {timestamp} &nbsp;|&nbsp; JDE AI Integrity Analyzer v2.0</font>
  </td>
  <td align="right">
    <font color="#f47c2f" size="1"><b>Centrilogic</b></font>
  </td>
</tr>
</table>
</td></tr>
</table>"""

_BADGE_ISSUES = (
    '<table cellpadding="4" cellspacing="0" bgcolor="#f25353">'
    '<tr><td><font color="#ffffff"><b>ISSUES FOUND</b></font></td></tr>'
    '</table>'
)
_BADGE_CLEAR = (
    '<table cellpadding="4" cellspacing="0" bgcolor="#2ddc7c">'
    '<tr><td><font color="#0d0e12"><b>ALL CLEAR</b></font></td></tr>'
    '</table>'
)


def _sanitize_html_for_jde(html: str) -> str:
    """Convert markdown-generated HTML to JDE-safe tags.

    JDE's CL001_SimpleEmailJob rejects style= attributes and many
    modern HTML tags. This converts to basic tags only:
    table, tr, td, th, p, b, i, br, hr, font, ul, ol, li.
    """
    import re as _re
    # Strip all style= attributes from any tag
    html = _re.sub(r'\s+style="[^"]*"', '', html)
    # Replace heading tags with Centrilogic-accented bold font
    html = _re.sub(r'<h1[^>]*>(.*?)</h1>', r'<p><font color="#f47c2f" size="4"><b>\1</b></font></p>', html)
    html = _re.sub(r'<h2[^>]*>(.*?)</h2>', r'<p><font color="#f47c2f" size="3"><b>\1</b></font></p>', html)
    html = _re.sub(r'<h3[^>]*>(.*?)</h3>', r'<p><font color="#f9a85d"><b>\1</b></font></p>', html)
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
# Email notification (Azure Communication Services Email)
# ──────────────────────────────────────────────────────────────
# No admin consent required — uses an ACS connection string (access key).
# Set ACS_CONNECTION_STRING and EMAIL_NOTIFICATION_TO to enable.
# Leave either blank to silently skip email (JDE response is unaffected).
# ──────────────────────────────────────────────────────────────

_ACS_FROM_DEFAULT = "DoNotReply@436186b1-bceb-48e0-bded-1fcbb6fea3a9.azurecomm.net"


async def _send_email_notification(subject: str, html_body: str) -> None:
    """Send analysis report via ACS Email as a fire-and-forget background task.

    Failures are logged but never propagate — email must not affect the JDE response.
    """
    connection_string = os.getenv("ACS_CONNECTION_STRING")
    to_address = os.getenv("EMAIL_NOTIFICATION_TO")

    if not connection_string or not to_address:
        logger.debug("Email notification skipped — ACS_CONNECTION_STRING or EMAIL_NOTIFICATION_TO not set")
        return

    from_address = os.getenv("EMAIL_FROM_ADDRESS", _ACS_FROM_DEFAULT)

    try:
        async with ACSEmailClient.from_connection_string(connection_string) as client:
            poller = await client.begin_send({
                "senderAddress": from_address,
                "recipients": {"to": [{"address": to_address}]},
                "content": {"subject": subject, "html": html_body},
            })
            result = await poller.result()
        logger.info(f"Email sent → {to_address} (id={result.get('id', '?')})")

    except Exception as exc:
        logger.error(f"Email notification failed (non-fatal): {exc}")


# ──────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────


@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0"}


@app.post("/v1/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest, background_tasks: BackgroundTasks):
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
            report_type, company = _parse_report_info(object_name)
            background_tasks.add_task(
                _send_email_notification,
                f"JDE Integrity Report — {report_type} ({company}) — ALL CLEAR",
                html,
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

        report_type, company = _parse_report_info(object_name)
        background_tasks.add_task(
            _send_email_notification,
            f"JDE Integrity Report — {report_type} ({company}) — ISSUES FOUND",
            html,
        )

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
