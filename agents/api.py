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

from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv(override=False)

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from azure.identity.aio import DefaultAzureCredential
from azure.core.credentials import AccessToken
from agent_framework.azure import AzureAIClient

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

        # ── Step 2: Determine checkerResponse ─────────────────
        has_data = _parse_has_data(extractor_text)

        if not has_data:
            logger.info(f"No data found in {object_name}")
            return AnalyzeResponse(
                checkerResponse="No",
                analysisResponse="No data found, analysis skipped.",
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

        return AnalyzeResponse(
            checkerResponse="Yes",
            analysisResponse=analysis_text,
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
