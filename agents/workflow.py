"""Sequential workflow: ExtractorAgent → AnalyzerAgent.

The workflow takes a PDF object name as input, runs it through the Extractor
(PDF → structured data), then passes the result to the Analyzer (structured data
→ MCP-verified analysis).

Architecture:
    Input (object_name) → ExtractorAgent → structured JSON → AnalyzerAgent → final report
"""
import os

from azure.identity.aio import DefaultAzureCredential
from agent_framework import WorkflowBuilder
from agent_framework.azure import AzureAIClient

from extractor.agent import download_and_extract_pdf, EXTRACTOR_INSTRUCTIONS
from analyzer.agent import MCP_TOOL, ANALYZER_INSTRUCTIONS


async def build_workflow(credential: DefaultAzureCredential):
    """Build and return the sequential Extractor → Analyzer workflow.

    Creates two separate AzureAIClient instances (one per agent, as required)
    and wires them into a graph-based workflow.

    Args:
        credential: Async Azure credential for authenticating with Foundry.

    Returns:
        A tuple of (workflow, extractor_ctx, analyzer_ctx) where the ctx objects
        are the async context managers that must be kept alive.
    """
    endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT")
    model = os.getenv("FOUNDRY_MODEL_DEPLOYMENT_NAME")

    # ── ExtractorAgent: PDF download + text extraction tool ────
    extractor_client = AzureAIClient(
        project_endpoint=endpoint,
        model_deployment_name=model,
        credential=credential,
    )
    extractor_ctx = extractor_client.as_agent(
        name="ExtractorAgent",
        instructions=EXTRACTOR_INSTRUCTIONS,
        tools=[download_and_extract_pdf],
    )

    # ── AnalyzerAgent: MCP tools for live JDE queries ─────────
    analyzer_client = AzureAIClient(
        project_endpoint=endpoint,
        model_deployment_name=model,
        credential=credential,
    )
    analyzer_ctx = analyzer_client.as_agent(
        name="AnalyzerAgent",
        instructions=ANALYZER_INSTRUCTIONS,
        tools=[MCP_TOOL],
    )

    # Enter both async contexts
    extractor = await extractor_ctx.__aenter__()
    analyzer = await analyzer_ctx.__aenter__()

    # ── Build sequential workflow graph ────────────────────────
    # ExtractorAgent output is automatically passed as input to AnalyzerAgent
    workflow = (
        WorkflowBuilder(start_executor=extractor)
        .add_edge(extractor, analyzer)
        .build()
    )

    return workflow, extractor_ctx, analyzer_ctx
