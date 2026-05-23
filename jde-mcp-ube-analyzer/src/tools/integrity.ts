import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import {
  JdeApVoucherQuerySchema,
  JdeGlBalanceQuerySchema,
  JdeGlDetailQuerySchema,
  JdeApGlIntegrityCheckSchema,
  type JdeApVoucherQueryInput,
  type JdeGlBalanceQueryInput,
  type JdeGlDetailQueryInput,
  type JdeApGlIntegrityCheckInput,
} from "../schemas/tools.js";
import { queryTable } from "../services/ais-client.js";
import { CHARACTER_LIMIT } from "../constants.js";
import type { AisOperator } from "../types.js";

// ──────────────────────────────────────────────────────────────
// Helpers (same pattern as domain.ts)
// ──────────────────────────────────────────────────────────────

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
// Tool 1: A/P Voucher Query (F0411)
// ──────────────────────────────────────────────────────────────

export function registerApVoucherQuery(server: McpServer): void {
  server.registerTool(
    "jde_ap_voucher_query",
    {
      title: "Query A/P Vouchers",
      description: `Query the JDE Accounts Payable Ledger (F0411) for voucher pay items.

Use this to look up AP vouchers filtered by company, supplier, GL offset code (GLPT),
payment status, date range, fiscal year, and period. Essential for R047001A integrity analysis.

Key columns returned: DOC, DCT, KCO, SFX, CO, AN8, MCU, AG (gross), AAP (open), PAAP (original),
GLPT (GL offset), AID, FY, PN, DGJ, PST, VINV.

The GLPT (GL Offset) field is critical — it determines which GL offset account the voucher posts to,
and is the primary grouping key for the R047001A integrity report.

Args:
  - company: Company code (CO)
  - supplierNumber: Supplier address book number (AN8)
  - documentType: Document type (DCT), e.g. 'PV'
  - payStatus: Payment status (PST): A=Approved, P=Paid, V=Void
  - glOffset: GL posting code (GLPT) — the key R047001A grouping field
  - dateFrom/dateTo: GL date range (YYYY-MM-DD)
  - fiscalYear: Fiscal year (FY)
  - period: GL period (PN)
  - maxRows: Max rows (default 100)`,
      inputSchema: JdeApVoucherQuerySchema,
      annotations: {
        readOnlyHint: true,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: true,
      },
    },
    async (params: JdeApVoucherQueryInput) => {
      try {
        const filters: FilterDef[] = [];
        addFilter(filters, "CO", "EQUAL", params.company);
        addFilter(filters, "AN8", "EQUAL", params.supplierNumber);
        addFilter(filters, "DCT", "EQUAL", params.documentType);
        addFilter(filters, "PST", "EQUAL", params.payStatus);
        addFilter(filters, "GLPT", "EQUAL", params.glOffset);
        addFilter(filters, "FY", "EQUAL", params.fiscalYear);
        addFilter(filters, "PN", "EQUAL", params.period);
        if (params.dateFrom) addFilter(filters, "DGJ", "GREATER_EQUAL", params.dateFrom);
        if (params.dateTo) addFilter(filters, "DGJ", "LESS_EQUAL", params.dateTo);

        const response = await queryTable({
          tableName: "F0411",
          columns: ["DOC", "DCT", "KCO", "SFX", "CO", "AN8", "MCU", "AG", "AAP", "PAAP", "GLPT", "AID", "FY", "PN", "DGJ", "PST", "VINV"],
          filters: filters.length > 0 ? filters : undefined,
          maxRows: params.maxRows,
        });

        const gridData = response.fs_DATABROWSE?.data?.gridData;
        if (!gridData) {
          return {
            content: [{ type: "text" as const, text: "No vouchers found matching the criteria." }],
          };
        }

        const output = {
          tableName: "F0411",
          description: "A/P Voucher Pay Items",
          totalRecords: gridData.summary.records,
          returnedRecords: gridData.rowset.length,
          hasMore: gridData.summary.moreRecords,
          rows: gridData.rowset,
        };

        return {
          content: [{ type: "text" as const, text: truncate(JSON.stringify(output, null, 2), gridData.summary.records) }],
        };
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        return {
          isError: true,
          content: [{ type: "text" as const, text: `Error querying F0411: ${msg}` }],
        };
      }
    }
  );
}

