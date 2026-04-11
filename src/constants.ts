// ──────────────────────────────────────────────────────────────
// JDE AIS Server Configuration (from environment)
// ──────────────────────────────────────────────────────────────

export const AIS_BASE_URL = process.env.JDE_AIS_URL ?? "";
export const JDE_USERNAME = process.env.JDE_USERNAME ?? "";
export const JDE_PASSWORD = process.env.JDE_PASSWORD ?? "";
export const JDE_ENVIRONMENT = process.env.JDE_ENVIRONMENT ?? "JDV920";
export const JDE_ROLE = process.env.JDE_ROLE ?? "*ALL";

// API version prefix: "v2" for direct AIS, "v3" for API Gateway
export const AIS_API_VERSION = process.env.JDE_API_VERSION ?? "v2";

// Fail fast if critical env vars are missing
if (!AIS_BASE_URL) throw new Error("JDE_AIS_URL environment variable is required");
if (!JDE_USERNAME) throw new Error("JDE_USERNAME environment variable is required");
if (!JDE_PASSWORD) throw new Error("JDE_PASSWORD environment variable is required");

// ──────────────────────────────────────────────────────────────
// MCP Server Defaults
// ──────────────────────────────────────────────────────────────

/** Max rows per query to avoid blowing up context windows */
export const DEFAULT_MAX_PAGE_SIZE = 50;

/** Max characters in a tool response before truncation */
export const CHARACTER_LIMIT = 50_000;

// Basic Auth is now used — no token refresh needed.
