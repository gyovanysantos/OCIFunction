# JDE Integrity Report AI Analyzer

> Multi-agent AI system that analyzes JD Edwards Integrity Reports using **Microsoft Foundry Agent Framework** and a **JDE MCP Server** — deployed on **Azure Container Apps**.

---

## What It Does

When JDE produces an Integrity Report (e.g., R047001A — A/P to G/L Integrity), this system:

1. **Downloads** the PDF from OCI Object Storage
2. **Extracts** structured data (company, fiscal year, discrepancies) using an AI agent
3. **Cross-references** the findings against **live JDE data** via MCP tools
4. **Returns** a verified analysis with confirmed issues and recommendations

The key differentiator: the AnalyzerAgent queries JDE tables (F0411, F0902, F0901) in real-time via the MCP Server, producing far more accurate results than LLM-only inference.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Azure Container Apps                     │
│                                                             │
│  ┌─────────────┐    ┌──────────────┐    ┌────────────────┐  │
│  │ API Wrapper  │───>│  Extractor   │───>│   Analyzer     │  │
│  │ FastAPI:8080 │    │  Agent       │    │   Agent        │  │
│  │ /v1/analyze  │    │ (PDF→JSON)   │    │ (MCP tools)    │  │
│  └─────────────┘    └──────┬───────┘    └───────┬────────┘  │
│                            │                    │            │
│                     ┌──────▼──────┐      ┌──────▼──────┐    │
│                     │ OCI Object  │      │ JDE MCP     │    │
│                     │ Storage     │      │ Server:3000 │    │
│                     └─────────────┘      └──────┬──────┘    │
│                                                 │            │
└─────────────────────────────────────────────────┼────────────┘
                                                  │
                                           ┌──────▼──────┐
                                           │  JDE AIS    │
                                           │  REST API   │
                                           └─────────────┘
```

### Components

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **ExtractorAgent** | Python 3.12 / Agent Framework | Downloads PDF from OCI, extracts text, produces structured JSON |
| **AnalyzerAgent** | Python 3.12 / Agent Framework + MCP | Cross-references PDF findings against live JDE data via MCP tools |
| **JDE MCP Server** | Node.js 22 / TypeScript | Exposes JDE tables as MCP tools via AIS REST API |
| **API Wrapper** | Python 3.12 / FastAPI | Backward-compatible REST API (`POST /v1/analyze`) for JDE Orchestrations |

---

## Tech Stack

### Agent Layer
| Technology | Version | Purpose |
|-----------|---------|---------|
| Python | 3.12 | Agent runtime |
| Microsoft Agent Framework | `1.0.0rc3` | Agent SDK — workflows, tools, streaming |
| Azure AI Foundry | GPT-4.1 | LLM for agent reasoning |
| Azure Identity | >= 1.17.0 | `DefaultAzureCredential` (async) |
| FastAPI | >= 0.115.0 | REST API wrapper |
| OCI SDK | >= 2.133.0 | PDF downloads from Object Storage |
| pypdf | >= 4.0.0 | PDF text extraction |

### MCP Server Layer
| Technology | Version | Purpose |
|-----------|---------|---------|
| Node.js | 22 LTS | Server runtime |
| TypeScript | ^5.5.0 | Type-safe tool implementations |
| MCP SDK | ^1.12.0 | Model Context Protocol server |
| Express | ^4.21.0 | HTTP transport for MCP |
| Zod | ^3.23.0 | Runtime schema validation |

### Infrastructure
| Service | Purpose |
|---------|---------|
| Azure Container Apps | Hosts MCP server + API wrapper |
| Azure Container Registry | Docker image storage |
| Azure AI Foundry | Model hosting and agent orchestration |
| OCI Object Storage | PDF report source (JDE uploads here) |

---

## MCP Tools — 5-Layer Architecture

The JDE MCP Server exposes 18 tools organized in layers:

| Layer | Tools | Purpose |
|-------|-------|---------|
| **0 — Discovery** | `jde_discover_table`, `jde_search_tables` | Dynamic JDE table discovery |
| **1 — Dictionary** | `jde_dictionary_search`, `jde_dictionary_list`, `jde_dictionary_table` | Table metadata lookup |
| **2 — Domain** | Sales Order CRUD (5 tools) | Business-level SO operations |
| **2.5 — Integrity** | `jde_ap_voucher_query`, `jde_gl_balance_query`, `jde_gl_detail_query`, `jde_ap_gl_integrity_check` | **AP/GL integrity analysis** |
| **3 — Lookups** | `jde_customer_lookup`, `jde_item_check` | Supporting lookups |
| **4 — Generic** | `jde_query_table`, `jde_call_orchestration` | Fallback tools |

The **`jde_ap_gl_integrity_check`** tool is the centerpiece — it performs the same reconciliation logic as the JDE R047001A report programmatically, comparing F0411 (AP Ledger) against F0902 (GL Balances).

---

## Quick Start — Local Development

### Prerequisites
- Docker Desktop
- OCI config file (`~/.oci/config` with DEFAULT profile)
- Azure AI Foundry project endpoint
- JDE AIS server access

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env with your JDE, Azure, and OCI credentials
```

### 2. Start all services

```bash
docker compose up --build
```

This starts 4 containers:

