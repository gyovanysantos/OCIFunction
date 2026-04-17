# JDE Integrity Report AI Analyzer — Tech Stack

> **Last Updated**: April 12, 2026

---

## OCI ADK Multi-Agent Architecture

### OCI ADK Agent Layer

| Component | Technology | Version | Why |
|-----------|-----------|---------|-----|
| **Agent Framework** | OCI Agent Development Kit (ADK) | `oci[adk]>=2.133.0` | Official OCI framework for building agents with `@tool` decorator, `Agent`, `AgentClient`, and deterministic workflows |
| **Agent Runtime** | OCI GenAI Agents Service | us-phoenix-1 | Server-side agent loop (LLM reasoning + tool calling) — agents are OCI-managed resources visible in Console |
| **Auth** | OCI SDK auth | via `AgentClient` | Supports `api_key` (local dev), `instance_principal` (OCI compute) |
| **Runtime** | Python | 3.12 | Latest stable Python; required for ADK SDK |
| **MCP Bridge** | httpx | >= 0.27.0 | Sync HTTP client for bridging ADK `@tool` functions to MCP server via JSON-RPC over StreamableHTTP |
| **Container** | Docker | python:3.12-slim | Slim image for OCI Container Instance / Docker Compose deployment |
| **API Framework** | FastAPI | >= 0.115.0 | Async REST wrapper for agent pipeline — exposes JDE Orchestration contract (`POST /v1/analyze`) |
| **ASGI Server** | uvicorn | >= 0.30.0 | Production ASGI server for FastAPI |
| **Markdown→HTML** | markdown | >= 3.7 | Converts LLM markdown output to HTML for JDE email integration (`CL001_SimpleEmailJob`) |
| **Environment** | python-dotenv | >= 1.0.0 | `load_dotenv(override=False)` — env file for local dev, container env vars in production |

### JDE MCP Server Layer

| Component | Technology | Version | Why |
|-----------|-----------|---------|-----|
| **Runtime** | Node.js | 22 (LTS) | Required for MCP SDK; latest LTS with native ESM and fetch |
| **MCP SDK** | `@modelcontextprotocol/sdk` | ^1.12.0 | Official Model Context Protocol SDK — provides `McpServer`, tool registration, and transport handling |
| **HTTP Framework** | Express | ^4.21.0 | Serves the MCP server endpoint via StreamableHTTPServerTransport over `/mcp` |
| **Validation** | Zod | ^3.23.0 | Runtime schema validation for all MCP tool inputs — type-safe, composable, JSON Schema compatible |
| **Language** | TypeScript | ^5.5.0 | Type safety for the 5-layer tool architecture; compiles to ESM for Node.js 22 |
| **Container** | Docker | Alpine-based Node.js 22 | Lightweight image for Azure Container Apps deployment |
| **Hosting** | Docker Compose / OCI Container Instance | — | Runs MCP server alongside the API container; can be deployed as OCI Container Instance in production |

### Cross-Cutting

| Component | Technology | Version | Why |
|-----------|-----------|---------|-----|
| **OCI SDK (Agents)** | `oci` Python SDK | >= 2.133.0 | ExtractorAgent downloads PDFs from OCI Object Storage using API key auth |
| **PDF Extraction** | `pypdf` | >= 4.0.0 | Pure Python, no native deps |
| **JDE AIS** | JDE AIS REST API | — | JDE EnterpriseOne Application Interface Services — the MCP server queries F0411, F0902, F0901 tables via HTTP Data Service |
| **Version Control** | Git (subtree) | — | JDE MCP server is included as a `git subtree` from `gyovanysantos/jde-mcp-server-template` |

---

## JDE Tables Used

| Table | Description | Used By |
|-------|-------------|---------|
| **F0411** | A/P Ledger (voucher pay items) | `jde_ap_voucher_query`, `jde_ap_gl_integrity_check` |
| **F0902** | Account Balances (period amounts) | `jde_gl_balance_query`, `jde_ap_gl_integrity_check` |
| **F0901** | Account Ledger (journal entries) | `jde_gl_detail_query` |
| F0101 | Address Book Master | Generic query |
| F4101 | Item Master | Generic query |

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **OCI ADK for agents** | Native OCI agent framework; manages agent loop server-side, supports deterministic workflows, all infrastructure in one cloud |
| **MCP for JDE integration** | Open standard for LLM tool calling; enables the AnalyzerAgent to query live JDE data without custom integration code |
| **MCP Bridge pattern** | ADK has no native MCP support; `@tool` functions in `mcp_bridge.py` call MCP server via httpx (JSON-RPC) |
| **Git subtree (not submodule)** | Subtree keeps the MCP server code inline — easier to modify, no submodule init required for contributors |
| **Separate agents (not monolith)** | ExtractorAgent and AnalyzerAgent have different concerns (PDF processing vs. data cross-reference) — separation enables independent testing and iteration |
| **OCI SDK for PDF access** | Simplest approach — reuses existing `~/.oci/config` pattern; no cross-cloud concerns |
