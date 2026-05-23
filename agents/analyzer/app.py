"""Standalone HTTP entry point for the AnalyzerAgent.

Runs the AnalyzerAgent as an independent Foundry hosted agent.
Input: structured JSON extraction from ExtractorAgent.
Output: MCP-verified analysis report with confirmed/resolved/new issues.

Usage:
    Local:    python app.py          (port 8088, mapped to 8089 via compose)
    Docker:   docker run -p 8089:8088 analyzer
"""
import asyncio
import os
import time
import logging

from dotenv import load_dotenv

load_dotenv(override=False)

from azure.identity.aio import DefaultAzureCredential
from azure.core.credentials import AccessToken
from agent_framework.azure import AzureAIClient
from azure.ai.agentserver.agentframework import from_agent_framework

from agent import MCP_TOOL, ANALYZER_INSTRUCTIONS


class _StaticTokenCredential:
    def __init__(self, token: str):
        self._token = token

    async def get_token(self, *scopes, **kwargs) -> AccessToken:
        return AccessToken(self._token, int(time.time()) + 3600)

    async def close(self):
        pass

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT")
    model = os.getenv("FOUNDRY_MODEL_DEPLOYMENT_NAME")
    if not endpoint or not model:
        raise ValueError(
            "Missing FOUNDRY_PROJECT_ENDPOINT or FOUNDRY_MODEL_DEPLOYMENT_NAME"
        )

    mcp_url = os.getenv("MCP_SERVER_URL", "http://localhost:3000/mcp")
    logger.info(f"AnalyzerAgent starting — endpoint={endpoint}, model={model}")
    logger.info(f"MCP server URL: {mcp_url}")

    static_token = os.getenv("FOUNDRY_TOKEN")
    credential = _StaticTokenCredential(static_token) if static_token else DefaultAzureCredential()
    try:
        client = AzureAIClient(
            project_endpoint=endpoint,
            model_deployment_name=model,
            credential=credential,
        )
        async with client.as_agent(
            name="AnalyzerAgent",
            instructions=ANALYZER_INSTRUCTIONS,
            tools=[MCP_TOOL],
        ) as agent:
            logger.info("AnalyzerAgent ready on port 8088")
            await from_agent_framework(agent).run_async()
    finally:
        await credential.close()


if __name__ == "__main__":
    asyncio.run(main())
