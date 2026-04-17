import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import {
  JdeBatchQuerySchema,
  JdeBatchTransactionQuerySchema,
  JdeUnpostedBatchCheckSchema,
  type JdeBatchQueryInput,
  type JdeBatchTransactionQueryInput,
  type JdeUnpostedBatchCheckInput,
} from "../schemas/tools.js";
import { queryTable } from "../services/ais-client.js";
import { CHARACTER_LIMIT } from "../constants.js";
import type { AisOperator } from "../types.js";

// ──────────────────────────────────────────────────────────────
// Helpers
// ──────────────────────────────────────────────────────────────

/**
 * Convert YYYY-MM-DD to JDE Julian date format (CYYDDD).
 * C = century digit (0=19xx, 1=20xx), YY = 2-digit year, DDD = day of year.
 * Example: 2026-03-09 → 126068
 */
function toJulianDate(dateStr: string): string {
  // Parse as UTC to avoid timezone-related day shifts
  const parts = dateStr.split("-").map(Number);
  if (parts.length !== 3 || parts.some(isNaN)) return dateStr;
  const [year, month, day] = parts;
  const century = Math.floor(year / 100) - 19; // 20xx → 1, 19xx → 0
  const yy = year % 100;
  // Day of year (UTC-safe calculation)
  const d = new Date(Date.UTC(year, month - 1, day));
  const startOfYear = new Date(Date.UTC(year, 0, 1));
  const ddd = Math.floor((d.getTime() - startOfYear.getTime()) / 86400000) + 1;
  return `${century}${String(yy).padStart(2, "0")}${String(ddd).padStart(3, "0")}`;
}

interface FilterDef {
  column: string;
  operator: AisOperator;
  value: string | string[];
}

function addFilter(
  filters: FilterDef[],
  column: string,
  operator: AisOperator,
  value: string | number | undefined
): void {
  if (value === undefined || value === "") return;
  filters.push({ column, operator, value: String(value) });
}

function truncate(text: string, records?: number): string {
  if (text.length <= CHARACTER_LIMIT) return text;
  return (
    text.slice(0, CHARACTER_LIMIT) +
    `\n\n... [TRUNCATED — ${records ?? "many"} total records. Narrow your filters.]`
  );
}

// ──────────────────────────────────────────────────────────────
// Tool 1: Batch Query (F0911 — replaces F0011 which lacks AIS BROWSE spec)
// ──────────────────────────────────────────────────────────────

export function registerBatchQuery(server: McpServer): void {
  server.registerTool(
    "jde_batch_query",
    {
      title: "Query Batch Transactions",
      description: `Query the JDE Account Ledger table (F0911) for batch transaction data.

Use this to look up transactions within batches by company, batch number, batch type,
or date range. Essential for R007011 (Unposted Batches) verification.

Note: F0011 (Batch Control) is not available via AIS Data Service in this environment.
Batch data is retrieved from F0911 which contains the actual GL transactions per batch.

Batch types (ICUT): G=General Ledger, V=Voucher Entry, W=Time Entry, K=Receipts, I=Invoice Entry, M=Manual Payment

Key columns returned: ICU (batch number), ICUT (batch type), DOC (document number),
DCT (document type), KCO (company), AA (amount), DGJ (GL date),
FY (fiscal year), PN (period), EXR (explanation), JELN (journal entry line).`,
      inputSchema: JdeBatchQuerySchema,
      annotations: {
        readOnlyHint: true,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: true,
      },
    },
    async (params: JdeBatchQueryInput) => {
      try {
        const filters: FilterDef[] = [];
        addFilter(filters, "KCO", "EQUAL", params.company);
        addFilter(filters, "ICU", "EQUAL", params.batchNumber);
        addFilter(filters, "ICUT", "EQUAL", params.batchType);
        if (params.dateFrom) addFilter(filters, "DGJ", "GREATER_EQUAL", toJulianDate(params.dateFrom));
        if (params.dateTo) addFilter(filters, "DGJ", "LESS_EQUAL", toJulianDate(params.dateTo));

        const response = await queryTable({
          tableName: "F0911",
          columns: ["ICU", "ICUT", "DOC", "DCT", "KCO", "AA", "DGJ", "FY", "PN", "EXR", "AN8", "JELN"],
          filters: filters.length > 0 ? filters : undefined,
          maxRows: params.maxRows,
        });

        const rows = response.fs_DATABROWSE?.data?.gridData?.rowset ?? [];
        const summary = response.fs_DATABROWSE?.data?.gridData?.summary;

        const output = {
          tableName: "F0911",
          description: "Account Ledger (Batch Transactions)",
          totalRecords: summary?.records ?? rows.length,
          returnedRecords: rows.length,
          hasMore: summary?.moreRecords ?? false,
          rows,
        };

        return {
          content: [{ type: "text" as const, text: truncate(JSON.stringify(output, null, 2), summary?.records) }],
        };
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        return {
          isError: true,
          content: [{ type: "text" as const, text: `Error querying F0911 batch data: ${msg}` }],
        };
      }
    }
  );
}

