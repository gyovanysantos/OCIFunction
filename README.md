# JDE Integrity Report AI Analyzer

> Multi-agent AI system that analyzes JD Edwards Integrity Reports using OCI GenAI Agents and the Model Context Protocol (MCP) for live JDE data verification.

---

## What It Does

When JDE runs a scheduled Integrity Report (R047001A A/P to G/L, R007011 Unposted Batches, etc.), a JDE Orchestration uploads the PDF to OCI Object Storage and calls this system. Two AI agents work in sequence:

1. **ExtractorAgent** — Downloads the PDF, extracts text, and produces structured JSON (report type, discrepancies, accounts).
2. **AnalyzerAgent** — Cross-references the extracted findings against **live JDE data** via MCP tools, confirming or resolving each discrepancy.

The system returns JDE-safe HTML that the Orchestration can route to email, notifications, or JDE queues.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     ORACLE CLOUD INFRASTRUCTURE                     │
│                                                                     │
│  ┌────────────────┐    ┌──────────────────┐                        │
│  │ API Container   │───▶│ ExtractorAgent   │                        │
│  │ (FastAPI :8080) │    │ (PDF → JSON)     │                        │
│  └────────────────┘    └────────┬─────────┘                        │
│                                 │ structured JSON                   │
│                        ┌────────▼─────────┐                        │
│                        │ AnalyzerAgent     │                        │
│                        │ (MCP bridge)      │                        │
│                        └────────┬─────────┘                        │
│                                 │ JSON-RPC over HTTP                │
│                        ┌────────▼─────────┐    ┌──────────────┐    │
│                        │ JDE MCP Server    │───▶│ JDE AIS API  │    │
│                        │ (Node.js :3000)   │    │ F0411, F0902 │    │
│                        └──────────────────┘    │ F0901, F0911 │    │
│                                                └──────────────┘    │
│  Compartment: jdee1 │ Region: us-phoenix-1                         │
└─────────────────────────────────────────────────────────────────────┘
```

### End-to-End Flow

| Step | Component | Action |
|------|-----------|--------|
| 1 | JDE Batch Job | Runs Integrity Report → produces PDF |
| 2 | JDE Orchestration | Uploads PDF to OCI Object Storage |
| 3 | JDE Orchestration | `POST /v1/analyze` with the PDF filename |
| 4 | ExtractorAgent | Downloads PDF from OCI, extracts text with `pypdf`, LLM produces structured JSON |
| 5 | AnalyzerAgent | Calls MCP bridge tools → queries live JDE data → cross-references findings |
| 6 | API | Returns `{checkerResponse, analysisResponse}` with JDE-safe HTML |

---

## Multi-Agent Architecture (OCI ADK)

This system uses the **OCI Agent Development Kit (ADK)** — Oracle's official framework for building AI agents that run on OCI GenAI Agents Service.

### How ADK Works

```
AgentClient (OCI auth)
    └── Agent.setup()         ← registers tools with OCI GenAI
    └── Agent.run(prompt)     ← starts the agent loop on OCI
         ├── LLM reasoning    ← runs server-side on OCI GenAI
         ├── Tool selection   ← LLM decides which @tool to call
         ├── Tool execution   ← runs locally in your container
         └── Result → LLM     ← loop continues until done
```

- **Server-side agent loop**: The LLM reasoning and tool-calling decisions run on OCI GenAI Agents Service — not locally.
- **Local tool execution**: When the LLM calls a `@tool`, the ADK framework executes it in your container and submits the result back.
- **Deterministic workflow**: Plain Python sequential `agent.run()` calls — ExtractorAgent first, then AnalyzerAgent.

### Agent Details

| Agent | Purpose | Tools | Output |
|-------|---------|-------|--------|
| **ExtractorAgent** | PDF → structured data | `download_and_extract_pdf` | JSON: report type, company, discrepancies, accounts |
| **AnalyzerAgent** | Cross-reference via MCP | 7 MCP bridge tools | Verified analysis with confirmed/resolved issues |

### Workflow Code Pattern

```python
from oci.addons.adk import Agent, AgentClient

client = AgentClient(auth_type="api_key")

extractor = Agent(client, endpoint_id=EXTRACTOR_ENDPOINT)
extractor.setup(tools=[download_and_extract_pdf])

analyzer = Agent(client, endpoint_id=ANALYZER_ENDPOINT)
analyzer.setup(tools=[jde_ap_voucher_query, jde_gl_balance_query, ...])

# Sequential deterministic pipeline
extraction = extractor.run(f"Extract data from {object_name}")
analysis = analyzer.run(f"Analyze this extraction: {extraction}")
```

---

## MCP Integration — The Bridge Pattern

The AnalyzerAgent needs to query live JDE data. OCI ADK has **no native MCP support**, so we use a bridge pattern:

```
AnalyzerAgent  →  ADK @tool functions  →  httpx (JSON-RPC)  →  JDE MCP Server  →  JDE AIS API
                  (mcp_bridge.py)                               (Node.js)          (live data)
