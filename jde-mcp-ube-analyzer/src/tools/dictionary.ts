import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import {
  JdeDictionarySearchSchema,
  JdeDictionaryListSchema,
  JdeDictionaryTableSchema,
  type JdeDictionarySearchInput,
} from "../schemas/tools.js";
import {
  searchDictionary,
  listTables,
  getTable,
} from "../services/dictionary.js";

export function registerDictionaryTools(server: McpServer): void {
  // ── Search the data dictionary ──────────────────────────────
  server.registerTool(
    "jde_dictionary_search",
    {
      title: "Search JDE Data Dictionary",
      description: `Search the JDE data dictionary by keyword to discover tables, columns, and their meanings.

Use this FIRST when you need to find out which JDE table and columns are relevant for a query. Returns matching tables with full column definitions including JDE aliases, data types, and descriptions.

Args:
  - keyword (string): Search term — matches table names, display names, descriptions, functional areas, and column names/aliases.

Returns:
  JSON array of matching tables, each with columns array containing alias, name, description, dataType, and example.

Examples:
  - "sales order" → returns F4201 (header) and F4211 (detail)
  - "customer" → returns F0101 (Address Book)
  - "DOCO" → returns any table with an order number column
  - "inventory" → returns F4101, F41021`,
      inputSchema: JdeDictionarySearchSchema,
      annotations: {
        readOnlyHint: true,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: false,
      },
    },
    async (params: JdeDictionarySearchInput) => {
      try {
        const results = await searchDictionary(params.keyword);

        if (results.length === 0) {
          return {
            content: [{
              type: "text" as const,
              text: `No tables found matching "${params.keyword}". Try a broader term like "sales", "inventory", or "customer".`,
            }],
          };
        }

        const output = results.map((t) => ({
          tableName: t.tableName,
          displayName: t.displayName,
          description: t.description,
          functionalArea: t.functionalArea,
          columns: t.columns,
        }));

        return {
          content: [{
            type: "text" as const,
            text: JSON.stringify(output, null, 2),
          }],
        };
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        return {
          isError: true,
          content: [{ type: "text" as const, text: `Error searching dictionary: ${msg}` }],
        };
      }
    }
  );

  // ── List all tables ─────────────────────────────────────────
  server.registerTool(
    "jde_dictionary_list",
    {
      title: "List All JDE Tables",
      description: `List all JDE tables available in the curated data dictionary.

Returns a summary of every table: table name, display name, and functional area. Use this to get an overview of what data is available before querying.

Args: none

Returns:
  JSON array of { tableName, displayName, functionalArea }`,
      inputSchema: JdeDictionaryListSchema,
      annotations: {
        readOnlyHint: true,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: false,
      },
    },
    async () => {
      try {
        const tables = await listTables();
        return {
          content: [{
            type: "text" as const,
            text: JSON.stringify(tables, null, 2),
          }],
        };
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        return {
          isError: true,
          content: [{ type: "text" as const, text: `Error listing tables: ${msg}` }],
        };
      }
    }
  );

  // ── Get table details ───────────────────────────────────────
  server.registerTool(
    "jde_dictionary_table",
    {
      title: "Get JDE Table Details",
      description: `Get the full column definitions for a specific JDE table.

Use when you already know the table name and need to see all available columns with their JDE aliases, descriptions, and data types before building a query.

Args:
  - tableName (string): JDE table name, e.g. "F4211"

Returns:
  Full table definition with all columns, or error if table not found.`,
      inputSchema: JdeDictionaryTableSchema,
      annotations: {
        readOnlyHint: true,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: false,
      },
    },
    async (params: { tableName: string }) => {
      try {
        const table = await getTable(params.tableName);

        if (!table) {
          return {
            isError: true,
            content: [{
              type: "text" as const,
              text: `Table "${params.tableName}" not found in the dictionary. Use jde_dictionary_search to find the right table name.`,
            }],
          };
        }

        return {
          content: [{
            type: "text" as const,
            text: JSON.stringify(table, null, 2),
          }],
        };
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        return {
          isError: true,
          content: [{ type: "text" as const, text: `Error getting table: ${msg}` }],
        };
      }
    }
  );
}
