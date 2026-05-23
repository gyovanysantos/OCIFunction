"""Layer 3 — Generic JDE orchestration caller."""
import json
import logging
from mcp.server.fastmcp import FastMCP

from config import CHARACTER_LIMIT
from services.ais_client import call_orchestration

logger = logging.getLogger(__name__)


def register(mcp: FastMCP) -> None:

    @mcp.tool(
        name="jde_call_orchestration",
        description=(
            "Invoke a named JDE Orchestration via the AIS REST API. "
            "Use for WRITE/TRANSACTIONAL operations — updating records or running multi-step business processes "
            "pre-built as orchestrations in Orchestrator Studio. "
            "WARNING: This tool can MODIFY DATA in JDE. Use only when the user explicitly requests create/update/delete. "
            "For READ operations, prefer jde_query_table or the curated tools. "
            "Args: orchestration_name (string), inputs (dict of key-value input parameters). "
            "Returns: JSON response from the orchestration (structure depends on the orchestration's output definition)."
        ),
        annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": True},
    )
    async def jde_call_orchestration(orchestration_name: str, inputs: dict) -> str:
        try:
            result = await call_orchestration(orchestration_name, inputs)
            text = json.dumps(result, indent=2)
            if len(text) > CHARACTER_LIMIT:
                text = text[:CHARACTER_LIMIT] + "\n\n... [TRUNCATED]"
            return text
        except Exception as exc:
            raise RuntimeError(
                f'Error calling orchestration "{orchestration_name}": {exc}. '
                "Verify the orchestration name and required input parameters."
            ) from exc
