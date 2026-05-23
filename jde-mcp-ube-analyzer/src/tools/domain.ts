import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import {
  JdeSalesOrderInquirySchema,
  JdeCreateSalesOrderSchema,
  JdeUpdateSalesOrderSchema,
  JdeAddSalesOrderLineSchema,
  JdeCancelSalesOrderSchema,
  JdeCustomerLookupSchema,
  JdeItemCheckSchema,
  type JdeSalesOrderInquiryInput,
  type JdeCreateSalesOrderInput,
  type JdeUpdateSalesOrderInput,
  type JdeAddSalesOrderLineInput,
  type JdeCancelSalesOrderInput,
  type JdeCustomerLookupInput,
  type JdeItemCheckInput,
} from "../schemas/tools.js";
import { queryTable, callOrchestration } from "../services/ais-client.js";
import { buildOrchestrationPayload } from "../services/orch-mapper.js";
import { CHARACTER_LIMIT } from "../constants.js";
import type { AisOperator } from "../types.js";

// ──────────────────────────────────────────────────────────────
// Helpers
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
    `\n\n... [TRUNCATED — ${records ?? "many"} total records. Narrow your criteria.]`
  );
}

function formatQueryResult(
  label: string,
  tableName: string,
  gridData: {
    summary: { records: number; moreRecords: boolean };
    rowset: Array<Record<string, unknown>>;
  }
): { content: Array<{ type: "text"; text: string }> } {
  const output = {
    label,
    tableName,
    totalRecords: gridData.summary.records,
    returnedRecords: gridData.rowset.length,
    hasMore: gridData.summary.moreRecords,
    rows: gridData.rowset,
  };
  return {
    content: [
      { type: "text" as const, text: truncate(JSON.stringify(output, null, 2), gridData.summary.records) },
    ],
  };
}

function orchResult(data: unknown): { content: Array<{ type: "text"; text: string }> } {
  return {
    content: [{ type: "text" as const, text: truncate(JSON.stringify(data, null, 2)) }],
  };
}

function orchError(operation: string, err: unknown): { isError: true; content: Array<{ type: "text"; text: string }> } {
  const msg = err instanceof Error ? err.message : String(err);
  return {
    isError: true,
    content: [{ type: "text" as const, text: `Error in ${operation}: ${msg}` }],
  };
}

// ══════════════════════════════════════════════════════════════
// READ — Sales Order Inquiry
// ══════════════════════════════════════════════════════════════