```

### How It Works

1. The AnalyzerAgent's LLM decides it needs JDE data (e.g., "query AP vouchers for company 00060").
2. ADK calls the corresponding `@tool` function in `mcp_bridge.py`.
3. The bridge function sends a JSON-RPC 2.0 request to the MCP server via `httpx`.
4. The MCP server queries JDE AIS REST API and returns the results.
5. The bridge function returns the data to ADK, which feeds it back to the LLM.

### MCP Bridge Tools

| Tool | JDE Table | Purpose |
|------|-----------|---------|
| `jde_ap_voucher_query` | F0411 | Query A/P vouchers by company, supplier, GL posting type |
| `jde_gl_balance_query` | F0902 | Query G/L period balances by account, ledger type, fiscal year |
| `jde_gl_detail_query` | F0901 | Drill into individual journal entries |
| `jde_ap_gl_integrity_check` | F0411 + F0902 | Programmatic R047001A — sums F0411 by GLPT, compares against F0902 |
| `jde_batch_query` | F0011 | Query batch headers by status and type |
| `jde_batch_transaction_query` | F0911 | Query batch transaction details |
| `jde_unposted_batch_check` | F0011 + F0911 | Identifies unposted batches (R007011 verification) |

### JDE MCP Server

The MCP server is a TypeScript/Node.js 22 application using the official `@modelcontextprotocol/sdk`. It exposes 14 tools across 5 layers:

| Layer | Tools | Description |
|-------|-------|-------------|
| **Discovery** | Table/column discovery | Explore JDE schema dynamically |
| **Dictionary** | Data dictionary lookups | Resolve JDE codes and field meanings |
| **Query** | Generic data queries | Flexible SQL-like queries on any JDE table |
| **Integrity** | AP/GL integrity checks | Curated tools for R047001A verification |
| **Batch** | Batch status queries | Curated tools for R007011 verification |

Transport: **StreamableHTTP** on port 3000 (`/mcp` endpoint, `/health` for health checks).

---

## OCI Infrastructure

All resources are in the **jdee1** compartment, **us-phoenix-1** region.

| Component | OCI Service | Purpose |
|-----------|-------------|---------|
| **Agent Endpoints** | OCI GenAI Agents Service | 2 agent endpoints (ExtractorAgent, AnalyzerAgent) — server-side LLM reasoning |
| **PDF Storage** | OCI Object Storage | Private bucket for Integrity Report PDFs |
| **API Gateway** | OCI API Gateway | Public + private endpoints for JDE Orchestration access |
| **Auth** | OCI IAM | `api_key` for local dev, `instance_principal` for OCI compute |

### Authentication

| Context | Auth Type | Details |
|---------|-----------|---------|
| Local development | `api_key` | Reads `~/.oci/config` (mounted as Docker volume) |
| OCI Container Instance | `instance_principal` | Automatic auth via instance metadata — no keys needed |

### Future: OCI Container Instances

Currently the API and MCP server run via Docker Compose for local development. The production plan is to deploy both as **OCI Container Instances**:

- **API Container** (Python/FastAPI) — runs both agents in-process via ADK
- **MCP Container** (Node.js) — serves MCP tools, queries JDE AIS

Container Instances provide serverless-like simplicity (no VMs to manage) with container flexibility.

---

## Quick Start

### Prerequisites

- Docker & Docker Compose
- OCI CLI configured (`~/.oci/config` with a valid profile)
- OCI GenAI Agent endpoints created (ExtractorAgent + AnalyzerAgent)
- JDE AIS server accessible from your environment

### 1. Configure Environment

```bash
cp .env.example .env
# Edit .env with your values:
#   JDE_AIS_URL, JDE_USERNAME, JDE_PASSWORD
#   EXTRACTOR_AGENT_ENDPOINT_ID, ANALYZER_AGENT_ENDPOINT_ID
```

### 2. Build & Run

```bash
docker compose up --build
```

This starts two containers:
- **jde-mcp-server** on `http://localhost:3000` (MCP + health check)
- **jde-api** on `http://localhost:8080` (REST API)

### 3. Test

```bash
# Health check
curl http://localhost:8080/health

# Analyze a report
curl -X POST http://localhost:8080/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{"object_name": "R007011_CAN0001_32083_PDF.pdf"}'
```

### 4. Run Integration Tests

```bash
# MCP server + bridge tests (8 tests)
python tests/test_local.py

# Full E2E workflow (requires real PDF in OCI bucket)
python tests/test_workflow_e2e.py

# Docker API endpoint test
python tests/test_api_docker.py
```