// ──────────────────────────────────────────────────────────────
// Tool 2: Batch Transaction Query (F0911)
// ──────────────────────────────────────────────────────────────

export function registerBatchTransactionQuery(server: McpServer): void {
  server.registerTool(
    "jde_batch_transaction_query",
    {
      title: "Query Batch Transactions",
      description: `Query the JDE Account Ledger table (F0911) for journal entry transactions within batches.

Use this to look up individual GL transactions by batch number, batch type, company,
document number, fiscal year, or period. Shows the detail behind each batch.

Key columns returned: ICU (batch number), ICUT (batch type), DOC (document number),
DCT (document type), KCO (company), AID (account ID), AA (amount), DGJ (GL date),
FY (fiscal year), PN (period), EXR (explanation), AN8 (address number), JELN (line number).`,
      inputSchema: JdeBatchTransactionQuerySchema,
      annotations: {
        readOnlyHint: true,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: true,
      },
    },
    async (params: JdeBatchTransactionQueryInput) => {
      try {
        const filters: FilterDef[] = [];
        addFilter(filters, "ICU", "EQUAL", params.batchNumber);
        addFilter(filters, "ICUT", "EQUAL", params.batchType);
        addFilter(filters, "KCO", "EQUAL", params.company);
        addFilter(filters, "DOC", "EQUAL", params.documentNumber);
        addFilter(filters, "FY", "EQUAL", params.fiscalYear);
        addFilter(filters, "PN", "EQUAL", params.period);

        const response = await queryTable({
          tableName: "F0911",
          columns: ["ICU", "ICUT", "DOC", "DCT", "KCO", "CO", "AID", "OBJ", "SUB", "AA", "DGJ", "FY", "PN", "EXR", "AN8", "JELN", "LT"],
          filters: filters.length > 0 ? filters : undefined,
          maxRows: params.maxRows,
        });

        const rows = response.fs_DATABROWSE?.data?.gridData?.rowset ?? [];
        const summary = response.fs_DATABROWSE?.data?.gridData?.summary;

        const output = {
          tableName: "F0911",
          description: "Account Ledger (Batch Transactions)",
          totalRecords: summary?.records ?? rows.length,
          returnedRecords: rows.length,
          hasMore: summary?.moreRecords ?? false,
          rows,
        };

        return {
          content: [{ type: "text" as const, text: truncate(JSON.stringify(output, null, 2), summary?.records) }],
        };
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        return {
          isError: true,
          content: [{ type: "text" as const, text: `Error querying F0911: ${msg}` }],
        };
      }
    }
  );
}

// ──────────────────────────────────────────────────────────────
// Tool 3: Batch Verification Check (R007011 — F0911 only)
// ──────────────────────────────────────────────────────────────

