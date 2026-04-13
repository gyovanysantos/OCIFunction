# JDE Integrity Report AI Analyzer — Architecture Document

> **Version**: 2.0 | **Date**: April 13, 2026 | **Status**: In Development  
> **Repository**: `OCIFunction/` | **Platform**: Azure (Foundry + Container Apps)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Solution Overview](#2-solution-overview)
3. [End-to-End Architecture](#3-end-to-end-architecture)
4. [JDE Orchestration Layer](#4-jde-orchestration-layer)
5. [Agent Descriptions](#5-agent-descriptions)
6. [JDE MCP Server](#6-jde-mcp-server)
7. [Workflow](#7-workflow)
8. [Deployment Topology](#8-deployment-topology)
9. [API Contract](#9-api-contract)
10. [Security & Authentication](#10-security--authentication)
11. [Codebase Structure](#11-codebase-structure)
12. [Future Enhancements](#12-future-enhancements)

---

## 1. Executive Summary

This solution adds **AI-powered analysis** to JD Edwards (JDE) Integrity Reports using a **multi-agent architecture**. When a scheduled JDE batch job produces an Integrity Report (PDF), a JDE Orchestration submits it for AI analysis. Two specialized agents work sequentially: the **ExtractorAgent** downloads and parses the PDF, and the **AnalyzerAgent** cross-references the findings against **live JDE data** via MCP tools — producing verified, actionable analysis.

**Key business value:**
- **Automated triage** — No human needs to open and read every Integrity Report.
- **Live data cross-reference** — The AnalyzerAgent queries JDE tables (F0411, F0902, F0901) via MCP to verify PDF findings against live data.
- **Expert-level analysis** — The AI understands JDE-specific concepts (subledger-to-GL reconciliation, GL offsets, error codes) and explains them in business terms.
- **Speed** — A 50+ page report is analyzed in under 60 seconds.

---

## 2. Solution Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        JD EDWARDS ENTERPRISEONE                        │
│                                                                         │
│  ┌──────────────┐    ┌──────────────────┐    ┌───────────────────────┐  │
│  │ Batch Job     │───>│ Report Generated │───>│ JDE Orchestration     │  │
│  │ (R047001A...) │    │ (PDF output)     │    │ (Service Requests)    │  │
│  └──────────────┘    └──────────────────┘    └──────────┬────────────┘  │
│                                                          │               │
└──────────────────────────────────────────────────────────┼───────────────┘
                                                           │
                                              REST POST /v1/analyze
                                                           │
┌──────────────────────────────────────────────────────────┼───────────────┐
│                     AZURE CONTAINER APPS                  │               │
│                                                           ▼               │
│  ┌────────────────┐    ┌───────────────┐    ┌──────────────────────────┐ │
│  │ API Wrapper     │───>│ Extractor     │───>│ Analyzer Agent          │ │
│  │ (FastAPI 8080)  │    │ Agent         │    │ (MCP-powered)           │ │
│  └────────────────┘    └──────┬────────┘    └──────────┬───────────────┘ │
│                               │                        │                 │
│                        ┌──────▼──────┐          ┌──────▼──────┐         │
│                        │ OCI Object  │          │ JDE MCP     │         │
│                        │ Storage     │          │ Server      │         │
│                        │ (PDF bucket)│          │ (port 3000) │         │
│                        └─────────────┘          └──────┬──────┘         │
│                                                        │                 │
│  Environment: jde-mcp-env | Region: East US            │                 │
└────────────────────────────────────────────────────────┼─────────────────┘
                                                         │
                                                  ┌──────▼──────┐
                                                  │ JDE AIS     │
                                                  │ REST API    │
                                                  │ F0411,F0902 │
                                                  │ F0901       │
                                                  └─────────────┘
```

---

## 3. End-to-End Architecture

### Flow Summary (Step by Step)

| Step | Component | Action |
|------|-----------|--------|
| **1** | JDE Batch Job | Scheduled job runs an Integrity Report (e.g., R047001A A/P to G/L Integrity). Output is a PDF. |
| **2** | JDE Orchestration | Uploads the PDF to OCI Object Storage, then sends `POST /v1/analyze` to the API Wrapper. |
| **3** | API Wrapper | Receives the request, builds the workflow, runs ExtractorAgent → AnalyzerAgent sequentially. |
| **4** | ExtractorAgent | Downloads PDF from OCI Object Storage, extracts text with `pypdf`, produces structured JSON (report type, company, discrepancies). |
| **5** | AnalyzerAgent | Receives structured JSON, calls MCP tools (`jde_ap_gl_integrity_check`, `jde_ap_voucher_query`, etc.) to cross-reference against live JDE data. |
| **6** | JDE MCP Server | Queries JDE tables (F0411, F0902, F0901) via AIS REST API and returns structured results. |
| **7** | Response | AnalyzerAgent produces verified analysis → API Wrapper returns `{"checkerResponse", "analysisResponse"}` to JDE. |
### Design Principles

- **Two-agent pipeline** — Separation of concerns: PDF extraction and data analysis are handled by specialized agents.
- **Live data verification** — The AnalyzerAgent queries JDE tables via MCP instead of using LLM-only inference.
- **MCP standard** — Open protocol for LLM tool calling; enables the AnalyzerAgent to query live JDE data.
- **Backward-compatible API** — The API Wrapper exposes the same `POST /v1/analyze` contract so JDE Orchestrations work unchanged.

---

## 4. JDE Orchestration Layer

The JDE Orchestration is configured inside JD Edwards EnterpriseOne and acts as the workflow engine:

| Request | Type | Purpose |
|---------|------|---------|
| **ServiceRequest1** | JDE Service | Runs the Integrity Report batch job. Returns the report name/description/job ID. |
| **ServiceRequest2** | JDE Service | Retrieves the generated PDF filename from the print queue. |
| **ConnectorRequest3** | REST Connector | Uploads the PDF to OCI Object Storage bucket via HTTP PUT. |
| **ConnectorRequest4** | REST Connector | Sends `POST /v1/analyze` to the API Wrapper with `{"object_name": "<filename>"}`. Receives `{checkerResponse, analysisResponse}`. |
| **ServiceRequest5** | JDE Service | Post-processing — routes the AI analysis (email, notification, work order). |

---

## 5. Agent Descriptions

| Agent | Purpose | Tools | Technology |
|-------|---------|-------|------------|
| **ExtractorAgent** | Downloads PDF from OCI Object Storage, extracts text with `pypdf`, uses LLM to produce structured JSON (report type, company, discrepancies, accounts) | `download_and_extract_pdf` (FunctionTool) | Python 3.12, OCI SDK, pypdf |
| **AnalyzerAgent** | Receives structured extraction, queries live JDE data via MCP tools, cross-references PDF findings, produces verified analysis with recommendations | 4 MCP tools (see §6) | Python 3.12, MCPStreamableHTTPTool → JDE MCP Server |

**ExtractorAgent output schema:**
```json
{
  "report_type": "R047001A",
  "has_data": true,
  "company": "00060",
  "fiscal_year": 25,
  "periods": [1, 2, 3],
  "discrepancies": [
    {
      "gl_offset": "PA",
      "account": "1110",
      "ap_amount": 123456.78,
      "gl_amount": 123400.00,
      "difference": 56.78
    }
  ]
}
```

---

## 6. JDE MCP Server

The JDE MCP Server (`jde-mcp-server-template/`) is a TypeScript service that exposes JDE data as MCP tools. It queries JDE EnterpriseOne via the AIS REST API.

### 5-Layer Tool Architecture

| Layer | Tools | Purpose |
|-------|-------|---------|
| **Layer 0** | `jde_discover_table`, `jde_search_tables` | Dynamic discovery from JDE |
| **Layer 1** | `jde_dictionary_search`, `jde_dictionary_list`, `jde_dictionary_table` | JDE table metadata lookup |
| **Layer 2** | SO CRUD: `jde_sales_order_inquiry`, `jde_create_sales_order`, `jde_update_sales_order`, `jde_add_sales_order_line`, `jde_cancel_sales_order` | Business-focused Sales Order operations |
| **Layer 2.5** | **AP/GL Integrity**: `jde_ap_voucher_query`, `jde_gl_balance_query`, `jde_gl_detail_query`, `jde_ap_gl_integrity_check` | R047001A integrity analysis |
| **Layer 3** | `jde_customer_lookup`, `jde_item_check` | Supporting lookups |
| **Layer 4** | `jde_query_table`, `jde_call_orchestration` | Generic fallback tools |

### Key Integrity Tools

| Tool | Table | Purpose |
|------|-------|---------|
| `jde_ap_voucher_query` | F0411 | Query AP vouchers by company, supplier, GLPT, dates |
| `jde_gl_balance_query` | F0902 | Query GL balances by account, ledger type, fiscal year |
| `jde_gl_detail_query` | F0901 | Drill-down into individual GL journal entries |
| `jde_ap_gl_integrity_check` | F0411 + F0902 | **Programmatic R047001A** — sums F0411 by GLPT, compares against F0902 balances |

---

## 7. Workflow

The workflow is a **sequential graph** built with `WorkflowBuilder`:

```
Input (object_name) → ExtractorAgent → structured JSON → AnalyzerAgent → final report
```

1. **Input**: User provides `object_name` (PDF filename in OCI bucket)
2. **ExtractorAgent**: Calls `download_and_extract_pdf` tool → LLM produces structured JSON extraction
3. **AnalyzerAgent**: Receives JSON → calls `jde_ap_gl_integrity_check` and other MCP tools → cross-references PDF findings against live data → produces verified analysis
4. **Output**: Structured analysis with confirmed/resolved/new issues and recommendations

---

## 8. Deployment Topology

| Component | Platform | Transport | Auth | URL |
|-----------|----------|-----------|------|-----|
| **API Wrapper** | Azure Container Apps (`jde-integrity-api`) | HTTP POST `/v1/analyze` | Static Azure AD token (see caveat below) | `https://jde-integrity-api.bluedesert-fb732cac.eastus.azurecontainerapps.io` |
| **JDE MCP Server** | Azure Container Apps (`jde-mcp-integrity`) | HTTP POST `/mcp` | Unauthenticated (public) | `https://jde-mcp-integrity.bluedesert-fb732cac.eastus.azurecontainerapps.io` |
| **JDE AIS** | On-prem / OCI | HTTP REST | Basic Auth (via AIS connector) | Configured via env vars |
| **OCI Object Storage** | OCI (us-phoenix-1) | OCI SDK | Base64-encoded PEM key (Container App secret) | — |

**Azure Infrastructure**:
- ACR: `acrjdemcppo.azurecr.io`
- Container Apps Environment: `jde-mcp-env` (East US)
- Resource Group: `rg-hackathon-2603` (subscription: CLSandbox2)

### Auth Caveat — Foundry Token

The API wrapper container authenticates to Azure AI Foundry using a **static Azure AD token** (`FOUNDRY_TOKEN` env var) that expires in ~1 hour. A permanent fix requires an Owner/User Access Administrator to assign the `Azure AI User` role to the managed identity.

### OCI Auth in Container

The ExtractorAgent authenticates to OCI Object Storage using env vars instead of `~/.oci/config`:

| Env Var | Source |
|---------|--------|
| `OCI_USER` | OCI config `user=` |
| `OCI_FINGERPRINT` | OCI config `fingerprint=` |
| `OCI_TENANCY` | OCI config `tenancy=` |
| `OCI_REGION` | OCI config `region=` |
| `OCI_KEY_CONTENT` | PEM key file (base64-encoded) |

---

## 9. API Contract

### Request

```
POST /v1/analyze
Content-Type: application/json

{
  "object_name": "R047001A_ZJDE0001_588_PDF.pdf",
  "prompt": "Analyze this Integrity Report. Identify all problems and recommend fixes."
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `object_name` | string | **Yes** | — | Filename of the PDF in the OCI Object Storage bucket |
| `prompt` | string | No | Default prompt | Custom analysis instruction |

### Response (Success — report has data)

```json
{
  "checkerResponse": "Yes",
  "analysisResponse": "<table width=\"100%\" ...>...JDE-safe HTML email body...</table>"
}
```

### Response (Success — empty report)

```json
{
  "checkerResponse": "No",
  "analysisResponse": "<table width=\"100%\" ...>...No discrepancies found...</table>"
}
```

---

## 10. Security & Authentication

| Layer | Method |
|-------|--------|
| **API Wrapper → Foundry** | `DefaultAzureCredential` (async) — managed identity in production |
| **ExtractorAgent → OCI** | API key auth via env vars (base64-encoded PEM key) |
| **MCP Server → JDE AIS** | Basic Auth (username/password via env vars) |
| **JDE → API Wrapper** | HTTPS REST (JDE Connector) |

---

## 11. Codebase Structure

```
OCIFunction/
├── docker-compose.yml               # Local dev: 4 services (mcp, extractor, analyzer, api)
├── .env.example                     # Root env template for docker-compose
│
├── agents/                          # Foundry Multi-Agent System
│   ├── api.py                       # FastAPI wrapper (POST /v1/analyze, GET /health)
│   ├── app.py                       # Workflow entry point (sequential orchestration)
│   ├── workflow.py                  # Sequential workflow: Extractor → Analyzer
│   ├── Dockerfile                   # Workflow container (python:3.12-slim, port 8088)
│   ├── Dockerfile.api               # API wrapper container (python:3.12-slim, port 8080)
│   ├── requirements.txt             # Agent deps (agent-framework, azure-identity, oci, pypdf)
│   ├── requirements-api.txt         # API deps (fastapi, uvicorn + agent deps)
│   ├── agent.yaml                   # Foundry agent metadata
│   ├── extractor/
│   │   ├── agent.py                 # ExtractorAgent: PDF download + text extraction
│   │   ├── app.py                   # Standalone HTTP entry point (port 8088)
│   │   ├── Dockerfile               # Container (python:3.12-slim)
│   │   └── requirements.txt         # Deps: oci, pypdf, agent-framework
│   └── analyzer/
│       ├── agent.py                 # AnalyzerAgent: MCP tools + cross-reference
│       ├── app.py                   # Standalone HTTP entry point (port 8088)
│       ├── Dockerfile               # Container (python:3.12-slim)
│       └── requirements.txt         # Deps: agent-framework (no oci/pypdf)
│
├── jde-mcp-server-template/         # JDE MCP Server (git subtree)
│   └── src/
│       ├── index.ts                 # Tool registration + HTTP transport
│       ├── tools/integrity.ts       # 4 AP/GL integrity tools
│       ├── schemas/tools.ts         # Zod schemas for all tool inputs
│       ├── services/ais-client.ts   # JDE AIS HTTP client
│       └── data/dictionary.json     # JDE table metadata (110+ tables)
│
├── tests/                           # Test files
├── ingest/                          # Sample report PDFs for testing
├── ARCHITECTURE.md                  # This document
├── TECH-STACK.md                    # Technology choices and rationale
├── PLAN.md                          # Project log and decision record
├── DEPLOY-PLAN.md                   # Azure Container Apps deployment steps
└── LESSONS.md                       # Lessons learned
```

---

## 12. Future Enhancements

| Enhancement | Description | Complexity |
|-------------|-------------|------------|
| **Managed Identity RBAC** | Assign `Azure AI User` role to Container App managed identity for permanent auth | Low |
| **Multi-report batch analysis** | Accept multiple object names in a single call | Medium |
| **Historical trend tracking** | Store analysis results to track issue trends over time | Medium |
| **Email/Teams notifications** | Automatically notify teams when critical issues are found | Low |
| **Support for non-PDF formats** | Extend to CSV or JSON report outputs from JDE | Low |

---

*Architecture documented on April 13, 2026. MCP deployed to Azure Container Apps.*