// ──────────────────────────────────────────────────────────────
// Tool 2: GL Balance Query (F0902)
// ──────────────────────────────────────────────────────────────

export function registerGlBalanceQuery(server: McpServer): void {
  server.registerTool(
    "jde_gl_balance_query",
    {
      title: "Query GL Account Balances",
      description: `Query the JDE Account Balances table (F0902) for period-level GL balances.

Use this to get the GL side of an integrity check. Returns balances by period for each
account/ledger type/fiscal year combination.

Key columns: AID, CO, MCU, OBJ, SUB, LT, FY, CTRY, AN01-AN14 (period amounts), BORG (beginning balance).

For R047001A: query by the object account that corresponds to the GLPT offset, then compare
the period totals against the F0411 voucher sums for the same period/company.

Args:
  - company: Company code (CO)
  - businessUnit: Business unit (MCU)
  - objectAccount: Object account (OBJ), e.g. '1110' for AP Trade
  - subsidiary: Subsidiary (SUB) for detail-level
  - ledgerType: Ledger type (default 'AA' = Actual)
  - fiscalYear: Fiscal year (FY)
  - maxRows: Max rows (default 100)`,
      inputSchema: JdeGlBalanceQuerySchema,
      annotations: {
        readOnlyHint: true,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: true,
      },
    },
    async (params: JdeGlBalanceQueryInput) => {
      try {
        const filters: FilterDef[] = [];
        addFilter(filters, "CO", "EQUAL", params.company);
        addFilter(filters, "MCU", "EQUAL", params.businessUnit);
        addFilter(filters, "OBJ", "EQUAL", params.objectAccount);
        addFilter(filters, "SUB", "EQUAL", params.subsidiary);
        addFilter(filters, "LT", "EQUAL", params.ledgerType);
        addFilter(filters, "FY", "EQUAL", params.fiscalYear);

        const response = await queryTable({
          tableName: "F0902",
          columns: ["AID", "CO", "MCU", "OBJ", "SUB", "LT", "FY", "CTRY",
                     "AN01", "AN02", "AN03", "AN04", "AN05", "AN06",
                     "AN07", "AN08", "AN09", "AN10", "AN11", "AN12",
                     "AN13", "AN14", "BORG"],
          filters: filters.length > 0 ? filters : undefined,
          maxRows: params.maxRows,
        });

        const gridData = response.fs_DATABROWSE?.data?.gridData;
        if (!gridData) {
          return {
            content: [{ type: "text" as const, text: "No account balances found matching the criteria." }],
          };
        }

        const output = {
          tableName: "F0902",
          description: "Account Balances by Period",
          totalRecords: gridData.summary.records,
          returnedRecords: gridData.rowset.length,
          hasMore: gridData.summary.moreRecords,
          rows: gridData.rowset,
        };

        return {
          content: [{ type: "text" as const, text: truncate(JSON.stringify(output, null, 2), gridData.summary.records) }],
        };
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        return {
          isError: true,
          content: [{ type: "text" as const, text: `Error querying F0902: ${msg}` }],
        };
      }
    }
  );
}

// ──────────────────────────────────────────────────────────────
// Tool 3: GL Detail / Journal Entry Query (F0901)
// ──────────────────────────────────────────────────────────────

