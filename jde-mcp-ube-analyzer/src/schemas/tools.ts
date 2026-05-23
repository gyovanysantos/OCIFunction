import { z } from "zod";

// ──────────────────────────────────────────────────────────────
// Shared
// ──────────────────────────────────────────────────────────────

const AisOperatorEnum = z.enum([
  "EQUAL", "NOT_EQUAL", "LESS", "LESS_EQUAL",
  "GREATER", "GREATER_EQUAL", "BETWEEN", "LIST",
  "STR_CONTAIN", "STR_START_WITH", "STR_END_WITH",
  "STR_BLANK", "STR_NOT_BLANK",
]).describe("AIS query operator");

const FilterSchema = z.object({
  column: z.string().describe("JDE column alias (e.g. DOCO, AN8, LITM)"),
  operator: AisOperatorEnum,
  value: z.union([z.string(), z.array(z.string())])
    .describe("Value(s) to filter on. Use array for LIST/BETWEEN operators"),
}).strict();

// ──────────────────────────────────────────────────────────────
// Data Dictionary Tools
// ──────────────────────────────────────────────────────────────

export const JdeDictionarySearchSchema = z.object({
  keyword: z.string()
    .min(1)
    .max(100)
    .describe("Search keyword — matches table names, descriptions, column names/aliases."),
}).strict();

export const JdeDictionaryListSchema = z.object({}).strict();

export const JdeDictionaryTableSchema = z.object({
  tableName: z.string().min(1).max(20)
    .describe("JDE table name (e.g. 'F4211', 'F0101')"),
}).strict();

// ──────────────────────────────────────────────────────────────
// Generic Query Tool
// ──────────────────────────────────────────────────────────────

export const JdeQueryTableSchema = z.object({
  tableName: z.string().min(1).max(20)
    .describe("JDE table name to query"),
  columns: z.array(z.string()).min(1).max(50)
    .describe("JDE column aliases to return"),
  filters: z.array(FilterSchema).optional()
    .describe("Optional filter conditions"),
  maxRows: z.number().int().min(1).max(500).default(50)
    .describe("Max rows to return (default 50)"),
}).strict();

// ──────────────────────────────────────────────────────────────
// Generic Orchestration (escape hatch)
// ──────────────────────────────────────────────────────────────

export const JdeCallOrchestrationSchema = z.object({
  orchestrationName: z.string().min(1).max(200)
    .describe("Name of the JDE orchestration to invoke"),
  inputs: z.record(z.unknown())
    .describe("Key-value inputs for the orchestration"),
}).strict();

// ──────────────────────────────────────────────────────────────
// Layer 0 — Dynamic Discovery Tools
// ──────────────────────────────────────────────────────────────

export const JdeDiscoverTableSchema = z.object({
  tableName: z.string().min(1).max(20)
    .describe("JDE table name to discover (e.g. 'F4211', 'F0101'). Queries F9210 for structure and F9200 for column descriptions."),
}).strict();

export const JdeSearchTablesSchema = z.object({
  keyword: z.string().min(1).max(100)
    .describe("Search keyword to find JDE tables by name or description. Queries F0092 (Object Librarian)."),
  maxRows: z.number().int().min(1).max(100).default(20)
    .describe("Max tables to return (default 20)"),
}).strict();

// ──────────────────────────────────────────────────────────────
// AP / GL Integrity Tools (R047001A support)
// ──────────────────────────────────────────────────────────────

export const JdeApVoucherQuerySchema = z.object({
  company: z.string().optional()
    .describe("Company code (CO), e.g. '00001'"),
  supplierNumber: z.number().int().optional()
    .describe("Supplier address book number (AN8)"),
  documentType: z.string().optional()
    .describe("Document type filter (DCT), e.g. 'PV' for voucher"),
  payStatus: z.string().optional()
    .describe("Payment status filter (PST): A=Approved, P=Paid, V=Void, D=Draft, H=Held"),
  glOffset: z.string().optional()
    .describe("GL posting code / offset account (GLPT). KEY field for R047001A grouping, e.g. 'IN' for inventory offset"),
  dateFrom: z.string().optional()
    .describe("GL date range start (YYYY-MM-DD)"),
  dateTo: z.string().optional()
    .describe("GL date range end (YYYY-MM-DD)"),
  fiscalYear: z.number().int().optional()
    .describe("Fiscal year filter (FY), e.g. 2026"),
  period: z.number().int().min(1).max(14).optional()
    .describe("GL period filter (PN), 1-14"),
  maxRows: z.number().int().min(1).max(500).default(100)
    .describe("Max rows to return (default 100)"),
}).strict();

export const JdeGlBalanceQuerySchema = z.object({
  company: z.string().optional()
    .describe("Company code (CO)"),
  businessUnit: z.string().optional()
    .describe("Business unit / cost center (MCU)"),
  objectAccount: z.string().optional()
    .describe("Object account (OBJ), e.g. '1110' for AP Trade"),
  subsidiary: z.string().optional()
    .describe("Subsidiary account (SUB) for detail-level lookup"),
  ledgerType: z.string().default("AA")
    .describe("Ledger type: AA=Actual (default), AU=Units, CA=Budget"),
  fiscalYear: z.number().int().optional()
    .describe("Fiscal year (FY), e.g. 2026"),
  maxRows: z.number().int().min(1).max(500).default(100)
    .describe("Max rows to return (default 100)"),
}).strict();

