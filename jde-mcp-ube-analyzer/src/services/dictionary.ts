import { readFile } from "fs/promises";
import { fileURLToPath } from "url";
import { dirname, join } from "path";
import type { DataDictionary, TableDef } from "../types.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// ──────────────────────────────────────────────────────────────
// In-memory cache
// ──────────────────────────────────────────────────────────────

let dictionary: DataDictionary | null = null;

// ──────────────────────────────────────────────────────────────
// Load
// ──────────────────────────────────────────────────────────────

/**
 * Load the curated dictionary from disk into memory.
 * Call once at server startup (index.ts).
 */
export async function loadDictionary(): Promise<void> {
  const dictPath = join(__dirname, "..", "data", "dictionary.json");
  const raw = await readFile(dictPath, "utf-8");
  dictionary = JSON.parse(raw) as DataDictionary;
  console.error(
    `Dictionary loaded: v${dictionary.version} — ${dictionary.tables.length} tables`
  );
}

function ensureLoaded(): DataDictionary {
  if (!dictionary) {
    throw new Error("Dictionary not loaded. Call loadDictionary() at startup.");
  }
  return dictionary;
}

// ──────────────────────────────────────────────────────────────
// Service functions (used by tool handlers)
// ──────────────────────────────────────────────────────────────

/**
 * Search for tables/columns matching a keyword.
 * Matches against table names, display names, descriptions,
 * functional areas, and column aliases/names/descriptions.
 */
export async function searchDictionary(keyword: string): Promise<TableDef[]> {
  const dict = ensureLoaded();
  const term = keyword.toLowerCase();

  return dict.tables.filter((table) => {
    // Match on table-level fields
    if (
      table.tableName.toLowerCase().includes(term) ||
      table.displayName.toLowerCase().includes(term) ||
      table.description.toLowerCase().includes(term) ||
      table.functionalArea.toLowerCase().includes(term)
    ) {
      return true;
    }

    // Match on any column
    return table.columns.some(
      (col) =>
        col.alias.toLowerCase().includes(term) ||
        col.name.toLowerCase().includes(term) ||
        col.description.toLowerCase().includes(term)
    );
  });
}

/**
 * List all tables in summary form.
 */
export async function listTables(): Promise<
  Array<{ tableName: string; displayName: string; functionalArea: string }>
> {
  const dict = ensureLoaded();
  return dict.tables.map((t) => ({
    tableName: t.tableName,
    displayName: t.displayName,
    functionalArea: t.functionalArea,
  }));
}

/**
 * Get full details for a specific table by name.
 * Returns null if not found.
 */
export async function getTable(tableName: string): Promise<TableDef | null> {
  const dict = ensureLoaded();
  return (
    dict.tables.find(
      (t) => t.tableName.toUpperCase() === tableName.toUpperCase()
    ) ?? null
  );
}

/**
 * Validate column aliases against the dictionary for a given table.
 * Returns which columns are known (valid) and which are not (invalid).
 * Unknown columns are not blocked — they may exist in JDE but not in
 * the curated dictionary.
 */
export async function resolveColumns(
  tableName: string,
  columns: string[]
): Promise<{ valid: string[]; invalid: string[] }> {
  const dict = ensureLoaded();
  const table = dict.tables.find(
    (t) => t.tableName.toUpperCase() === tableName.toUpperCase()
  );

  if (!table) {
    // Table not in dictionary — can't validate, treat all as valid
    return { valid: columns, invalid: [] };
  }

  const knownAliases = new Set(
    table.columns.map((c) => c.alias.toUpperCase())
  );

  const valid: string[] = [];
  const invalid: string[] = [];

  for (const col of columns) {
    if (knownAliases.has(col.toUpperCase())) {
      valid.push(col);
    } else {
      invalid.push(col);
    }
  }

  return { valid, invalid };
}
