// ──────────────────────────────────────────────────────────────
// JDE AIS Types
// ──────────────────────────────────────────────────────────────

/** AIS Data Service request body */
export interface AisDataRequest {
  targetType: "table" | "view";
  targetName: string;
  dataServiceType: "BROWSE";
  returnControlIDs?: string;       // pipe-delimited column aliases; omit for all
  query?: AisQuery;
  maxPageSize?: string;
  findOnEntry: "TRUE" | "FALSE";
  environment?: string;
  role?: string;
}

/** AIS query filter */
export interface AisQuery {
  autoFind: boolean;
  condition: AisCondition[];
}

export interface AisCondition {
  value: Array<{
    content: string;
    specialValueId: string;
  }>;
  controlId: string;
  operator: AisOperator;
}

export type AisOperator =
  | "EQUAL"
  | "NOT_EQUAL"
  | "LESS"
  | "LESS_EQUAL"
  | "GREATER"
  | "GREATER_EQUAL"
  | "BETWEEN"
  | "LIST"
  | "STR_CONTAIN"
  | "STR_START_WITH"
  | "STR_END_WITH"
  | "STR_BLANK"
  | "STR_NOT_BLANK";

/** AIS Data Service response */
export interface AisDataResponse {
  fs_DATABROWSE: {
    title: string;
    data: {
      gridData: {
        id: number;
        columns: Record<string, string>;
        rowset: Array<Record<string, unknown>>;
        summary: {
          records: number;
          moreRecords: boolean;
        };
      };
    };
  };
}

/** AIS Form Service request body */
export interface AisFormRequest {
  formName: string;
  version: string;
  formServiceAction: string;
  maxPageSize?: string;
  returnControlIDs?: string;
  query?: AisQuery;
  formInputs?: Array<{
    id: string;
    value: string;
  }>;
  environment?: string;
  role?: string;
}

/** AIS Orchestration request body */
export interface AisOrchestrationRequest {
  [key: string]: unknown;       // orchestration-specific inputs
}

// ──────────────────────────────────────────────────────────────
// Data Dictionary Types
// ──────────────────────────────────────────────────────────────

/** A column definition in the curated data dictionary */
export interface ColumnDef {
  alias: string;          // JDE alias (e.g. "DOCO")
  name: string;           // Human-friendly name (e.g. "Order Number")
  description: string;    // What this column represents
  dataType: "string" | "number" | "date";
  example?: string;       // Example value for Claude
}

/** A table definition in the curated data dictionary */
export interface TableDef {
  tableName: string;      // e.g. "F4211"
  displayName: string;    // e.g. "Sales Order Detail"
  description: string;    // What this table contains
  functionalArea: string; // e.g. "Sales Orders", "Inventory", "Accounts"
  columns: ColumnDef[];
}

/** The full curated dictionary */
export interface DataDictionary {
  version: string;
  lastUpdated: string;
  tables: TableDef[];
}

// ──────────────────────────────────────────────────────────────
// Tool Response Types
// ──────────────────────────────────────────────────────────────

export interface PaginatedResult {
  totalRecords: number;
  returnedRecords: number;
  hasMore: boolean;
  rows: Array<Record<string, unknown>>;
}

export interface DictionarySearchResult {
  matchedTables: Array<{
    tableName: string;
    displayName: string;
    description: string;
    functionalArea: string;
    columns: ColumnDef[];
  }>;
}

// ──────────────────────────────────────────────────────────────
// Dynamic Discovery Types (Layer 0 — live from JDE system tables)
// ──────────────────────────────────────────────────────────────

/** A column discovered live from F9210 + F9200 */
export interface DiscoveredColumn {
  alias: string;          // JDE data item alias (e.g. "DOCO")
  description: string;    // Human-readable description from F9200
  dataType: string;       // JDE data type code (e.g. "2"=string, "7"=MATH_NUMERIC)
  size: number;           // Field size from F9210
  decimalPlaces: number;  // Decimal positions
  sequence: number;       // Column order in the table
}

/** Full table structure discovered live */
export interface DiscoveredTable {
  tableName: string;           // e.g. "F4211"
  description: string;         // From F9210 or F0092
  columns: DiscoveredColumn[];
  columnCount: number;
  discoveredAt: string;        // ISO timestamp of when this was cached
}

/** Lightweight table summary from F0092 search */
export interface DiscoveredTableSummary {
  tableName: string;      // e.g. "F4211"
  description: string;    // Object description
  objectType: string;     // "TBLE", "VIEW", etc.
}
