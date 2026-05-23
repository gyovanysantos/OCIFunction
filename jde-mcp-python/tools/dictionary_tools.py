"""Layer 1 — Curated data dictionary tools."""
import json
import logging
from mcp.server.fastmcp import FastMCP

from services.dictionary import search_dictionary, list_tables, get_table

logger = logging.getLogger(__name__)


def register(mcp: FastMCP) -> None:

    @mcp.tool(
        name="jde_dictionary_search",
        description=(
            "Search the JDE data dictionary by keyword to discover tables, columns, and their meanings. "
            "Use this FIRST when you need to find which JDE table and columns are relevant for a query. "
            "Args: keyword (string) — matches table names, descriptions, functional areas, and column aliases. "
            "Returns: JSON array of matching tables with full column definitions."
        ),
        annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    )
    async def jde_dictionary_search(keyword: str) -> str:
        try:
            results = search_dictionary(keyword)
            if not results:
                return f'No tables found matching "{keyword}". Try a broader term like "sales", "inventory", or "customer".'
            output = [
                {
                    "tableName": t["tableName"],
                    "displayName": t["displayName"],
                    "description": t["description"],
                    "functionalArea": t["functionalArea"],
                    "columns": t["columns"],
                }
                for t in results
            ]
            return json.dumps(output, indent=2)
        except Exception as exc:
            raise RuntimeError(f"Error searching dictionary: {exc}") from exc

    @mcp.tool(
        name="jde_dictionary_list",
        description=(
            "List all JDE tables available in the curated data dictionary. "
            "Returns a summary: tableName, displayName, functionalArea for every table. "
            "Args: none."
        ),
        annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    )
    async def jde_dictionary_list() -> str:
        try:
            return json.dumps(list_tables(), indent=2)
        except Exception as exc:
            raise RuntimeError(f"Error listing tables: {exc}") from exc

    @mcp.tool(
        name="jde_dictionary_table",
        description=(
            "Get the full column definitions for a specific JDE table by name. "
            "Use when you already know the table name and need all available columns with aliases, descriptions, and data types. "
            "Args: table_name (string) e.g. 'F4211'."
        ),
        annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    )
    async def jde_dictionary_table(table_name: str) -> str:
        try:
            table = get_table(table_name)
            if not table:
                raise RuntimeError(
                    f'Table "{table_name}" not found in the dictionary. Use jde_dictionary_search to find the right table name.'
                )
            return json.dumps(table, indent=2)
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Error getting table: {exc}") from exc