export function registerSalesOrderInquiry(server: McpServer): void {
  server.registerTool(
    "jde_sales_order_inquiry",
    {
      title: "JDE Sales Order Inquiry",
      description: `Query sales order detail lines (F4211) and optionally the header (F4201).

Use for: "show me order 12345", "what are the open orders for customer 4242",
"find all orders with item ABC123", "what's backordered at branch M30".

All filters are optional — combine them to narrow results.

Common status ranges (NXTR):
  520-540: open, awaiting pick/ship
  560-580: shipped, awaiting invoice
  999: closed/completed

Args:
  - orderNumber, customerNumber, customerName, itemNumber, branchPlant
  - orderType (default SO), statusFrom, statusTo
  - includeHeader: also return F4201 header row
  - maxRows (default 50)`,
      inputSchema: JdeSalesOrderInquirySchema,
      annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true },
    },
    async (params: JdeSalesOrderInquiryInput) => {
      try {
        // If customerName provided, resolve to AN8 first
        let resolvedAN8 = params.customerNumber;
        if (params.customerName && !resolvedAN8) {
          const custResp = await queryTable({
            tableName: "F0101",
            columns: ["AN8", "ALPH"],
            filters: [
              { column: "ALPH", operator: "STR_CONTAIN", value: params.customerName },
              { column: "AT1", operator: "EQUAL", value: "C" },
            ],
            maxRows: 5,
          });
          const custRows = custResp.fs_DATABROWSE?.data?.gridData?.rowset;
          if (custRows && custRows.length > 0) {
            resolvedAN8 = Number(custRows[0]["F0101_AN8"] ?? custRows[0]["AN8"]);
          } else {
            return {
              content: [{
                type: "text" as const,
                text: `No customer found matching "${params.customerName}". Try jde_customer_lookup for more options.`,
              }],
            };
          }
        }

        const filters: FilterDef[] = [];
        addFilter(filters, "DOCO", "EQUAL", params.orderNumber);
        addFilter(filters, "AN8", "EQUAL", resolvedAN8);
        addFilter(filters, "LITM", "STR_CONTAIN", params.itemNumber);
        addFilter(filters, "MCU", "EQUAL", params.branchPlant);
        addFilter(filters, "DCTO", "EQUAL", params.orderType);
        addFilter(filters, "NXTR", "GREATER_EQUAL", params.statusFrom);
        addFilter(filters, "NXTR", "LESS_EQUAL", params.statusTo);

        const detailCols = [
          "DOCO", "DCTO", "KCOO", "LNID", "AN8", "SHAN", "LITM", "DSC1",
          "UORG", "SOQS", "SOBK", "UPRC", "AEXP", "LNTY",
          "NXTR", "LTTR", "MCU", "TRDJ", "DRQJ", "PDDJ",
        ];

        const detailResp = await queryTable({
          tableName: "F4211",
          columns: detailCols,
          filters,
          maxRows: params.maxRows,
        });

        const detailGrid = detailResp.fs_DATABROWSE?.data?.gridData;
        if (!detailGrid || detailGrid.rowset.length === 0) {
          return {
            content: [{ type: "text" as const, text: "No sales order lines found matching the criteria." }],
          };
        }

        // Optionally fetch header
        let headerData: unknown = null;
        if (params.includeHeader && params.orderNumber) {
          const headerResp = await queryTable({
            tableName: "F4201",
            columns: ["DOCO", "DCTO", "KCOO", "AN8", "SHAN", "MCU", "TRDJ", "DRQJ", "PDDJ", "OTOT", "HOLD", "NXTR", "VR01"],
            filters: [{ column: "DOCO", operator: "EQUAL", value: String(params.orderNumber) }],
            maxRows: 1,
          });
          const hGrid = headerResp.fs_DATABROWSE?.data?.gridData;
          if (hGrid && hGrid.rowset.length > 0) {
            headerData = hGrid.rowset[0];
          }
        }

        const output = {
          label: "Sales Order Inquiry",
          ...(headerData ? { header: headerData } : {}),
          detail: {
            tableName: "F4211",
            totalRecords: detailGrid.summary.records,
            returnedRecords: detailGrid.rowset.length,
            hasMore: detailGrid.summary.moreRecords,
            rows: detailGrid.rowset,
          },
        };

        return {
          content: [{ type: "text" as const, text: truncate(JSON.stringify(output, null, 2), detailGrid.summary.records) }],
        };
      } catch (err) {
        return orchError("jde_sales_order_inquiry", err);
      }
    }
  );
}

// ══════════════════════════════════════════════════════════════
// CREATE — New Sales Order
// ══════════════════════════════════════════════════════════════

export function registerCreateSalesOrder(server: McpServer): void {
  server.registerTool(
    "jde_create_sales_order",
    {
      title: "Create JDE Sales Order",
      description: `Create a new sales order in JDE via orchestration (P4210).

This calls the configured "createSalesOrder" orchestration, which drives P4210 to create a header and one or more detail lines. JDE business rules (pricing, availability, credit checks) are enforced by the orchestration.

⚠️ This CREATES data in JDE. Confirm details with the user before calling.

Args:
  - customerNumber (required): Sold-to AN8
  - shipToNumber: Ship-to AN8 (defaults to customerNumber)
  - branchPlant (required): Default branch/plant (MCU)
  - orderType: Default "SO"
  - orderDate, requestedDate, customerPO
  - lines[]: At least one line with itemNumber and quantity

Returns: Orchestration response with the new order number.`,
      inputSchema: JdeCreateSalesOrderSchema,
      annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: true },
    },
    async (params: JdeCreateSalesOrderInput) => {
      try {
        const { orchestrationName, inputs } = await buildOrchestrationPayload(
          "createSalesOrder",
          params as unknown as Record<string, unknown>
        );
        const result = await callOrchestration(orchestrationName, inputs);
        return orchResult(result);
      } catch (err) {
        return orchError("jde_create_sales_order", err);
      }
    }
  );
}