export function registerGlDetailQuery(server: McpServer): void {
  server.registerTool(
    "jde_gl_detail_query",
    {
      title: "Query GL Journal Entries",
      description: `Query the JDE Account Ledger (F0901) for individual GL journal entries.

Use this for drill-down when an integrity discrepancy is found. Shows the individual
transactions that make up the GL balance for a specific account.

Key columns: AID, DOC, DCT, KCO, CO, MCU, LT, FY, PN, AA (amount), DGJ, EXR, AN8, JELN.

Args:
  - accountId: Account ID (AID), e.g. '00001.1110.ACME'
  - company: Company code (CO)
  - documentType: Document type (DCT)
  - fiscalYear: Fiscal year (FY)
  - period: GL period (PN)
  - dateFrom/dateTo: GL date range
  - maxRows: Max rows (default 100)`,
      inputSchema: JdeGlDetailQuerySchema,
      annotations: {
        readOnlyHint: true,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: true,
      },
    },
    async (params: JdeGlDetailQueryInput) => {
      try {
        const filters: FilterDef[] = [];
        addFilter(filters, "AID", "EQUAL", params.accountId);
        addFilter(filters, "CO", "EQUAL", params.company);
        addFilter(filters, "DCT", "EQUAL", params.documentType);
        addFilter(filters, "FY", "EQUAL", params.fiscalYear);
        addFilter(filters, "PN", "EQUAL", params.period);
        if (params.dateFrom) addFilter(filters, "DGJ", "GREATER_EQUAL", params.dateFrom);
        if (params.dateTo) addFilter(filters, "DGJ", "LESS_EQUAL", params.dateTo);

        const response = await queryTable({
          tableName: "F0901",
          columns: ["AID", "DOC", "DCT", "KCO", "CO", "MCU", "LT", "FY", "PN", "AA", "DGJ", "EXR", "AN8", "JELN"],
          filters: filters.length > 0 ? filters : undefined,
          maxRows: params.maxRows,
        });

        const gridData = response.fs_DATABROWSE?.data?.gridData;
        if (!gridData) {
          return {
            content: [{ type: "text" as const, text: "No journal entries found matching the criteria." }],
          };
        }

        const output = {
          tableName: "F0901",
          description: "GL Journal Entry Detail",
          totalRecords: gridData.summary.records,
          returnedRecords: gridData.rowset.length,
          hasMore: gridData.summary.moreRecords,
          rows: gridData.rowset,
        };

        return {
          content: [{ type: "text" as const, text: truncate(JSON.stringify(output, null, 2), gridData.summary.records) }],
        };
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        return {
          isError: true,
          content: [{ type: "text" as const, text: `Error querying F0901: ${msg}` }],
        };
      }
    }
  );
}

// ──────────────────────────────────────────────────────────────
// Tool 4: A/P to G/L Integrity Check (programmatic R047001A)
// ──────────────────────────────────────────────────────────────

