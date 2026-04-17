# JDE Integrity Report AI Analyzer — Architecture Document

> **Version**: 2.0 | **Date**: April 12, 2026 | **Status**: In Development  
> **Repository**: `OCIFunction/` | **Region**: us-phoenix-1 (OCI)  
> **Multi-Agent**: OCI ADK agents with MCP-powered JDE verification

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Solution Overview](#2-solution-overview)
3. [End-to-End Architecture](#3-end-to-end-architecture)
4. [JDE Orchestration Layer](#4-jde-orchestration-layer)
5. [OCI Infrastructure Components](#5-oci-infrastructure-components)
6. [Security & IAM Policies](#6-security--iam-policies)
7. [Codebase Structure](#7-codebase-structure)
8. [API Contract](#8-api-contract)
9. [Cost Considerations](#9-cost-considerations)
10. [Scalability & Limits](#10-scalability--limits)
11. [Future Enhancements](#11-future-enhancements)
12. [Multi-Agent Architecture](#12-multi-agent-architecture)
    - 12.1 [Architecture Diagram](#121-architecture-diagram)
    - 12.2 [Agent Descriptions](#122-agent-descriptions)
    - 12.3 [JDE MCP Server Enhancement](#123-jde-mcp-server-enhancement)
    - 12.4 [Workflow](#124-workflow)
    - 12.5 [Deployment Topology](#125-deployment-topology)
    - 12.6 [Codebase Structure](#126-codebase-structure)

---

## 1. Executive Summary

This solution adds **AI-powered analysis** to JD Edwards (JDE) Integrity Reports. When a scheduled JDE batch job produces an Integrity Report (PDF), a JDE Orchestration automatically submits it for AI analysis. The AI reads the full report, determines whether it contains actionable data, and — if it does — produces a structured analysis that identifies **problems, explains their JDE context, and recommends corrective actions**.

**Key business value:**
- **Automated triage** — No human needs to open and read every Integrity Report to decide if action is needed.
- **Expert-level analysis** — The AI understands JDE-specific concepts (unposted batches, subledger-to-GL reconciliation, error codes) and explains them in business terms.
- **Speed** — A 50+ page report is analyzed in under 30 seconds.
- **Cost-efficient** — Pay only when reports are actually being analyzed.

---

## 2. Solution Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        JD EDWARDS ENTERPRISEONE                        │
│                                                                         │
│  ┌──────────────┐    ┌──────────────────┐    ┌───────────────────────┐  │
│  │ Batch Job     │───>│ Report Generated │───>│ JDE Orchestration     │  │
│  │ (R007011,     │    │ (PDF output)     │    │ (5 Service Requests)  │  │
│  │  R047001A...) │    │                  │    │                       │  │
│  └──────────────┘    └──────────────────┘    └──────────┬────────────┘  │
│                                                          │               │
└──────────────────────────────────────────────────────────┼───────────────┘
                                                           │
                                              REST POST /v1/analyze
                                                           │
┌──────────────────────────────────────────────────────────┼───────────────┐
│                     ORACLE CLOUD INFRASTRUCTURE (OCI)     │               │
│                                                           ▼               │
│  ┌────────────────┐    ┌──────────────────────┐                          │
│  │ API Container   │───>│ ExtractorAgent       │                          │
│  │ (FastAPI :8080) │    │ (PDF→structured JSON)│                          │
│  └────────────────┘    └──────────┬───────────┘                          │
│                                   │                                      │
│                          ┌────────▼────────┐                             │
│                          │ AnalyzerAgent    │                             │
│                          │ (MCP bridge)     │                             │
│                          └────────┬────────┘                             │
│                                   │                                      │
│                          ┌────────▼────────┐    ┌──────────────────┐     │
│                          │ JDE MCP Server   │───>│ JDE AIS REST API │     │
│                          │ (Node.js :3000)  │    │ F0411,F0902,F0901│     │
│                          └─────────────────┘    └──────────────────┘     │
│                                                                          │
│  Compartment: jdee1 | Region: us-phoenix-1                               │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 3. End-to-End Architecture

### Flow Summary (Step by Step)

| Step | Component | Action |
|------|-----------|--------|
| **1** | JDE Batch Job | Scheduled job runs an Integrity Report (e.g., R007011 Unposted Batches, R047001A A/P to G/L Integrity). Output is a PDF. |
| **2** | JDE Orchestration | A JDE Orchestration is triggered. It executes 5 sequential service/connector requests (see Section 4). |
| **3** | JDE → Object Storage | The Orchestration uploads the report PDF to an OCI Object Storage bucket via a Connector Request (REST PUT). |
| **4** | JDE → API | The Orchestration sends a REST `POST /v1/analyze` to the API container with the PDF filename. |
| **5** | API → ExtractorAgent | The API triggers the ADK workflow. ExtractorAgent downloads the PDF from OCI Object Storage, extracts text with pypdf, and produces structured JSON. |
| **6** | ExtractorAgent → AnalyzerAgent | The structured extraction (report type, discrepancies, accounts) is passed to the AnalyzerAgent. |
| **7** | AnalyzerAgent → MCP Server | The AnalyzerAgent calls MCP bridge tools to query live JDE data (F0411, F0902, F0901) via the JDE MCP Server. |
| **8** | MCP Server → JDE AIS | The MCP server queries JDE AIS REST API to retrieve actual AP/GL data for cross-referencing. |
| **9** | AnalyzerAgent | Cross-references PDF findings against live JDE data, confirming/resolving discrepancies. |
| **10** | Response | The API returns `{"checkerResponse", "analysisResponse"}` with JDE-safe HTML back to the JDE Orchestration. |
| **11** | JDE Orchestration | The Orchestration receives the AI analysis and can route it (email, notification, JDE queue, etc.). |

### Design Principles

- **Multi-agent separation** — ExtractorAgent handles PDF processing, AnalyzerAgent handles JDE data cross-referencing. Each agent has a focused responsibility.
- **Live data verification** — Unlike simple LLM-only inference, the AnalyzerAgent queries live JDE systems via MCP to verify findings from the PDF.
- **Deterministic workflow** — Plain Python sequential `agent.run()` calls ensure predictable execution order.
- **Deterministic checker** — The "does this report have data?" decision is code-based (text length check), not LLM-based. This eliminates false positives from AI hallucination.

---

## 4. JDE Orchestration Layer

The JDE Orchestration is configured inside JD Edwards EnterpriseOne and acts as the workflow engine. It executes **5 sequential steps** per report:

| Request | Type | Purpose |
|---------|------|---------|
| **ServiceRequest1** | JDE Service | Runs the Integrity Report batch job. Returns the report name, description, and job ID. |
| **ServiceRequest2** | JDE Service | Retrieves the generated PDF filename from the print queue (e.g., `R047001A_SCH0001_32089_PDF.pdf`). |
| **ConnectorRequest3** | REST Connector | Uploads (HTTP PUT) the PDF file to the OCI Object Storage bucket. Returns HTTP 200 on success. |
| **ConnectorRequest4** | REST Connector | Sends `POST /v1/analyze` to the OCI API Gateway with `{"object_name": "<filename>"}`. Receives back the `checkerResponse` and `analysisResponse`. |
| **ServiceRequest5** | JDE Service | Post-processing — routes the AI analysis result (e.g., stores it, sends email notification, creates a JDE work order). |

### Communication Protocol

- **JDE → OCI**: Standard HTTPS REST calls via JDE Connector (built-in JDE EnterpriseOne capability).
- **Authentication**: The API Gateway endpoint is currently unauthenticated (suitable for internal/VPN access). Can be secured with API keys or OAuth2 for production hardening.
- **Data format**: JSON request/response. The PDF binary is uploaded separately to Object Storage (ConnectorRequest3), then referenced by filename in the analysis call (ConnectorRequest4).

### Example Orchestration Output

```json
{
  "ServiceRequest1": {
    "submitted": true,
    "output": { "1": "R047001A_SCH0001", "2": "A/P To G/L Integrity by Offset Account" }
  },
  "ServiceRequest2": {
    "output": { "3": "R047001A_SCH0001_32089_PDF.pdf" }
  },
  "ConnectorRequest3": {
    "Response Status": 200
  },
  "ConnectorRequest4": {
    "checkerResponse": "Yes",
    "analysisResponse": "This report indicates significant discrepancies between A/P subledger (F0411) and G/L (F0902)..."
  },
  "ServiceRequest5": {
    "success": true
  }
}
```

---

## 5. OCI Infrastructure Components

### 5.1 Object Storage Bucket

| Property | Value |
|----------|-------|
| Bucket Name | `OBJECTSTORAGE` |
| Namespace | `idxoqn0ijjyv` |
| Tier | Standard |
| Region | us-phoenix-1 |
| Purpose | Stores Integrity Report PDFs uploaded by JDE Orchestrations |

JDE uploads each report PDF to this bucket before requesting analysis. The ExtractorAgent reads from this bucket using the OCI SDK.

### 5.2 API Gateway

Two gateways provide REST access:

| Gateway | Type | Hostname | Use Case |
|---------|------|----------|----------|
| `JDE_API_Gateway_Open` | **Public** | `jfiidvdcmm4d2oqweow44nsovq.apigateway.us-phoenix-1.oci.customer-oci.com` | External/dev access, JDE Orchestrations over internet |
| `JDE_API_Gateway` | **Private** | `daa6bnvhau6ufxbsf7n3my4b4y.apigateway.us-phoenix-1.oci.customer-oci.com` | JDE servers on the same VCN (traffic stays internal) |

Both gateways have an `AgentAnalyze` deployment with:
- **Path prefix**: `/v1`
- **Route**: `POST /analyze`
- **Full URL**: `https://<gateway-hostname>/v1/analyze`

### 5.3 OCI GenAI Agents Service

| Property | Value |
|----------|-------|
| Compartment | jdee1 |
| Region | us-phoenix-1 |
| ExtractorAgent | `EXTRACTOR_AGENT_ENDPOINT_ID` |
| AnalyzerAgent | `ANALYZER_AGENT_ENDPOINT_ID` |
| Auth | `api_key` (local dev), `instance_principal` (OCI compute) |

---

## 6. Security & IAM Policies

### 6.1 Authentication Model

The agents use **OCI API Key** authentication for local development and **Instance Principal** for OCI compute deployments. No hardcoded credentials in the code.

### 6.2 IAM Policies

| Policy Name | Statement | Purpose |
|-------------|-----------|---------|
| `agent-functions-policy` | `Allow dynamic-group agent-functions-dg to manage generative-ai-family in compartment jdee1` | Access OCI GenAI Inference API |
| `fn-objectstorage-read` | `Allow dynamic-group agent-functions-dg to read object-family in compartment jdee1` | Download PDFs from Object Storage |
| `apigw-functions-policy` | `Allow any-user to use functions-family in compartment jdee1 where ALL {request.principal.type = 'ApiGateway', ...}` | API Gateway routing |

### 6.3 Network Security

| Layer | Configuration |
|-------|--------------|
| **Public API Gateway** | HTTPS only (TLS 1.2+). No authentication currently configured — suitable for internal networks or VPN. |
| **Private API Gateway** | Accessible only from within the VCN (`PrivatRegSub` subnet 10.9.4.0/24). Used when JDE servers are on the same OCI VCN. |
| **Object Storage** | Private bucket. Accessible only via IAM-authenticated OCI SDK calls. No public access. |
| **GenAI Service** | OCI service endpoint. Accessed via OCI SDK. Traffic stays on OCI backbone. |

### 6.4 Security Recommendations for Production

| Recommendation | Priority | Details |
|----------------|----------|---------|
| Add API Gateway authentication | **High** | Add API key validation or OAuth2/JWT to the public gateway to prevent unauthorized access. |
| Enable API Gateway rate limiting | Medium | Protect against abuse and control costs. |
| Enable OCI Audit logging | Medium | Track all API Gateway invocations for compliance. |

---

## 7. Codebase Structure

All source code resides in the `OCIFunction/` directory:

```
OCIFunction/
├── docker-compose.yml               # Local dev: 2 services (mcp, api)
├── .env.example                     # Root env template for docker-compose
│
├── agents/                          # OCI ADK Multi-Agent System
│   ├── api.py                       # FastAPI wrapper (POST /v1/analyze, GET /health)
│   ├── workflow.py                  # ADK deterministic workflow: Extractor → Analyzer
│   ├── mcp_bridge.py                # ADK @tool functions → MCP server via HTTP (JSON-RPC)
│   ├── Dockerfile.api               # API container (python:3.12-slim, port 8080)
│   ├── requirements.txt             # Python deps (oci[adk], httpx, fastapi, pypdf)
│   ├── extractor/
│   │   └── agent.py                 # ExtractorAgent: PDF download + text extraction (@tool)
│   ├── analyzer/
│   │   └── agent.py                 # AnalyzerAgent instructions (MCP tools in mcp_bridge)
│   └── __init__.py
│
├── jde-mcp-server-template/         # JDE MCP Server (git subtree)
│   └── src/
│       ├── tools/integrity.ts       # 4 AP/GL integrity tools
│       ├── schemas/tools.ts         # Zod schemas (integrity + generic)
│       ├── data/dictionary.json     # F0411, F0902, F0901
│       └── index.ts                 # Tool registration
│
├── tests/                           # Integration tests
│   ├── test_mcp.py                  # MCP server tests
│   └── test_workflow_local.py       # Local workflow test
│
├── ARCHITECTURE.md                  # This document
├── PLAN.md                          # Project log and decision record
└── TECH-STACK.md                    # Technology inventory
```

---

## 8. API Contract

### Request

```
POST /v1/analyze
Content-Type: application/json

{
  "object_name": "R007011_CAN0001_32083_PDF.pdf",
  "prompt": "Analyze this Integrity Report. Identify all problems and recommend fixes."
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `object_name` | string | **Yes** | — | Filename of the PDF in the Object Storage bucket |
| `prompt` | string | No | `"Analyze this Integrity Report. Identify all problems and recommend fixes."` | Custom analysis instruction |

### Response (Success — report has data)

```json
{
  "checkerResponse": "Yes",
  "analysisResponse": "<table width=\"100%\" ...>...JDE-safe HTML email body...</table>"
}
```

The `analysisResponse` field contains **JDE-safe HTML** (compatible with `CL001_SimpleEmailJob`):
- Zero `style=` attributes — uses only `bgcolor`, `width`, `align`, `cellpadding`, `cellspacing`
- Text styling via `<font color=\"...\" size=\"...\">` and `<b>`/`<i>` tags
- No document-level tags (`<html>`, `<head>`, `<body>`, `<style>`)
- No `<span>`, `<code>`, `<pre>` tags
- Markdown from the LLM is converted to HTML, then sanitized by `_sanitize_html_for_jde()`

### Response (Success — empty report)

```json
{
  "checkerResponse": "No",
  "analysisResponse": "<table width=\"100%\" ...>...No discrepancies found...</table>"
}
```

### Response (Error — file not found)

```json
{
  "error": "Object 'nonexistent.pdf' not found in bucket"
}
```

---

## 9. Cost Considerations

### 9.1 OCI Services Pricing Model

All components use **pay-per-use** pricing. There are no fixed monthly commitments required.

| Service | Pricing Model | Key Metric | Estimated Cost |
|---------|--------------|------------|----------------|
| **OCI Container Instances** | Per compute time | vCPU + memory hours | Depends on instance size and uptime |
| **OCI Object Storage** | Per GB stored + requests | $0.0255/GB/month (Standard) + $0.0034/10K requests | Minimal. Report PDFs are small (< 5 MB each). |
| **OCI API Gateway** | Per million API calls | $3.00 per million calls | Minimal at expected volumes. |
| **OCI GenAI (On-Demand)** | Per token (input + output) | Varies by model. | Primary cost driver. See below. |

### 9.2 GenAI Cost Estimation

The GenAI inference cost depends on document size (input tokens) and analysis length (output tokens).

| Report Type | Pages | Input Tokens (est.) | Output Tokens (est.) | Cost per Analysis (est.) |
|------------|-------|--------------------|--------------------|------------------------|
| Small report (R047001A) | 1-2 | ~500 | ~800 | < $0.001 |
| Medium report (R007011) | 10-30 | ~20,000 | ~800 | ~$0.002 - $0.005 |
| Large report | 50+ | ~50,000 | ~800 | ~$0.005 - $0.015 |

> **Note**: OCI GenAI on-demand pricing for Google Gemini models through OCI may vary. Check the [OCI GenAI Pricing page](https://www.oracle.com/cloud/pricing/#generative-ai) for current rates. OCI often provides generous free-tier allowances for GenAI services.

### 9.3 Monthly Cost Scenarios

| Scenario | Reports/Month | Estimated Monthly Cost |
|----------|---------------|----------------------|
| **Low volume** | 50 reports | $0.25 - $1.00 |
| **Medium volume** | 500 reports | $2.50 - $10.00 |
| **High volume** | 5,000 reports | $25.00 - $100.00 |

> These estimates include Object Storage, API Gateway, and GenAI inference. The dominant cost is GenAI inference.

### 9.4 Cost Optimization Levers

| Strategy | Impact |
|----------|--------|
| **Checker skips empty reports** | Reports with no data (< 300 chars of text) skip the GenAI call entirely. Zero inference cost for empty reports. |
| **System prompt word cap** | Limits output tokens to ~850 words, preventing unnecessarily verbose (and expensive) responses. |
| **On-demand serving** | No idle cost. You only pay when a report is actually being analyzed. |
| **Gemini Flash (not Pro)** | Flash variant is significantly cheaper than Pro while providing excellent analysis quality for this use case. |

---

## 10. Scalability & Limits

| Dimension | Limit | Notes |
|-----------|-------|-------|
| Concurrent function invocations | Default: 30 (adjustable) | OCI Functions scales automatically. Request a limit increase for higher concurrency. |
| Function timeout | 300 seconds | Sufficient for 50+ page reports. |
| Function memory | 1024 MB | PDF extraction + text processing fits comfortably. |
| GenAI context window | ~1,000,000 tokens | Can handle reports up to ~750,000 words (far exceeding any Integrity Report). |
| Max output tokens | 8,192 (configured) | Enough for ~6,000 words of analysis. System prompt limits to ~850 words. |
| Object Storage | Virtually unlimited | Standard OCI Object Storage. No practical limit on number of report PDFs. |
| API Gateway throughput | 1,000 requests/second (default) | Far exceeds expected Integrity Report volumes. |

---

## 11. Future Enhancements

| Enhancement | Description | Complexity |
|-------------|-------------|------------|
| **API Gateway authentication** | Add API key or OAuth2 to the public endpoint. | Low |
| **Multi-report batch analysis** | Accept multiple object names in a single call for batch processing. | Medium |
| **Historical trend tracking** | Store analysis results in an OCI Autonomous Database to track issue trends over time. | Medium |
| **Email/Teams notifications** | Automatically notify responsible teams when critical issues are found. | Low |
| **Support for non-PDF formats** | Extend to CSV or JSON report outputs from JDE. | Low |
| **Custom prompt per report type** | Different system prompts for R007011 (Unposted Batches) vs R047001A (A/P to G/L) etc. | Low |
| **OCI Events integration** | Trigger analysis automatically when a PDF is uploaded to the bucket (event-driven, no Orchestration needed). | Medium |

---

*This document describes the architecture as of April 12, 2026.*

---

## 12. Multi-Agent Architecture

### 12.1 Architecture Diagram

```
                    ┌───────────────────────────────┐
                    │   OCI GenAI Agents Service     │
                    │   (us-phoenix-1 / jdee1)       │
                    │   ADK Deterministic Workflow    │
                    └─────────────┬─────────────────┘
                                  │
                     ┌────────────┼─────────────┐
                     │                          │
              ┌──────▼──────┐           ┌───────▼───────┐
              │  Extractor  │──struct──▶│   Analyzer    │
              │   Agent     │  JSON     │     Agent     │
              │ (PDF→data)  │           │(MCP bridge)   │
              └──────┬──────┘           └───────┬───────┘
                     │                          │
              ┌──────▼──────┐           ┌───────▼───────┐
              │ OCI Object  │           │ MCP Bridge    │
              │  Storage    │           │ (httpx→MCP)   │
              │ (bucket)    │           └───────┬───────┘
              └─────────────┘                   │
                                         ┌──────▼──────┐
                                         │  JDE MCP    │
                                         │  Server     │
                                         │ (container) │
                                         └──────┬──────┘
                                                │
                                         ┌──────▼──────┐
                                         │  JDE AIS    │
                                         │ REST API    │
                                         │ F0411,F0902 │
                                         │ F0901       │
                                         └─────────────┘
```

### 12.2 Agent Descriptions

| Agent | Purpose | Tools | Technology |
|-------|---------|-------|------------|
| **ExtractorAgent** | Downloads PDF from OCI Object Storage, extracts text with `pypdf`, uses LLM to produce structured JSON (report type, company, discrepancies, accounts) | `download_and_extract_pdf` (ADK `@tool`) | Python, OCI SDK, pypdf, OCI ADK |
| **AnalyzerAgent** | Receives structured extraction, queries live JDE data via MCP bridge tools, cross-references PDF findings, produces verified analysis with recommendations | 4 MCP bridge `@tool` functions (see §13.3) | Python, OCI ADK, httpx → MCP Server |

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

### 12.3 JDE MCP Server Enhancement

The existing JDE MCP server (TypeScript, `jde-mcp-server-template/`) was enhanced with 4 new **curated integrity tools** and 3 new table definitions:

**New Tables (dictionary.json v1.2.0):**

| Table | Description | Key Columns |
|-------|-------------|-------------|
| **F0411** | A/P Ledger (voucher pay items) | DOC, DCT, AN8, AG, AAP, GLPT, AID, FY, PN |
| **F0902** | Account Balances (period amounts) | AID, OBJ, SUB, LT, FY, AN01-AN14, BORG |
| **F0901** | Account Ledger (journal entries) | AID, DOC, DCT, AA, DGJ, AN8, JELN |

**New MCP Tools (integrity.ts):**

| Tool | Table | Purpose |
|------|-------|---------|
| `jde_ap_voucher_query` | F0411 | Query AP vouchers by company, supplier, GLPT, dates |
| `jde_gl_balance_query` | F0902 | Query GL balances by account, ledger type, fiscal year |
| `jde_gl_detail_query` | F0901 | Drill-down into individual GL journal entries |
| `jde_ap_gl_integrity_check` | F0411 + F0902 | **Programmatic R047001A** — sums F0411 by GLPT, compares against F0902 balances |

The `jde_ap_gl_integrity_check` tool is the centerpiece — it performs the same reconciliation logic as the JDE R047001A report, but programmatically, returning `{ matches, discrepancies, summary }`.

### 12.4 Workflow

The workflow is a **deterministic pipeline** using OCI ADK — plain Python sequential `agent.run()` calls:

```
Input (object_name) → ExtractorAgent.run() → structured JSON → AnalyzerAgent.run() → final report
```

1. **Input**: User provides `object_name` (PDF filename in OCI bucket)
2. **ExtractorAgent**: Calls `download_and_extract_pdf` tool → LLM produces structured JSON extraction
3. **has_data check**: If PDF has no data, skip analysis and return early
4. **AnalyzerAgent**: Receives JSON → calls `jde_ap_gl_integrity_check` and other MCP bridge tools → cross-references PDF findings against live data → produces verified analysis
5. **Output**: Structured analysis with confirmed/resolved/new issues and recommendations

**ADK Pattern**: `AgentClient` → 2 `Agent` instances → `setup()` (once) → sequential `run()` calls. The agent loop (LLM reasoning + tool selection) runs on OCI GenAI Agents Service. When a tool needs to be called, control returns to the local ADK, which executes the function and submits the result back.

### 12.5 Deployment Topology

| Component | Platform | Transport | Auth | Notes |
|-----------|----------|-----------|------|-------|
| **API + Agents** | Container (OCI or Docker Compose) | HTTP POST `/v1/analyze` | OCI `api_key` or `instance_principal` | Runs ExtractorAgent + AnalyzerAgent in-process via OCI ADK |
| **JDE MCP Server** | Container (same compose or separate) | HTTP POST `/mcp` | Unauthenticated | MCP StreamableHTTP with JSON responses |
| **OCI GenAI Agents** | OCI GenAI Agents Service (us-phoenix-1) | ADK ↔ Agent Endpoint | OCI auth (via AgentClient) | 2 agent endpoints in jdee1 compartment |
| **JDE AIS** | On-prem / OCI | HTTP REST | Basic Auth (via AIS connector) | Configured via env vars |
| **OCI Object Storage** | OCI (us-phoenix-1) | OCI SDK | API key / instance principal | PDF storage bucket |

**OCI Infrastructure (jdee1 compartment, us-phoenix-1)**:
- GenAI Agent Endpoints: `EXTRACTOR_AGENT_ENDPOINT_ID`, `ANALYZER_AGENT_ENDPOINT_ID`
- Object Storage Bucket: `OBJECTSTORAGE` (namespace: `idxoqn0ijjyv`)
- ADK auth: `api_key` for local dev, `instance_principal` for OCI compute

#### OCI Auth in Container

| Env Var | Purpose |
|---------|---------|
| `OCI_AUTH_TYPE` | `api_key` (local dev) or `instance_principal` (OCI compute) |
| `OCI_REGION` | `us-phoenix-1` |
| `OCI_PROFILE` | OCI config profile (default: `DEFAULT`) |
| `EXTRACTOR_AGENT_ENDPOINT_ID` | OCID of ExtractorAgent endpoint |
| `ANALYZER_AGENT_ENDPOINT_ID` | OCID of AnalyzerAgent endpoint |
| `MCP_SERVER_URL` | MCP server URL (e.g. `http://mcp:3000/mcp`) |

### 12.6 Codebase Structure

```
OCIFunction/
├── docker-compose.yml               # Local dev: 2 services (mcp, api)
├── .env.example                     # Root env template for docker-compose
│
├── agents/                          # OCI ADK Multi-Agent System
│   ├── api.py                       # FastAPI wrapper (POST /v1/analyze, GET /health)
│   ├── workflow.py                  # ADK deterministic workflow: Extractor → Analyzer
│   ├── mcp_bridge.py                # ADK @tool functions → MCP server via HTTP (JSON-RPC)
│   ├── Dockerfile.api               # API container (python:3.12-slim, port 8080)
│   ├── requirements.txt             # Python deps (oci[adk], httpx, fastapi, pypdf)
│   ├── extractor/
│   │   └── agent.py                 # ExtractorAgent: PDF download + text extraction (@tool)
│   ├── analyzer/
│   │   └── agent.py                 # AnalyzerAgent instructions (MCP tools in mcp_bridge)
│   └── __init__.py
│
├── jde-mcp-server-template/         # JDE MCP Server (git subtree)
│   └── src/
│       ├── tools/integrity.ts       # 4 AP/GL integrity tools
│       ├── schemas/tools.ts         # Zod schemas (integrity + generic)
│       ├── data/dictionary.json     # F0411, F0902, F0901
│       └── index.ts                 # Tool registration
│
├── tests/                           # Integration tests
│   ├── test_mcp.py                  # MCP server tests
│   └── test_workflow_local.py       # Local workflow test
│
├── ARCHITECTURE.md                  # This document
├── PLAN.md                          # Project log and decision record
└── TECH-STACK.md                    # Technology inventory
```

---

*Architecture documented on April 12, 2026.*