// ══════════════════════════════════════════════════════════════
// UPDATE — Existing Sales Order Line
// ══════════════════════════════════════════════════════════════

export function registerUpdateSalesOrder(server: McpServer): void {
  server.registerTool(
    "jde_update_sales_order",
    {
      title: "Update JDE Sales Order Line",
      description: `Update an existing sales order detail line in JDE via orchestration (P4210 EditLine).

Use to change quantity, price, dates, or branch on a specific line of an existing order.

⚠️ This MODIFIES data in JDE. Confirm changes with the user before calling.

Args:
  - orderNumber (required): DOCO
  - lineNumber (required): LNID (e.g. 1000 = line 1)
  - orderType, orderCompany
  - quantity, unitPrice, requestedDate, promisedDate, branchPlant (all optional — only changed fields)

Returns: Orchestration response confirming the update.`,
      inputSchema: JdeUpdateSalesOrderSchema,
      annotations: { readOnlyHint: false, destructiveHint: true, idempotentHint: true, openWorldHint: true },
    },
    async (params: JdeUpdateSalesOrderInput) => {
      try {
        const { orchestrationName, inputs } = await buildOrchestrationPayload(
          "updateSalesOrderLine",
          params as unknown as Record<string, unknown>
        );
        const result = await callOrchestration(orchestrationName, inputs);
        return orchResult(result);
      } catch (err) {
        return orchError("jde_update_sales_order", err);
      }
    }
  );
}

// ══════════════════════════════════════════════════════════════
// ADD LINE — to Existing Sales Order
// ══════════════════════════════════════════════════════════════

export function registerAddSalesOrderLine(server: McpServer): void {
  server.registerTool(
    "jde_add_sales_order_line",
    {
      title: "Add Lines to JDE Sales Order",
      description: `Add one or more new detail lines to an existing JDE sales order via orchestration.

⚠️ This MODIFIES data in JDE. Confirm with the user before calling.

Args:
  - orderNumber (required): Existing DOCO
  - orderType, orderCompany
  - lines[]: New lines to add, each with itemNumber and quantity (at minimum)

Returns: Orchestration response confirming lines added.`,
      inputSchema: JdeAddSalesOrderLineSchema,
      annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: true },
    },
    async (params: JdeAddSalesOrderLineInput) => {
      try {
        const { orchestrationName, inputs } = await buildOrchestrationPayload(
          "addSalesOrderLines",
          params as unknown as Record<string, unknown>
        );
        const result = await callOrchestration(orchestrationName, inputs);
        return orchResult(result);
      } catch (err) {
        return orchError("jde_add_sales_order_line", err);
      }
    }
  );
}

// ══════════════════════════════════════════════════════════════
// CANCEL / DELETE — Sales Order or Line
// ══════════════════════════════════════════════════════════════