export function registerUnpostedBatchCheck(server: McpServer): void {
  server.registerTool(
    "jde_unposted_batch_check",
    {
      title: "Batch Verification Check (R007011)",
      description: `Verify batch data from an R007011 (Unposted Batches) report against live JDE data.

Queries F0911 (Account Ledger) for batch transactions matching the given filters,
groups results by batch number, and returns a per-batch summary including:
- Transaction count and total amount per batch
- Document types found in each batch
- GL date range per batch

Use this to verify that batches listed in the R007011 PDF actually exist in the GL
and to compare amounts/transaction counts against the report data.

Note: Batch posting status (posted/unposted) is determined from the R007011 PDF itself.
F0011 (Batch Control) is not available via AIS Data Service in this environment.
This tool verifies the underlying transaction DATA behind those batches.

Returns: { summary, batches[] } where each batch has batchNumber, batchType, company,
totalAmount, transactionCount, documentTypes, and dateRange.`,
      inputSchema: JdeUnpostedBatchCheckSchema,
      annotations: {
        readOnlyHint: true,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: true,
      },
    },
    async (params: JdeUnpostedBatchCheckInput) => {
      try {
        // Query F0911 for batch transactions
        const filters: FilterDef[] = [];
        addFilter(filters, "KCO", "EQUAL", params.company);
        if (params.batchType) addFilter(filters, "ICUT", "EQUAL", params.batchType);
        if (params.dateFrom) addFilter(filters, "DGJ", "GREATER_EQUAL", toJulianDate(params.dateFrom));
        if (params.dateTo) addFilter(filters, "DGJ", "LESS_EQUAL", toJulianDate(params.dateTo));

        const response = await queryTable({
          tableName: "F0911",
          columns: ["ICU", "ICUT", "DOC", "DCT", "KCO", "CO", "OBJ", "SUB", "AA", "DGJ", "FY", "PN", "EXR", "AN8", "JELN"],
          filters: filters.length > 0 ? filters : undefined,
          maxRows: params.maxRows ?? 200,
        });

        const rows = response.fs_DATABROWSE?.data?.gridData?.rowset ?? [];

        if (rows.length === 0) {
          const output = {
            reportName: "Batch Verification (R007011)",
            company: params.company ?? "ALL",
            batchTypeFilter: params.batchType ?? "ALL",
            summary: {
              totalBatchesFound: 0,
              totalTransactions: 0,
              totalAmount: 0,
              message: "No batch transactions found matching the filters.",
            },
            batches: [],
          };
          return {
            content: [{ type: "text" as const, text: JSON.stringify(output, null, 2) }],
          };
        }

        // Group by batch number
        const batchMap = new Map<number, {
          batchNumber: number;
          batchType: string;
          company: string;
          totalAmount: number;
          transactionCount: number;
          documentTypes: Set<string>;
          earliest: string;
          latest: string;
        }>();

        for (const row of rows) {
          const batchNum = Number(row["F0911_ICU"] ?? row["ICU"] ?? 0);
          const batchType = String(row["F0911_ICUT"] ?? row["ICUT"] ?? "");
          const company = String(row["F0911_KCO"] ?? row["KCO"] ?? "");
          const amount = Number(row["F0911_AA"] ?? row["AA"] ?? 0);
          const docType = String(row["F0911_DCT"] ?? row["DCT"] ?? "");
          const glDate = String(row["F0911_DGJ"] ?? row["DGJ"] ?? "");

          let batch = batchMap.get(batchNum);
          if (!batch) {
            batch = {
              batchNumber: batchNum,
              batchType,
              company,
              totalAmount: 0,
              transactionCount: 0,
              documentTypes: new Set(),
              earliest: glDate,
              latest: glDate,
            };
            batchMap.set(batchNum, batch);
          }

          batch.totalAmount += amount;
          batch.transactionCount += 1;
          if (docType) batch.documentTypes.add(docType);
          if (glDate && glDate < batch.earliest) batch.earliest = glDate;
          if (glDate && glDate > batch.latest) batch.latest = glDate;
        }

        // Convert to serializable output
        const batches = Array.from(batchMap.values()).map(b => ({
          batchNumber: b.batchNumber,
          batchType: b.batchType,
          company: b.company,
          totalAmount: Math.round(b.totalAmount * 100) / 100,
          transactionCount: b.transactionCount,
          documentTypes: Array.from(b.documentTypes),
          dateRange: { earliest: b.earliest, latest: b.latest },
        }));

        // Summary by batch type
        const byType: Record<string, { count: number; total: number }> = {};
        for (const b of batches) {
          const key = b.batchType || "UNKNOWN";
          if (!byType[key]) byType[key] = { count: 0, total: 0 };
          byType[key].count += 1;
          byType[key].total += b.totalAmount;
        }

        const output = {
          reportName: "Batch Verification (R007011)",
          company: params.company ?? "ALL",
          batchTypeFilter: params.batchType ?? "ALL",
          dateRange: {
            from: params.dateFrom ?? "ALL",
            to: params.dateTo ?? "ALL",
          },
          summary: {
            totalBatchesFound: batches.length,
            totalTransactions: rows.length,
            totalAmount: Math.round(batches.reduce((s, b) => s + b.totalAmount, 0) * 100) / 100,
            byBatchType: byType,
          },
          batches,
        };

        return {
          content: [{ type: "text" as const, text: truncate(JSON.stringify(output, null, 2)) }],
        };
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        return {
          isError: true,
          content: [{
            type: "text" as const,
            text: `Error running batch verification: ${msg}`,
          }],
        };
      }
    }
  );
}
