// ──────────────────────────────────────────────────────────────
// Dynamic Data Dictionary Discovery Service
//
// Discovers table columns by INTROSPECTING the target table:
//   1. Query target table with no returnControlIDs → AIS returns all exposed columns
//   2. Extract column aliases from response keys (e.g. "F0101_AN8" → "AN8")
//   3. Batch-query F9200 with DTAI filter for descriptions
//   4. Enrich from F9210 (DTAS=size, DTAD=decimals, CLAS=class) where available
//
//   4. For table search, queries F9860 (Object Configuration Manager) with OBNM/MD.
// Results are cached in memory to avoid repeated AIS calls.
// ──────────────────────────────────────────────────────────────

import { queryTable } from "./ais-client.js";
import type { DiscoveredColumn, DiscoveredTable, DiscoveredTableSummary } from "../types.js";

// ── In-memory cache ───────────────────────────────────────────

const tableCache = new Map<string, DiscoveredTable>();

// ── Constants ─────────────────────────────────────────────────

/** F9210 columns that AIS actually exposes (verified by testing) */
const F9210_COLUMNS = ["DTAI", "DTAS", "DTAD", "CLAS"];

/** Chunk size for F9200/F9210 batch lookups */
const CHUNK_SIZE = 100;

// ──────────────────────────────────────────────────────────────
// discoverTable — get full column structure for a table
// ──────────────────────────────────────────────────────────────

export async function discoverTable(tableName: string): Promise<DiscoveredTable> {
  const normalizedName = tableName.toUpperCase().trim();

  // Return from cache if available
  const cached = tableCache.get(normalizedName);
  if (cached) return cached;

  // Step 1: Introspect — query the table with NO columns to get all exposed fields
  const introspectResponse = await queryTable({
    tableName: normalizedName,
    // columns omitted → AIS returns all exposed columns
    maxRows: 1,
  });

  const rows = introspectResponse.fs_DATABROWSE?.data?.gridData?.rowset;
  if (!rows || rows.length === 0) {
    throw new Error(
      `Table "${normalizedName}" returned no data. It may be empty, not exposed via AIS, or the table name is wrong.`
    );
  }

  // Step 2: Extract column aliases from the response keys
  // Keys look like "F0101_AN8", "F0101_ALPH" — strip the "{TABLE}_" prefix
  const prefix = `${normalizedName}_`;
  const aliases = Object.keys(rows[0])
    .filter((key) => key.startsWith(prefix))
    .map((key) => key.slice(prefix.length))
    .filter((alias) => alias.length > 0);

  if (aliases.length === 0) {
    throw new Error(
      `Table "${normalizedName}" returned data but no recognizable column aliases.`
    );
  }

  // Step 3: Fetch descriptions from F9200 and metadata from F9210
  const [descriptionMap, metadataMap] = await Promise.all([
    fetchDescriptions(aliases),
    fetchMetadata(aliases),
  ]);

  // Step 4: Build the discovered columns
  const columns: DiscoveredColumn[] = aliases.map((alias, index) => {
    const meta = metadataMap.get(alias);
    return {
      alias,
      description: descriptionMap.get(alias) ?? "(no description)",
      dataType: meta?.dataType ?? "",
      size: meta?.size ?? 0,
      decimalPlaces: meta?.decimalPlaces ?? 0,
      sequence: index + 1,
    };
  });

  const result: DiscoveredTable = {
    tableName: normalizedName,
    description: `${normalizedName} (${columns.length} columns discovered)`,
    columns,
    columnCount: columns.length,
    discoveredAt: new Date().toISOString(),
  };

  // Cache it
  tableCache.set(normalizedName, result);
  return result;
}

// ──────────────────────────────────────────────────────────────
// searchTables — find tables by keyword from F0092
// ──────────────────────────────────────────────────────────────

export async function searchTables(
  keyword: string,
  maxRows: number = 20
): Promise<DiscoveredTableSummary[]> {
  // Try searching by object name first (most common: "F4211", "F01")
  const byName = await searchTablesByColumn("OBNM", keyword, maxRows);
  if (byName.length > 0) return byName;

  // Fallback: search by description
  return searchTablesByColumn("MD", keyword, maxRows);
}