export function registerApGlIntegrityCheck(server: McpServer): void {
  server.registerTool(
    "jde_ap_gl_integrity_check",
    {
      title: "A/P to G/L Integrity Check",
      description: `Perform a programmatic A/P to G/L integrity check — the same logic as JDE report R047001A.

This tool:
1. Queries F0411 (A/P Ledger) and sums voucher amounts grouped by GL offset code (GLPT)
2. Queries F0902 (Account Balances) for the corresponding GL accounts
3. Compares the AP subledger totals against the GL balance for each offset account
4. Returns matches (balanced) and discrepancies (out of balance)

This is the KEY tool for R047001A analysis. Use it to verify whether the PDF report's
findings are consistent with the current state of the JDE data.

Args:
  - company: Company code (CO). Required.
  - fiscalYear: Fiscal year (FY). Required.
  - periodFrom: Starting period (PN). Required.
  - periodTo: Ending period (PN). Required.
  - glOffset: Specific GLPT to check. Omit for ALL offset accounts.

Returns:
  { summary, matches, discrepancies } where each entry shows the GLPT code,
  AP subtotal, GL balance, and the difference.`,
      inputSchema: JdeApGlIntegrityCheckSchema,
      annotations: {
        readOnlyHint: true,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: true,
      },
    },
    async (params: JdeApGlIntegrityCheckInput) => {
      try {
        // ── Step 1: Query F0411 for AP voucher amounts ──
        const apFilters: FilterDef[] = [];
        addFilter(apFilters, "CO", "EQUAL", params.company);
        addFilter(apFilters, "FY", "EQUAL", params.fiscalYear);
        addFilter(apFilters, "PN", "GREATER_EQUAL", params.periodFrom);
        addFilter(apFilters, "PN", "LESS_EQUAL", params.periodTo);
        if (params.glOffset) addFilter(apFilters, "GLPT", "EQUAL", params.glOffset);

        const apResponse = await queryTable({
          tableName: "F0411",
          columns: ["GLPT", "AG", "AAP", "CO", "FY", "PN", "AID"],
          filters: apFilters,
          maxRows: 500,
        });

        const apRows = apResponse.fs_DATABROWSE?.data?.gridData?.rowset ?? [];

        // Group AP amounts by GLPT
        const apByGlpt: Record<string, { gross: number; open: number; count: number; aids: Set<string> }> = {};
        for (const row of apRows) {
          const glpt = String(row["F0411_GLPT"] ?? row["GLPT"] ?? "UNKNOWN");
          const gross = Number(row["F0411_AG"] ?? row["AG"] ?? 0);
          const open = Number(row["F0411_AAP"] ?? row["AAP"] ?? 0);
          const aid = String(row["F0411_AID"] ?? row["AID"] ?? "");

          if (!apByGlpt[glpt]) {
            apByGlpt[glpt] = { gross: 0, open: 0, count: 0, aids: new Set() };
          }
          apByGlpt[glpt].gross += gross;
          apByGlpt[glpt].open += open;
          apByGlpt[glpt].count += 1;
          if (aid) apByGlpt[glpt].aids.add(aid);
        }

        // ── Step 2: Query F0902 for GL balances ──
        const glFilters: FilterDef[] = [];
        addFilter(glFilters, "CO", "EQUAL", params.company);
        addFilter(glFilters, "LT", "EQUAL", "AA");
        addFilter(glFilters, "FY", "EQUAL", params.fiscalYear);

        const glResponse = await queryTable({
          tableName: "F0902",
          columns: ["AID", "CO", "OBJ", "SUB", "FY",
                     "AN01", "AN02", "AN03", "AN04", "AN05", "AN06",
                     "AN07", "AN08", "AN09", "AN10", "AN11", "AN12",
                     "AN13", "AN14", "BORG"],
          filters: glFilters,
          maxRows: 500,
        });

        const glRows = glResponse.fs_DATABROWSE?.data?.gridData?.rowset ?? [];

        // Build a map of AID → sum of period amounts for requested range
        const glByAid: Record<string, number> = {};
        for (const row of glRows) {
          const aid = String(row["F0902_AID"] ?? row["AID"] ?? "");
          let periodSum = 0;
          for (let p = params.periodFrom; p <= params.periodTo; p++) {
            const key = `AN${String(p).padStart(2, "0")}`;
            const prefixedKey = `F0902_${key}`;
            periodSum += Number(row[prefixedKey] ?? row[key] ?? 0);
          }
          glByAid[aid] = (glByAid[aid] ?? 0) + periodSum;
        }

        // ── Step 3: Compare AP vs GL ──
        const matches: Array<Record<string, unknown>> = [];
        const discrepancies: Array<Record<string, unknown>> = [];

        for (const [glpt, ap] of Object.entries(apByGlpt)) {
          // Find GL balance for any AID referenced by this GLPT group
          let glTotal = 0;
          const matchedAids: string[] = [];
          for (const aid of ap.aids) {
            if (glByAid[aid] !== undefined) {
              glTotal += glByAid[aid];
              matchedAids.push(aid);
            }
          }

          const difference = Math.round((ap.gross - glTotal) * 100) / 100;
          const entry = {
            glOffset: glpt,
            apGrossTotal: Math.round(ap.gross * 100) / 100,
            apOpenTotal: Math.round(ap.open * 100) / 100,
            glPeriodTotal: Math.round(glTotal * 100) / 100,
            difference,
            voucherCount: ap.count,
            matchedAccountIds: matchedAids,
          };

          if (Math.abs(difference) < 0.01) {
            matches.push(entry);
          } else {
            discrepancies.push(entry);
          }
        }

        const output = {
          reportName: "A/P to G/L Integrity Check (R047001A)",
          company: params.company,
          fiscalYear: params.fiscalYear,
          periodRange: `${params.periodFrom}-${params.periodTo}`,
          glOffsetFilter: params.glOffset ?? "ALL",
          apVouchersAnalyzed: apRows.length,
          glAccountsAnalyzed: glRows.length,
          summary: {
            totalOffsetGroups: Object.keys(apByGlpt).length,
            balanced: matches.length,
            discrepancies: discrepancies.length,
          },
          discrepancies,
          matches,
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
            text: `Error running integrity check: ${msg}. Verify company '${params.company}' and fiscal year ${params.fiscalYear} exist in F0411.`,
          }],
        };
      }
    }
  );
}