---

## API Contract

### `POST /v1/analyze`

**Request:**
```json
{
  "object_name": "R007011_CAN0001_32083_PDF.pdf",
  "prompt": "Analyze this Integrity Report. Identify all problems and recommend fixes."
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `object_name` | string | Yes | PDF filename in OCI Object Storage |
| `prompt` | string | No | Custom analysis instruction (has default) |

**Response (report has data):**
```json
{
  "checkerResponse": "Yes",
  "analysisResponse": "<table width=\"100%\" ...>JDE-safe HTML</table>"
}
```

**Response (empty report):**
```json
{
  "checkerResponse": "No",
  "analysisResponse": "<table width=\"100%\" ...>No discrepancies found</table>"
}
```

The `analysisResponse` field contains **JDE-safe HTML** compatible with `CL001_SimpleEmailJob` — no CSS, no modern HTML tags, only table-based layout with `<font>` tags.

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `JDE_AIS_URL` | Yes | — | JDE AIS REST API base URL |
| `JDE_USERNAME` | Yes | — | JDE AIS username |
| `JDE_PASSWORD` | Yes | — | JDE AIS password |
| `JDE_ENVIRONMENT` | No | `JDV920` | JDE environment name |
| `OCI_AUTH_TYPE` | No | `api_key` | `api_key`, `instance_principal`, or `resource_principal` |
| `OCI_REGION` | No | `us-phoenix-1` | OCI region |
| `EXTRACTOR_AGENT_ENDPOINT_ID` | Yes | — | OCID of ExtractorAgent endpoint |
| `ANALYZER_AGENT_ENDPOINT_ID` | Yes | — | OCID of AnalyzerAgent endpoint |
| `OCI_BUCKET_NAME` | No | `OBJECTSTORAGE` | OCI Object Storage bucket name |
| `OCI_NAMESPACE` | No | `idxoqn0ijjyv` | OCI Object Storage namespace |
| `MCP_SERVER_URL` | No | `http://mcp:3000/mcp` | MCP server URL (set by Docker Compose) |
| `ADK_LOG_LEVEL` | No | `INFO` | Set to `DEBUG` for tool execution traces |

---

## Tech Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| Agent Framework | OCI ADK (`oci[adk]`) | >= 2.133.0 |
| Agent Runtime | OCI GenAI Agents Service | — |
| API Framework | FastAPI + uvicorn | >= 0.115.0 |
| MCP SDK | `@modelcontextprotocol/sdk` | ^1.12.0 |
| MCP Server Runtime | Node.js | 22 LTS |
| MCP Server Language | TypeScript | ^5.5.0 |
| HTTP Transport (bridge) | httpx | >= 0.27.0 |
| PDF Extraction | pypdf | >= 4.0.0 |
| Validation | Zod | ^3.23.0 |
| Containers | Docker Compose | — |

---

## Project Structure

```
OCIFunction/
├── docker-compose.yml                # 2 services: mcp + api
├── .env.example                      # Environment template
│
├── agents/                           # OCI ADK Multi-Agent System
│   ├── api.py                        # FastAPI (POST /v1/analyze, GET /health)
│   ├── workflow.py                   # Deterministic pipeline: Extractor → Analyzer
│   ├── mcp_bridge.py                 # @tool bridging ADK → MCP server via httpx
│   ├── Dockerfile.api                # Python 3.12-slim container
│   ├── extractor/agent.py            # ExtractorAgent: PDF download + extraction
│   └── analyzer/agent.py             # AnalyzerAgent: MCP cross-reference instructions
│
├── jde-mcp-server-template/          # JDE MCP Server (git subtree)
│   ├── src/
│   │   ├── index.ts                  # Server setup, 14 tool registrations
│   │   ├── tools/integrity.ts        # AP/GL integrity tools
│   │   ├── tools/batch.ts            # Batch status tools (R007011)
│   │   ├── tools/query.ts            # Generic JDE query tools
│   │   └── schemas/tools.ts          # Zod input schemas
│   └── Dockerfile                    # Node.js 22 Alpine container
│
├── tests/                            # Integration & E2E tests
├── ARCHITECTURE.md                   # Detailed architecture document
├── TECH-STACK.md                     # Technology inventory
├── PLAN.md                           # Project log & decisions
└── LESSONS.md                        # Lessons learned
```

---

## Documentation

| Document | Content |
|----------|---------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Full architecture with diagrams, API contract, security, cost analysis |
| [TECH-STACK.md](TECH-STACK.md) | All technologies, versions, and rationale |
| [PLAN.md](PLAN.md) | Project log: decisions, changes, deployment history |
| [LESSONS.md](LESSONS.md) | Lessons learned during development |

---

## License

Internal project — not for public distribution.
