"""Standalone HTTP entry point for the ExtractorAgent.

Runs the ExtractorAgent as an independent Foundry hosted agent.
Input: user message containing the object_name of a PDF in OCI bucket.
Output: structured JSON extraction (report type, company, discrepancies, etc.)

Usage:
    Local:    python app.py          (port 8088)
    Docker:   docker run -p 8088:8088 extractor
"""
import asyncio
import os
import logging

from dotenv import load_dotenv

load_dotenv(override=False)

from azure.identity.aio import DefaultAzureCredential
from agent_framework.azure import AzureAIClient
from azure.ai.agentserver.agentframework import from_agent_framework

from agent import download_and_extract_pdf, EXTRACTOR_INSTRUCTIONS

# download_and_extract_pdf is already a FunctionTool via @tool decorator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT")
    model = os.getenv("FOUNDRY_MODEL_DEPLOYMENT_NAME")
    if not endpoint or not model:
        raise ValueError(
            "Missing FOUNDRY_PROJECT_ENDPOINT or FOUNDRY_MODEL_DEPLOYMENT_NAME"
        )

    logger.info(f"ExtractorAgent starting — endpoint={endpoint}, model={model}")

    credential = DefaultAzureCredential()
    try:
        client = AzureAIClient(
            project_endpoint=endpoint,
            model_deployment_name=model,
            credential=credential,
        )
        async with client.as_agent(
            name="ExtractorAgent",
            instructions=EXTRACTOR_INSTRUCTIONS,
            tools=[download_and_extract_pdf],
        ) as agent:
            logger.info("ExtractorAgent ready on port 8088")
            await from_agent_framework(agent).run_async()
    finally:
        await credential.close()


if __name__ == "__main__":
    asyncio.run(main())
