"""Sequential workflow: ExtractorAgent → AnalyzerAgent using OCI ADK.

Deterministic workflow pattern: plain Python control flow chaining
agent.run() calls sequentially. The ADK handles the agent loop
(LLM reasoning + tool calling) on OCI GenAI Agents Service.

Architecture:
    Input (object_name) → ExtractorAgent → structured JSON → AnalyzerAgent → final report
"""
import asyncio
import logging
import os

from oci.addons.adk import Agent, AgentClient

from extractor.agent import download_and_extract_pdf, EXTRACTOR_INSTRUCTIONS
from mcp_bridge import (
    jde_ap_voucher_query,
    jde_gl_balance_query,
    jde_gl_detail_query,
    jde_ap_gl_integrity_check,
    jde_batch_query,
    jde_batch_transaction_query,
    jde_unposted_batch_check,
)
from analyzer.agent import ANALYZER_INSTRUCTIONS

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Module-level agent instances (initialized once, reused)
# ──────────────────────────────────────────────────────────────

_client: AgentClient | None = None
_extractor: Agent | None = None
_analyzer: Agent | None = None


def _ensure_agents() -> None:
    """Initialize ADK client and agents on first use.

    Creates an AgentClient with OCI auth, builds both Agent instances,
    and calls setup() to sync local tools with the remote agent endpoints.
    setup() is idempotent — safe to call multiple times.
    """
    global _client, _extractor, _analyzer
    if _extractor is not None:
        return

    # ── Auth ──────────────────────────────────────────────────
    auth_type = os.getenv("OCI_AUTH_TYPE", "api_key")
    region = os.getenv("OCI_REGION", "us-phoenix-1")

    client_kwargs: dict = {"auth_type": auth_type, "region": region}
    if auth_type == "api_key":
        client_kwargs["profile"] = os.getenv("OCI_PROFILE", "DEFAULT")

    _client = AgentClient(**client_kwargs)
    logger.info(f"AgentClient created — auth={auth_type}, region={region}")

    # ── Extractor Agent ───────────────────────────────────────
    _extractor = Agent(
        client=_client,
        agent_endpoint_id=os.getenv("EXTRACTOR_AGENT_ENDPOINT_ID"),
        name="ExtractorAgent",
        instructions=EXTRACTOR_INSTRUCTIONS,
        tools=[download_and_extract_pdf],
    )

    # ── Analyzer Agent ────────────────────────────────────────
    _analyzer = Agent(
        client=_client,
        agent_endpoint_id=os.getenv("ANALYZER_AGENT_ENDPOINT_ID"),
        name="AnalyzerAgent",
        instructions=ANALYZER_INSTRUCTIONS,
        tools=[
            jde_ap_voucher_query,
            jde_gl_balance_query,
            jde_gl_detail_query,
            jde_ap_gl_integrity_check,
            jde_batch_query,
            jde_batch_transaction_query,
            jde_unposted_batch_check,
        ],
    )

    # ── Sync local tools → remote agent endpoints ─────────────
    logger.info("Setting up ExtractorAgent (syncing tools to OCI)...")
    _extractor.setup()
    logger.info("Setting up AnalyzerAgent (syncing tools to OCI)...")
    _analyzer.setup()
    logger.info("Both agents initialized and synced with OCI GenAI Agents.")


# ──────────────────────────────────────────────────────────────
# Workflow steps (called from api.py)
# ──────────────────────────────────────────────────────────────


def _ensure_event_loop() -> None:
    """Ensure an event loop exists in the current thread.

    ADK agent.run() internally needs an asyncio event loop.
    When called via asyncio.to_thread(), the worker thread has none.
    """
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())


def run_extractor(object_name: str) -> str:
    """Step 1: Download PDF and extract structured data.

    Returns the ExtractorAgent's text output (should be JSON).
    """
    _ensure_event_loop()
    _ensure_agents()
    logger.info(f"ExtractorAgent: processing {object_name}")
    response = _extractor.run(
        f"Please download and extract the PDF: {object_name}"
    )
    text = response.output
    if not text:
        logger.warning("ExtractorAgent returned empty/null output")
        text = '{"has_data": false, "error": "ExtractorAgent returned no output"}'
    logger.info(f"ExtractorAgent complete: {len(text)} chars")
    return text


def run_analyzer(extractor_text: str) -> str:
    """Step 2: Cross-reference extraction against live JDE data via MCP.

    Returns the AnalyzerAgent's markdown analysis report.
    """
    _ensure_event_loop()
    _ensure_agents()
    logger.info("AnalyzerAgent: starting cross-reference analysis...")
    response = _analyzer.run(
        f"Analyze this extraction from the JDE Integrity Report:\n\n{extractor_text}"
    )
    text = response.output
    if not text:
        logger.warning("AnalyzerAgent returned empty/null output")
        text = "AnalyzerAgent returned no output. The model may have encountered an error during tool calls."
    logger.info(f"AnalyzerAgent complete: {len(text)} chars")
    return text
