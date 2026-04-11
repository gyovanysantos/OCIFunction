import {
  AIS_BASE_URL,
  JDE_USERNAME,
  JDE_PASSWORD,
  JDE_ENVIRONMENT,
  JDE_ROLE,
  AIS_API_VERSION,
  DEFAULT_MAX_PAGE_SIZE,
} from "../constants.js";

import https from "node:https";
import http from "node:http";

import type {
  AisDataRequest,
  AisDataResponse,
  AisFormRequest,
  AisOrchestrationRequest,
  AisQuery,
  AisCondition,
  AisOperator,
} from "../types.js";

// ──────────────────────────────────────────────────────────────
// Basic Auth — used for all AIS requests
// ──────────────────────────────────────────────────────────────

const BASIC_AUTH = Buffer.from(`${JDE_USERNAME}:${JDE_PASSWORD}`).toString("base64");

async function aisRequest<T>(
  path: string,
  body: object
): Promise<T> {
  const url = new URL(`${AIS_BASE_URL}${path}`);
  const payload = JSON.stringify(body);
  const transport = url.protocol === "https:" ? https : http;

  return new Promise<T>((resolve, reject) => {
    const req = transport.request(
      url,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Content-Length": Buffer.byteLength(payload),
          "Accept-Encoding": "identity",
          "Authorization": `Basic ${BASIC_AUTH}`,
        },
      },
      (res) => {
        const chunks: Buffer[] = [];
        res.on("data", (chunk: Buffer) => chunks.push(chunk));
        res.on("end", () => {
          const text = Buffer.concat(chunks).toString("utf-8");
          if (!res.statusCode || res.statusCode < 200 || res.statusCode >= 300) {
            reject(new Error(
              `AIS ${path} responded ${res.statusCode}: ${text.slice(0, 500)}`
            ));
            return;
          }
          try {
            resolve(JSON.parse(text) as T);
          } catch {
            reject(new Error(`AIS ${path}: invalid JSON response`));
          }
        });
        res.on("error", reject);
      }
    );
    req.on("error", reject);
    req.setTimeout(55_000, () => {
      req.destroy(new Error(`AIS ${path}: request timed out after 55s`));
    });
    req.write(payload);
    req.end();
  });
}

// No token lifecycle needed — Basic Auth is stateless.
// Kept as no-op export so index.ts doesn't need changes.
export async function logout(): Promise<void> {
  // Basic Auth is stateless — nothing to clean up.
}

// ──────────────────────────────────────────────────────────────
// Data Service — generic table query
// ──────────────────────────────────────────────────────────────

export interface DataServiceParams {
  tableName: string;
  columns?: string[];        // JDE aliases (e.g. ["DOCO","AN8","LITM"]); omit to return all
  filters?: Array<{
    column: string;
    operator: AisOperator;
    value: string | string[];
  }>;
  maxRows?: number;
}

function buildConditions(
  tableName: string,
  filters: DataServiceParams["filters"]
): AisCondition[] {
  if (!filters || filters.length === 0) return [];

  return filters.map((f) => {
    const values = Array.isArray(f.value) ? f.value : [f.value];
    // AIS v2/dataservice requires table-prefixed controlId (e.g. F4211.DOCO)
    const controlId = f.column.includes(".") ? f.column : `${tableName}.${f.column}`;
    return {
      controlId,
      operator: f.operator,
      value: values.map((v) => ({
        content: v,
        specialValueId: "LITERAL",
      })),
    };
  });
}

export async function queryTable(
  params: DataServiceParams
): Promise<AisDataResponse> {
  const body: AisDataRequest = {
    targetType: "table",
    targetName: params.tableName,
    dataServiceType: "BROWSE",
    findOnEntry: "TRUE",
    maxPageSize: String(params.maxRows ?? DEFAULT_MAX_PAGE_SIZE),
    environment: JDE_ENVIRONMENT,
    role: JDE_ROLE,
  };

  // Only include returnControlIDs when specific columns are requested.
  // Omitting it tells AIS to return all exposed columns.
  if (params.columns && params.columns.length > 0) {
    body.returnControlIDs = params.columns.join("|");
  }

  const conditions = buildConditions(params.tableName, params.filters);
  if (conditions.length > 0) {
    body.query = { autoFind: true, condition: conditions };
  }

  // AIS returns data under a dynamic key: fs_DATABROWSE_{tableName}
  // (e.g. fs_DATABROWSE_F0101, fs_DATABROWSE_F4211).
  // Normalize it to fs_DATABROWSE so all callers can access it consistently.
  const raw = await aisRequest<Record<string, unknown>>(`/${AIS_API_VERSION}/dataservice`, body);
  const browseKey = Object.keys(raw).find(k => k.startsWith("fs_DATABROWSE"));
  if (browseKey && browseKey !== "fs_DATABROWSE") {
    (raw as Record<string, unknown>)["fs_DATABROWSE"] = raw[browseKey];
  }
  return raw as unknown as AisDataResponse;
}

// ──────────────────────────────────────────────────────────────
// Form Service — for transactional operations
// ──────────────────────────────────────────────────────────────

export async function callFormService(
  formName: string,
  version: string,
  action: string,
  options?: {
    returnControlIDs?: string[];
    query?: AisQuery;
    formInputs?: Array<{ id: string; value: string }>;
    maxRows?: number;
  }
): Promise<unknown> {
  const body: AisFormRequest = {
    formName,
    version,
    formServiceAction: action,
    maxPageSize: String(options?.maxRows ?? DEFAULT_MAX_PAGE_SIZE),
    environment: JDE_ENVIRONMENT,
    role: JDE_ROLE,
  };

  if (options?.returnControlIDs) {
    body.returnControlIDs = options.returnControlIDs.join("|");
  }
  if (options?.query) {
    body.query = options.query;
  }
  if (options?.formInputs) {
    body.formInputs = options.formInputs;
  }

  return aisRequest("/v3/formservice", body);
}

// ──────────────────────────────────────────────────────────────
// Orchestration Service
// ──────────────────────────────────────────────────────────────

export async function callOrchestration(
  orchestrationName: string,
  inputs: Record<string, unknown>
): Promise<unknown> {
  const body: AisOrchestrationRequest = {
    environment: JDE_ENVIRONMENT,
    role: JDE_ROLE,
    ...inputs,
  };

  return aisRequest(
    `/v3/orchestrator/${encodeURIComponent(orchestrationName)}`,
    body
  );
}
