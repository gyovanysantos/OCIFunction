"""Run the ExtractorAgent → AnalyzerAgent workflow locally (host Python).

This script runs the agents IN-PROCESS using the host's Azure CLI credential,
bypassing the Docker container auth issue. The MCP server must still be running
in Docker at localhost:3000.

Usage:
    python tests/test_workflow_local.py
"""
import asyncio
import json
import os
import sys
import time

# ── Set up paths and env ──────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "agents"))

# Load .env from project root
from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"), override=False)

# Ensure Foundry and MCP env vars are set
os.environ.setdefault("MCP_SERVER_URL", "http://localhost:3000/mcp")

from azure.identity.aio import DefaultAzureCredential
from agent_framework.azure import AzureAIClient

# Import agent components (using sys.path set above)
from extractor.agent import download_and_extract_pdf, EXTRACTOR_INSTRUCTIONS
from analyzer.agent import MCP_TOOL, ANALYZER_INSTRUCTIONS

PDF_OBJECT = "R047001A_ZJDE0001_588_PDF.pdf"


async def main():
    endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT")
    model = os.getenv("FOUNDRY_MODEL_DEPLOYMENT_NAME")

    if not endpoint or not model:
        print("ERROR: Missing FOUNDRY_PROJECT_ENDPOINT or FOUNDRY_MODEL_DEPLOYMENT_NAME")
        sys.exit(1)

    print("=" * 70)
    print("JDE Integrity Analyzer — Local Workflow Test")
    print(f"  PDF:      {PDF_OBJECT}")
    print(f"  Endpoint: {endpoint}")
    print(f"  Model:    {model}")
    print(f"  MCP:      {os.getenv('MCP_SERVER_URL')}")
    print("=" * 70)

    credential = DefaultAzureCredential()

    try:
        # ── Step 1: ExtractorAgent ────────────────────────────
        print("\n[1/2] Running ExtractorAgent...")
        t0 = time.time()

        extractor_client = AzureAIClient(
            project_endpoint=endpoint,
            model_deployment_name=model,
            credential=credential,
        )
        async with extractor_client.as_agent(
            name="ExtractorAgent",
            instructions=EXTRACTOR_INSTRUCTIONS,
            tools=[download_and_extract_pdf],
        ) as extractor:
            extractor_result = await extractor.run(
                f"Please download and extract the PDF: {PDF_OBJECT}"
            )

        extractor_text = extractor_result.text
        elapsed = time.time() - t0
        print(f"  Done ({elapsed:.1f}s) — {len(extractor_text)} chars")
        print("\n--- Extractor Output ---")
        print(extractor_text[:3000])
        if len(extractor_text) > 3000:
            print(f"\n... (truncated, total {len(extractor_text)} chars)")

        # Save extractor output
        with open(os.path.join(ROOT, "tests", "extractor_output.json"), "w") as f:
            json.dump({"text": extractor_text}, f, indent=2)

        # ── Step 2: AnalyzerAgent ─────────────────────────────
        print("\n" + "=" * 70)
        print("[2/2] Running AnalyzerAgent...")
        t1 = time.time()

        analyzer_client = AzureAIClient(
            project_endpoint=endpoint,
            model_deployment_name=model,
            credential=credential,
        )
        async with analyzer_client.as_agent(
            name="AnalyzerAgent",
            instructions=ANALYZER_INSTRUCTIONS,
            tools=[MCP_TOOL],
        ) as analyzer:
            analyzer_result = await analyzer.run(
                f"Analyze this extraction from the JDE Integrity Report:\n\n{extractor_text}"
            )

        analyzer_text = analyzer_result.text
        elapsed = time.time() - t1
        print(f"  Done ({elapsed:.1f}s) — {len(analyzer_text)} chars")
        print("\n--- Analyzer Output ---")
        print(analyzer_text[:5000])
        if len(analyzer_text) > 5000:
            print(f"\n... (truncated, total {len(analyzer_text)} chars)")

        # Save analyzer output
        with open(os.path.join(ROOT, "tests", "analyzer_output.json"), "w") as f:
            json.dump({"text": analyzer_text}, f, indent=2)

        print("\n" + "=" * 70)
        print("WORKFLOW COMPLETE")
        print(f"  Extractor: {len(extractor_text)} chars")
        print(f"  Analyzer:  {len(analyzer_text)} chars")
        print("  Outputs saved to tests/extractor_output.json and tests/analyzer_output.json")
        print("=" * 70)

    finally:
        await credential.close()


if __name__ == "__main__":
    asyncio.run(main())
