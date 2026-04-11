"""HTTP entry point for the JDE Integrity Analyzer — Foundry hosted agent.

This is the main entry point that:
1. Creates the ExtractorAgent (PDF → structured data)
2. Creates the AnalyzerAgent (structured data → MCP-verified analysis)
3. Wires them into a sequential workflow
4. Serves via the Foundry hosting adapter on port 8088

Usage:
    Local dev:  python app.py          (reads .env for Foundry credentials)
    Deployed:   Foundry Agent Service  (env vars set by the platform)
"""
import asyncio
import os
import logging

from dotenv import load_dotenv

# IMPORTANT: override=False so Foundry runtime env vars take precedence over .env
load_dotenv(override=False)

from azure.identity.aio import DefaultAzureCredential
from azure.ai.agentserver.agentframework import from_agent_framework

from workflow import build_workflow

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    """Start the agent HTTP server."""
    logger.info("Starting JDE Integrity Analyzer workflow...")

    # Validate required environment variables
    endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT")
    model = os.getenv("FOUNDRY_MODEL_DEPLOYMENT_NAME")
    if not endpoint or not model:
        raise ValueError(
            "Missing required environment variables:\n"
            "  FOUNDRY_PROJECT_ENDPOINT — Your Foundry project endpoint URL\n"
            "  FOUNDRY_MODEL_DEPLOYMENT_NAME — Your model deployment name (e.g. gpt-4o)\n"
            "Set them in .env or as environment variables."
        )

    mcp_url = os.getenv("MCP_SERVER_URL", "http://localhost:3000/mcp")
    logger.info(f"Foundry endpoint: {endpoint}")
    logger.info(f"Model deployment: {model}")
    logger.info(f"MCP server URL: {mcp_url}")

    credential = DefaultAzureCredential()

    try:
        # Build the Extractor → Analyzer workflow
        workflow, extractor_ctx, analyzer_ctx = await build_workflow(credential)

        logger.info("Workflow built: ExtractorAgent → AnalyzerAgent")
        logger.info("Starting HTTP server on port 8088...")

        # Serve via Foundry hosting adapter
        await from_agent_framework(workflow).run_async()

    finally:
        # Clean up async context managers
        await analyzer_ctx.__aexit__(None, None, None)
        await extractor_ctx.__aexit__(None, None, None)
        await credential.close()


if __name__ == "__main__":
    asyncio.run(main())