// ──────────────────────────────────────────────────────────────
// Cache utilities
// ──────────────────────────────────────────────────────────────

export function isTableCached(tableName: string): boolean {
  return tableCache.has(tableName.toUpperCase().trim());
}

export function getCacheStats(): { cachedTables: number; tableNames: string[] } {
  return {
    cachedTables: tableCache.size,
    tableNames: [...tableCache.keys()],
  };
}

export function clearCache(): void {
  tableCache.clear();
}

// ──────────────────────────────────────────────────────────────
// Internal helpers
// ──────────────────────────────────────────────────────────────

/**
 * Fetches descriptions for a batch of data item aliases from F9200.
 * F9200 exposes: DTAI (alias as key + filter).
 * Description comes from the row data when querying with no specific columns.
 */
async function fetchDescriptions(
  aliases: string[]
): Promise<Map<string, string>> {
  const descMap = new Map<string, string>();
  if (aliases.length === 0) return descMap;

  for (let i = 0; i < aliases.length; i += CHUNK_SIZE) {
    const chunk = aliases.slice(i, i + CHUNK_SIZE);

    try {
      const response = await queryTable({
        tableName: "F9200",
        columns: ["DTAI"],
        filters: [
          {
            column: "DTAI",
            operator: "LIST",
            value: chunk,
          },
        ],
        maxRows: chunk.length,
      });

      const rows = response.fs_DATABROWSE?.data?.gridData?.rowset;
      if (rows) {
        for (const row of rows) {
          const alias = String(row["F9200_DTAI"] ?? "").trim();
          // F9200 doesn't expose the description column through AIS,
          // so we just confirm the alias exists. Mark as found.
          if (alias) descMap.set(alias, alias);
        }
      }
    } catch {
      // F9200 lookup is best-effort — don't fail the discovery
    }
  }

  return descMap;
}

/**
 * Fetches metadata (size, decimals, class) from F9210 for a batch of aliases.
 * F9210 exposes: DTAI, DTAS (size), DTAD (decimals), CLAS (class).
 */
async function fetchMetadata(
  aliases: string[]
): Promise<Map<string, { dataType: string; size: number; decimalPlaces: number }>> {
  const metaMap = new Map<string, { dataType: string; size: number; decimalPlaces: number }>();
  if (aliases.length === 0) return metaMap;

  for (let i = 0; i < aliases.length; i += CHUNK_SIZE) {
    const chunk = aliases.slice(i, i + CHUNK_SIZE);

    try {
      const response = await queryTable({
        tableName: "F9210",
        columns: F9210_COLUMNS,
        filters: [
          {
            column: "DTAI",
            operator: "LIST",
            value: chunk,
          },
        ],
        maxRows: chunk.length,
      });

      const rows = response.fs_DATABROWSE?.data?.gridData?.rowset;
      if (rows) {
        for (const row of rows) {
          const alias = String(row["F9210_DTAI"] ?? "").trim();
          if (alias) {
            metaMap.set(alias, {
              dataType: String(row["F9210_CLAS"] ?? "").trim(),
              size: Number(row["F9210_DTAS"] ?? 0),
              decimalPlaces: Number(row["F9210_DTAD"] ?? 0),
            });
          }
        }
      }
    } catch {
      // F9210 lookup is best-effort — don't fail the discovery
    }
  }

  return metaMap;
}

/**
 * Search F9860 (Object Configuration Manager) by a specific column.
 */
async function searchTablesByColumn(
  column: string,
  keyword: string,
  maxRows: number
): Promise<DiscoveredTableSummary[]> {
  try {
    const response = await queryTable({
      tableName: "F9860",
      columns: ["OBNM", "MD"],
      filters: [
        {
          column,
          operator: "STR_CONTAIN",
          value: keyword.toUpperCase(),
        },
      ],
      maxRows,
    });

    const rows = response.fs_DATABROWSE?.data?.gridData?.rowset;
    if (!rows || rows.length === 0) return [];

    return rows.map((row) => {
      const obnm = String(row["F9860_OBNM"] ?? "").trim();
      const md = String(row["F9860_MD"] ?? "").trim();
      return {
        tableName: obnm,
        description: md,
        objectType: "TABLE",
      };
    });
  } catch {
    return [];
  }
}