export function registerCancelSalesOrder(server: McpServer): void {
  server.registerTool(
    "jde_cancel_sales_order",
    {
      title: "Cancel JDE Sales Order or Line",
      description: `Cancel an entire sales order or a specific line in JDE via orchestration.

If lineNumber is provided, only that line is cancelled.
If lineNumber is omitted, the ENTIRE order is cancelled.

⚠️ This is a DESTRUCTIVE operation. Always confirm with the user.

Args:
  - orderNumber (required): DOCO
  - orderType, orderCompany
  - lineNumber: Specific line to cancel (LNID). Omit to cancel entire order.
  - cancelReason: Optional reason code

Returns: Orchestration response confirming cancellation.`,
      inputSchema: JdeCancelSalesOrderSchema,
      annotations: { readOnlyHint: false, destructiveHint: true, idempotentHint: true, openWorldHint: true },
    },
    async (params: JdeCancelSalesOrderInput) => {
      try {
        const { orchestrationName, inputs } = await buildOrchestrationPayload(
          "cancelSalesOrder",
          params as unknown as Record<string, unknown>
        );
        const result = await callOrchestration(orchestrationName, inputs);
        return orchResult(result);
      } catch (err) {
        return orchError("jde_cancel_sales_order", err);
      }
    }
  );
}

// ══════════════════════════════════════════════════════════════
// SUPPORTING — Customer Lookup
// ══════════════════════════════════════════════════════════════

export function registerCustomerLookup(server: McpServer): void {
  server.registerTool(
    "jde_customer_lookup",
    {
      title: "Look Up JDE Customer",
      description: `Search the JDE Address Book (F0101) for customers.

Use this to find a customer's AN8 before creating a sales order, or to verify customer details.

Args:
  - customerNumber: Exact AN8 lookup
  - name: Partial name search
  - maxRows (default 20)`,
      inputSchema: JdeCustomerLookupSchema,
      annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true },
    },
    async (params: JdeCustomerLookupInput) => {
      try {
        const filters: FilterDef[] = [];
        addFilter(filters, "AN8", "EQUAL", params.customerNumber);
        filters.push({ column: "AT1", operator: "EQUAL", value: "C" });
        if (params.name) {
          filters.push({ column: "ALPH", operator: "STR_CONTAIN", value: params.name });
        }

        const resp = await queryTable({
          tableName: "F0101",
          columns: ["AN8", "ALPH", "DC", "AT1", "ADD1", "CTY1", "ADDS", "CTR"],
          filters,
          maxRows: params.maxRows,
        });

        const grid = resp.fs_DATABROWSE?.data?.gridData;
        if (!grid || grid.rowset.length === 0) {
          return { content: [{ type: "text" as const, text: "No customers found." }] };
        }
        return formatQueryResult("Customer Lookup (F0101)", "F0101", grid);
      } catch (err) {
        return orchError("jde_customer_lookup", err);
      }
    }
  );
}

// ══════════════════════════════════════════════════════════════
// SUPPORTING — Item / Availability Check
// ══════════════════════════════════════════════════════════════

export function registerItemCheck(server: McpServer): void {
  server.registerTool(
    "jde_item_check",
    {
      title: "Check JDE Item & Availability",
      description: `Look up an item in JDE and check on-hand availability by branch (F41021).

Use before adding a line to a sales order to verify the item exists and has stock.

Args:
  - itemNumber: LITM (full or partial)
  - branchPlant: MCU to check (omit for all branches)
  - maxRows (default 20)`,
      inputSchema: JdeItemCheckSchema,
      annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true },
    },
    async (params: JdeItemCheckInput) => {
      try {
        const filters: FilterDef[] = [];
        if (params.itemNumber) {
          filters.push({ column: "LITM", operator: "STR_CONTAIN", value: params.itemNumber });
        }
        addFilter(filters, "MCU", "EQUAL", params.branchPlant);

        const resp = await queryTable({
          tableName: "F41021",
          columns: ["ITM", "LITM", "MCU", "OPC"],
          filters,
          maxRows: params.maxRows,
        });

        const grid = resp.fs_DATABROWSE?.data?.gridData;
        if (!grid || grid.rowset.length === 0) {
          return { content: [{ type: "text" as const, text: "No items found matching the criteria." }] };
        }
        return formatQueryResult("Item Availability (F41021)", "F41021", grid);
      } catch (err) {
        return orchError("jde_item_check", err);
      }
    }
  );
}