export const JdeGlDetailQuerySchema = z.object({
  accountId: z.string().optional()
    .describe("Account ID (AID), e.g. '00001.1110.ACME'"),
  company: z.string().optional()
    .describe("Company code (CO)"),
  documentType: z.string().optional()
    .describe("Document type (DCT), e.g. 'PV', 'JE'"),
  fiscalYear: z.number().int().optional()
    .describe("Fiscal year (FY)"),
  period: z.number().int().min(1).max(14).optional()
    .describe("GL period (PN), 1-14"),
  dateFrom: z.string().optional()
    .describe("GL date range start (YYYY-MM-DD)"),
  dateTo: z.string().optional()
    .describe("GL date range end (YYYY-MM-DD)"),
  maxRows: z.number().int().min(1).max(500).default(100)
    .describe("Max rows to return (default 100)"),
}).strict();

export const JdeApGlIntegrityCheckSchema = z.object({
  company: z.string()
    .describe("Company code (CO). Required for integrity check."),
  fiscalYear: z.number().int()
    .describe("Fiscal year to check (FY), e.g. 2026. Required."),
  periodFrom: z.number().int().min(1).max(14)
    .describe("Starting period (PN). Required."),
  periodTo: z.number().int().min(1).max(14)
    .describe("Ending period (PN). Required."),
  glOffset: z.string().optional()
    .describe("Specific GL offset code (GLPT) to check. Omit to check ALL offset accounts."),
}).strict();

// ──────────────────────────────────────────────────────────────
// Inferred types
// ──────────────────────────────────────────────────────────────

export type JdeDictionarySearchInput = z.infer<typeof JdeDictionarySearchSchema>;
export type JdeQueryTableInput = z.infer<typeof JdeQueryTableSchema>;
export type JdeCallOrchestrationInput = z.infer<typeof JdeCallOrchestrationSchema>;
export type JdeDiscoverTableInput = z.infer<typeof JdeDiscoverTableSchema>;
export type JdeSearchTablesInput = z.infer<typeof JdeSearchTablesSchema>;
export type JdeApVoucherQueryInput = z.infer<typeof JdeApVoucherQuerySchema>;
export type JdeGlBalanceQueryInput = z.infer<typeof JdeGlBalanceQuerySchema>;
export type JdeGlDetailQueryInput = z.infer<typeof JdeGlDetailQuerySchema>;
export type JdeApGlIntegrityCheckInput = z.infer<typeof JdeApGlIntegrityCheckSchema>;

// ──────────────────────────────────────────────────────────────
// Batch / Unposted Batches Tools (R007011 support)
// ──────────────────────────────────────────────────────────────

export const JdeBatchQuerySchema = z.object({
  company: z.string().optional()
    .describe("Company code (KCO)"),
  batchNumber: z.number().int().optional()
    .describe("Specific batch number (ICU)"),
  batchType: z.string().optional()
    .describe("Batch type (ICUT): G=GL, V=Voucher, W=Time Entry, K=Receipts, etc."),
  dateFrom: z.string().optional()
    .describe("GL date range start (YYYY-MM-DD) for DGJ (GL date)"),
  dateTo: z.string().optional()
    .describe("GL date range end (YYYY-MM-DD) for DGJ (GL date)"),
  maxRows: z.number().int().min(1).max(500).default(100)
    .describe("Max rows to return (default 100)"),
}).strict();

export const JdeBatchTransactionQuerySchema = z.object({
  batchNumber: z.number().int().optional()
    .describe("Batch number (ICU) to retrieve transactions for"),
  batchType: z.string().optional()
    .describe("Batch type (ICUT): G=GL, V=Voucher, etc."),
  company: z.string().optional()
    .describe("Company code (KCO)"),
  documentNumber: z.number().int().optional()
    .describe("Document number (DOC) within the batch"),
  fiscalYear: z.number().int().optional()
    .describe("Fiscal year (FY)"),
  period: z.number().int().min(1).max(14).optional()
    .describe("GL period (PN), 1-14"),
  maxRows: z.number().int().min(1).max(500).default(100)
    .describe("Max rows to return (default 100)"),
}).strict();

export const JdeUnpostedBatchCheckSchema = z.object({
  company: z.string().optional()
    .describe("Company code (KCO). Optional filter."),
  batchType: z.string().optional()
    .describe("Batch type to check (ICUT): G=GL, V=Voucher. Omit for ALL types."),
  dateFrom: z.string().optional()
    .describe("Only check batches with GL date on or after this date (YYYY-MM-DD)"),
  dateTo: z.string().optional()
    .describe("Only check batches with GL date on or before this date (YYYY-MM-DD)"),
  maxRows: z.number().int().min(1).max(500).default(200)
    .describe("Max rows to return (default 200)"),
}).strict();

export type JdeBatchQueryInput = z.infer<typeof JdeBatchQuerySchema>;
export type JdeBatchTransactionQueryInput = z.infer<typeof JdeBatchTransactionQuerySchema>;
export type JdeUnpostedBatchCheckInput = z.infer<typeof JdeUnpostedBatchCheckSchema>;
