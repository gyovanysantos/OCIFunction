// ──────────────────────────────────────────────────────────────
// Layer 0 — Dynamic Data Dictionary Discovery Tools
//
// These tools query JDE system tables LIVE to discover any table
// structure, not just the curated ones in dictionary.json.
//
// Use jde_discover_table when you know the table name and need
// its columns. Use jde_search_tables when looking for tables
// by keyword.
// ──────────────────────────────────────────────────────────────

import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import {
  JdeDiscoverTableSchema,
  JdeSearchTablesSchema,
  type JdeDiscoverTableInput,
  type JdeSearchTablesInput,
} from "../schemas/tools.js";
import { discoverTable, searchTables } from "../services/dd-discovery.js";
import { CHARACTER_LIMIT } from "../constants.js";

function truncate(text: string): string {
  if (text.length <= CHARACTER_LIMIT) return text;
  return text.slice(0, CHARACTER_LIMIT) + "\n\n⚠️ Output truncated at 50,000 characters.";
}

// ── jde_discover_table ────────────────────────────────────────

export function registerDiscoverTable(server: McpServer): void {
  server.registerTool(
    "jde_discover_table",
    {
      title: "Discover JDE Table Structure",
      description: `Discover the full column structure of ANY JDE table by querying the live data dictionary (F9210 + F9200).

Unlike jde_dictionary_table (which only knows curated tables), this tool can describe ANY table in the JDE environment — including custom tables (F55xxx), less common standard tables, and tables added by updates.

Results are cached in memory, so repeated calls for the same table are instant.

Args:
  - tableName (string): JDE table name, e.g. "F4211", "F0101", "F55001"

Returns:
  Full table structure: table name, description, and all columns with alias, description, data type, size, and sequence.

Examples:
  - "F4211" → Sales Order Detail (22+ columns with aliases DOCO, AN8, LITM, etc.)
  - "F0101" → Address Book Master
  - "F55001" → Custom table (if it exists in this environment)

Use jde_search_tables first if you don't know the table name.`,
      inputSchema: JdeDiscoverTableSchema,
      annotations: {
        readOnlyHint: true,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: true,       // queries live JDE — can discover any table
      },
    },
    async (params: JdeDiscoverTableInput) => {
      try {
        const table = await discoverTable(params.tableName);
        const text = truncate(JSON.stringify(table, null, 2));
        return {
          content: [{ type: "text" as const, text }],
        };
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        return {
          isError: true,
          content: [{
            type: "text" as const,
            text: `Error discovering table "${params.tableName}": ${msg}`,
          }],
        };
      }
    }
  );
}

// ── jde_search_tables ─────────────────────────────────────────

export function registerSearchTables(server: McpServer): void {
  server.registerTool(
    "jde_search_tables",
    {
      title: "Search JDE Tables",
      description: `Search for JDE tables by keyword, querying the Object Configuration Manager (F9860) live.

Returns table names and descriptions matching your keyword. Use this when you don't know the exact table name — then call jde_discover_table to get the full column structure.

Args:
  - keyword (string): Search term — matches table names and descriptions.
  - maxRows (number, default 20): Maximum results to return.

Returns:
  JSON array of { tableName, description, objectType } for matching tables.

Examples:
  - "sales order" → finds F4201, F4211, F42019, etc.
  - "address book" → finds F0101, F0111, F0115, etc.
  - "inventory" → finds F41021, F4101, F4102, etc.
  - "F42" → finds all tables starting with F42`,
      inputSchema: JdeSearchTablesSchema,
      annotations: {
        readOnlyHint: true,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: true,
      },
    },
    async (params: JdeSearchTablesInput) => {
      try {
        const results = await searchTables(params.keyword, params.maxRows);

        if (results.length === 0) {
          return {
            content: [{
              type: "text" as const,
              text: `No tables found matching "${params.keyword}". Try broader terms like "order", "customer", or "item", or use a table prefix like "F42".`,
            }],
          };
        }

        const text = truncate(JSON.stringify(results, null, 2));
        return {
          content: [{ type: "text" as const, text }],
        };
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        return {
          isError: true,
          content: [{
            type: "text" as const,
            text: `Error searching tables: ${msg}`,
          }],
        };
      }
    }
  );
}