| Service | Port | URL |
|---------|------|-----|
| JDE MCP Server | 3000 | http://localhost:3000/health |
| ExtractorAgent | 8088 | http://localhost:8088 |
| AnalyzerAgent | 8089 | http://localhost:8089 |
| API Wrapper | 8080 | http://localhost:8080/health |

### 3. Test the API

```bash
curl -X POST http://localhost:8080/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{"object_name": "R047001A_ZJDE0001_588_PDF.pdf"}'
```

---

## API Contract

### Request

```
POST /v1/analyze
Content-Type: application/json

{
  "object_name": "R047001A_ZJDE0001_588_PDF.pdf",
  "prompt": "Analyze this Integrity Report."
}
```

### Response

```json
{
  "checkerResponse": "Yes",
  "analysisResponse": "<table>...JDE-safe HTML analysis...</table>"
}
```

| Field | Description |
|-------|-------------|
| `checkerResponse` | `"Yes"` if report has data, `"No"` if empty |
| `analysisResponse` | HTML-formatted analysis (JDE email-safe) |

---

## Deployment — Azure Container Apps

### Azure Resources

| Resource | Name |
|----------|------|
| Resource Group | `rg-hackathon-2603` |
| Container Registry | `acrjdemcppo.azurecr.io` |
| Container Apps Environment | `jde-mcp-env` (East US) |
| MCP Container App | `jde-mcp-integrity` |
| API Container App | `jde-integrity-api` |

### Deploy MCP Server

```bash
# Build and push
docker build -t acrjdemcppo.azurecr.io/jde-mcp-integrity:v1 ./jde-mcp-ube-analyzer
docker push acrjdemcppo.azurecr.io/jde-mcp-integrity:v1

# Create/update Container App
az containerapp create --name jde-mcp-integrity \
  --resource-group rg-hackathon-2603 \
  --environment jde-mcp-env \
  --image acrjdemcppo.azurecr.io/jde-mcp-integrity:v1 \
  --target-port 3000 --ingress external
```

### Deploy API Wrapper

```bash
docker build -t acrjdemcppo.azurecr.io/jde-integrity-api:v5 -f agents/Dockerfile.api ./agents
docker push acrjdemcppo.azurecr.io/jde-integrity-api:v5
```

> **Note**: Use `docker build` + `docker push` — not `az acr build` (cloud builds crash for this project).

---

## Project Structure

```
OCIFunction/
├── docker-compose.yml               # Local dev: 4 services
├── .env.example                     # Environment template
│
├── agents/                          # Foundry Multi-Agent System
│   ├── api.py                       # FastAPI wrapper (POST /v1/analyze)
│   ├── app.py                       # Workflow entry point
│   ├── workflow.py                  # Sequential workflow: Extractor → Analyzer
│   ├── Dockerfile / Dockerfile.api  # Agent & API containers
│   ├── extractor/
│   │   └── agent.py                 # PDF download + text extraction
│   └── analyzer/
│       └── agent.py                 # MCP-powered JDE cross-reference
│
├── jde-mcp-ube-analyzer/            # JDE MCP Server (git subtree)
│   └── src/
│       ├── index.ts                 # Server + transport setup
│       ├── tools/                   # 18 MCP tools (5 layers)
│       ├── services/ais-client.ts   # JDE AIS HTTP client
│       └── data/dictionary.json     # 110+ JDE table definitions
│
├── tests/                           # MCP + workflow tests
├── ingest/                          # Sample report PDFs
├── ARCHITECTURE.md                  # Full architecture document
├── TECH-STACK.md                    # Technology choices & rationale
├── DEPLOY-PLAN.md                   # Azure deployment steps
└── LESSONS.md                       # Lessons learned
```

---

## Workflow: How Reports Get Analyzed

```
JDE Batch Job → PDF → OCI Object Storage
                            │
                    JDE Orchestration
                    POST /v1/analyze
                            │
                    ┌───────▼───────┐
                    │ API Wrapper    │
                    │ (FastAPI)      │
                    └───────┬───────┘
                            │
              ┌─────────────▼─────────────┐
              │     ExtractorAgent         │
              │  1. Download PDF from OCI  │
              │  2. Extract text (pypdf)   │
              │  3. Produce structured JSON│
              │     (report type, company, │
              │      discrepancies)        │
              └─────────────┬─────────────┘
                            │
              ┌─────────────▼─────────────┐
              │     AnalyzerAgent          │
              │  1. Call MCP tools:        │
              │     - jde_ap_gl_integrity  │
              │     - jde_ap_voucher_query │
              │     - jde_gl_balance_query │
              │  2. Cross-reference PDF    │
              │     vs live JDE data       │
              │  3. Produce verified       │
              │     analysis + recs        │
              └─────────────┬─────────────┘
                            │
                    { checkerResponse,
                      analysisResponse }
                            │
                    Back to JDE Orchestration
                    → Email / Notification
```

---

## Documentation

| File | Purpose |
|------|---------|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Full architecture with diagrams and deployment topology |
| [TECH-STACK.md](docs/TECH-STACK.md) | Every technology, version, and why it's used |
| [DEPLOY-PLAN.md](docs/DEPLOY-PLAN.md) | Step-by-step Azure Container Apps deployment |
| [LESSONS.md](docs/LESSONS.md) | Lessons learned (Agent Framework, Docker, JDE, Git) |
| [PLAN.md](docs/PLAN.md) | Project log — all decisions and session history |
