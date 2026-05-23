"""Layer 0 — Dynamic table discovery tools."""
import json
import logging
from mcp.server.fastmcp import FastMCP

from config import CHARACTER_LIMIT
from services.dd_discovery import discover_table, search_tables

logger = logging.getLogger(__name__)


def _truncate(text: str) -> str:
    if len(text) <= CHARACTER_LIMIT:
        return text
    return text[:CHARACTER_LIMIT] + "\n\n[Output truncated at 50,000 characters.]"


def register(mcp: FastMCP) -> None:

    @mcp.tool(
        name="jde_discover_table",
        description=(
            "Discover the full column structure of ANY JDE table by querying the live data dictionary (F9210 + F9200). "
            "Unlike jde_dictionary_table (curated only), this can describe any table — custom (F55xxx), uncommon, or newer. "
            "Results are cached so repeated calls are instant. "
            "Args: table_name (string) e.g. 'F4211', 'F0101', 'F55001'. "
            "Returns: full structure with alias, description, dataType, size, and sequence for every column."
        ),
        annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    )
    async def jde_discover_table(table_name: str) -> str:
        try:
            table = await discover_table(table_name)
            return _truncate(json.dumps(table, indent=2))
        except Exception as exc:
            raise RuntimeError(f'Error discovering table "{table_name}": {exc}') from exc

    @mcp.tool(
        name="jde_search_tables",
        description=(
            "Search for JDE tables by keyword, querying the Object Configuration Manager (F9860) live. "
            "Use when you don't know the table name — then call jde_discover_table for full column structure. "
            "Args: keyword (string) — matches table names and descriptions; max_rows (int, default 20). "
            "Returns: JSON array of { tableName, description, objectType }. "
            "Examples: 'sales order' → F4201/F4211; 'F42' → all F42 tables."
        ),
        annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    )
    async def jde_search_tables(keyword: str, max_rows: int = 20) -> str:
        try:
            results = await search_tables(keyword, max_rows)
            if not results:
                return (
                    f'No tables found matching "{keyword}". '
                    'Try broader terms like "order", "customer", or "item", or a table prefix like "F42".'
                )
            return _truncate(json.dumps(results, indent=2))
        except Exception as exc:
            raise RuntimeError(f"Error searching tables: {exc}") from exc
