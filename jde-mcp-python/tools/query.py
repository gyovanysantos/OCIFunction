"""Layer 3 — Generic table query tool."""
import json
import logging
from typing import Optional
from mcp.server.fastmcp import FastMCP

from config import CHARACTER_LIMIT
from services.ais_client import query_table
from services.dictionary import resolve_columns

logger = logging.getLogger(__name__)


def register(mcp: FastMCP) -> None:

    @mcp.tool(
        name="jde_query_table",
        description=(
            "Execute a read-only query against any JDE EnterpriseOne table via AIS Data Service. "
            "IMPORTANT: Before calling, use jde_dictionary_search or jde_dictionary_table to discover valid table names "
            "and column aliases. JDE uses cryptic aliases (e.g. DOCO = Order Number, AN8 = Address Number) — guessing will fail. "
            "Args: table_name (string), columns (list of alias strings), "
            "filters (list of {column, operator, value}), max_rows (1-500, default 50). "
            "Operators: EQUAL, NOT_EQUAL, LESS, LESS_EQUAL, GREATER, GREATER_EQUAL, BETWEEN, LIST, "
            "STR_CONTAIN, STR_START_WITH, STR_END_WITH, STR_BLANK, STR_NOT_BLANK. "
            "Returns: JSON with rows array and metadata (totalRecords, returnedRecords, hasMore)."
        ),
        annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    )
    async def jde_query_table(
        table_name: str,
        columns: list[str],
        filters: Optional[list[dict]] = None,
        max_rows: int = 50,
    ) -> str:
        try:
            resolved = resolve_columns(table_name, columns)
            warning = ""
            if resolved["invalid"]:
                warning = (
                    f"Warning: Unrecognized columns for {table_name}: {', '.join(resolved['invalid'])}. "
                    "They may still work if they exist in JDE but are not in the curated dictionary.\n\n"
                )

            resp = await query_table(
                table_name=table_name,
                columns=columns,
                filters=[
                    {"column": f["column"], "operator": f["operator"], "value": f["value"]}
                    for f in (filters or [])
                ] or None,
                max_rows=max_rows,
            )

            grid = (resp.get("fs_DATABROWSE") or {}).get("data", {}).get("gridData")
            if not grid:
                return warning + "No data returned from AIS. The table may be empty or filters too restrictive."

            output = {
                "tableName": table_name,
                "totalRecords": grid.get("summary", {}).get("records"),
                "returnedRecords": len(grid.get("rowset", [])),
                "hasMore": grid.get("summary", {}).get("moreRecords"),
                "rows": grid.get("rowset", []),
            }
            text = warning + json.dumps(output, indent=2)
            if len(text) > CHARACTER_LIMIT:
                text = (
                    text[:CHARACTER_LIMIT]
                    + f"\n\n... [TRUNCATED — {grid.get('summary', {}).get('records')} total records. Narrow your filters or reduce max_rows.]"
                )
            return text
        except Exception as exc:
            raise RuntimeError(
                f"Error querying {table_name}: {exc}. Verify the table name and column aliases using jde_dictionary_search."
            ) from exc
