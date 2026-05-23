# JDE Integrity Report AI Analyzer — Tech Stack

> **Last Updated**: April 13, 2026

---

## Foundry Agent Layer

| Component | Technology | Version | Why |
|-----------|-----------|---------|-----|
| **Agent Framework** | Microsoft Agent Framework | `agent-framework-core==1.0.0rc3`, `agent-framework-azure-ai==1.0.0rc3` | Official Microsoft framework for building hosted agents with tool support, workflows, and streaming |
| **Hosting Adapter** | `azure-ai-agentserver-agentframework` | `1.0.0b16` | Wraps agents as HTTP services (port 8088) for Foundry Agent Service deployment |
| **Azure Identity** | `azure-identity` | >= 1.17.0 | Async `DefaultAzureCredential` for Foundry authentication (local dev + managed identity in production) |
| **Runtime** | Python | 3.12 | Required for agent-framework SDK; latest stable Python |
| **LLM (Agents)** | Azure OpenAI (e.g. GPT-4o) | Via Foundry deployment | Model for agent reasoning — configured via `FOUNDRY_MODEL_DEPLOYMENT_NAME` |
| **Container** | Docker | python:3.12-slim | Slim image for Foundry Agent Service deployment |
| **API Framework** | FastAPI | >= 0.115.0 | Async REST wrapper for agent pipeline — exposes v1.0 JDE Orchestration contract (`POST /v1/analyze`) |
| **ASGI Server** | uvicorn | >= 0.30.0 | Production ASGI server for FastAPI (standard extras for auto-reload in dev) |
| **Markdown→HTML** | markdown | >= 3.6 | Converts LLM markdown output to HTML for JDE email integration (`CL001_SimpleEmailJob`) |
| **Environment** | python-dotenv | >= 1.0.0 | `load_dotenv(override=False)` — env file for local dev, Foundry sets vars in production |

### JDE MCP Server Layer

| Component | Technology | Version | Why |
|-----------|-----------|---------|-----|
| **Runtime** | Node.js | 22 (LTS) | Required for MCP SDK; latest LTS with native ESM and fetch |
| **MCP SDK** | `@modelcontextprotocol/sdk` | ^1.12.0 | Official Model Context Protocol SDK — provides `McpServer`, tool registration, and transport handling |
| **HTTP Framework** | Express | ^4.21.0 | Serves the MCP server endpoint via StreamableHTTPServerTransport over `/mcp` |
| **Validation** | Zod | ^3.23.0 | Runtime schema validation for all MCP tool inputs — type-safe, composable, JSON Schema compatible |
| **Language** | TypeScript | ^5.5.0 | Type safety for the 5-layer tool architecture; compiles to ESM for Node.js 22 |
| **Container** | Docker | Alpine-based Node.js 22 | Lightweight image for Azure Container Apps deployment |
| **Hosting** | Azure Container Apps | — | Runs MCP server (`jde-mcp-integrity`) and API wrapper (`jde-integrity-api`) as always-on HTTP services |

### Cross-Cutting

| Component | Technology | Version | Why |
|-----------|-----------|---------|-----|
| **OCI SDK (Agents)** | `oci` Python SDK | >= 2.133.0 | ExtractorAgent downloads PDFs from OCI Object Storage using API key auth |
| **PDF Extraction** | `pypdf` | >= 4.0.0 | Same library used in v1.0 — pure Python, no native deps |
| **JDE AIS** | JDE AIS REST API | — | JDE EnterpriseOne Application Interface Services — the MCP server queries F0411, F0902, F0901 tables via HTTP Data Service |
| **Version Control** | Git (subtree) | — | JDE MCP server is included as a `git subtree` from `gyovanysantos/jde-mcp-server-template` |

---

## JDE Tables Used

| Table | Description | Used By |
|-------|-------------|---------|
| **F0411** | A/P Ledger (voucher pay items) | `jde_ap_voucher_query`, `jde_ap_gl_integrity_check` |
| **F0902** | Account Balances (period amounts) | `jde_gl_balance_query`, `jde_ap_gl_integrity_check` |
| **F0901** | Account Ledger (journal entries) | `jde_gl_detail_query` |
| F4211 | Sales Order Detail (line items) | Existing SO CRUD tools |
| F4201 | Sales Order Header | Existing SO CRUD tools |
| F0101 | Address Book Master | Customer lookup |
| F4101 | Item Master | Item check |
| F41021 | Item Location | Item availability |

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Azure OpenAI for agents** | Required by Foundry Agent Service; GPT-4.1 provides excellent reasoning for multi-step tool use |
| **MCP for JDE integration** | Open standard for LLM tool calling; enables the AnalyzerAgent to query live JDE data without custom integration code |
| **Git subtree (not submodule)** | Subtree keeps the MCP server code inline — easier to modify, no submodule init required for contributors |
| **Separate agents (not monolith)** | ExtractorAgent and AnalyzerAgent have different concerns (PDF processing vs. data cross-reference) — separation enables independent testing and iteration |
| **OCI SDK for PDF access** | Simplest approach — reuses existing `~/.oci/config` pattern; no need to mirror PDFs to Azure |
