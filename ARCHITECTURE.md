# JDE Integrity Report AI Analyzer — Architecture Document

> **Version**: 2.0 | **Date**: April 11, 2025 | **Status**: In Development  
> **Repository**: `OCIFunction/` | **Regions**: us-phoenix-1 (OCI), Azure (Foundry)  
> **v1.0 (OCI Function)**: Production — direct LLM inference fallback  
> **v2.0 (Multi-Agent)**: Development — Foundry agents with MCP-powered JDE verification

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Solution Overview](#2-solution-overview)
3. [End-to-End Architecture](#3-end-to-end-architecture)
4. [JDE Orchestration Layer](#4-jde-orchestration-layer)
5. [OCI Function — The Analysis Engine](#5-oci-function--the-analysis-engine)
6. [OCI Infrastructure Components](#6-oci-infrastructure-components)
7. [Security & IAM Policies](#7-security--iam-policies)
8. [Codebase Structure](#8-codebase-structure)
9. [API Contract](#9-api-contract)
10. [Cost Considerations](#10-cost-considerations)
11. [Scalability & Limits](#11-scalability--limits)
12. [Future Enhancements](#12-future-enhancements)
    - 12.1 [Next Step: Migrate to OCI Container Instances](#121-next-step-migrate-to-oci-container-instances-recommended)
    - 12.2 [Other Enhancements](#122-other-enhancements)
13. [Multi-Agent Architecture (v2.0)](#13-multi-agent-architecture-v20)
    - 13.1 [Architecture Diagram](#131-architecture-diagram)
    - 13.2 [Agent Descriptions](#132-agent-descriptions)
    - 13.3 [JDE MCP Server Enhancement](#133-jde-mcp-server-enhancement)
    - 13.4 [Workflow](#134-workflow)
    - 13.5 [Deployment Topology](#135-deployment-topology)
    - 13.6 [v2.0 Codebase Structure](#136-v20-codebase-structure)

---

## 1. Executive Summary

This solution adds **AI-powered analysis** to JD Edwards (JDE) Integrity Reports. When a scheduled JDE batch job produces an Integrity Report (PDF), a JDE Orchestration automatically submits it for AI analysis. The AI reads the full report, determines whether it contains actionable data, and — if it does — produces a structured analysis that identifies **problems, explains their JDE context, and recommends corrective actions**.

**Key business value:**
- **Automated triage** — No human needs to open and read every Integrity Report to decide if action is needed.
- **Expert-level analysis** — The AI understands JDE-specific concepts (unposted batches, subledger-to-GL reconciliation, error codes) and explains them in business terms.
- **Speed** — A 50+ page report is analyzed in under 30 seconds.
- **Cost-efficient** — Serverless architecture means you only pay when reports are actually being analyzed.

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
│  ┌────────────────┐    ┌──────────────┐    ┌──────────────────────────┐  │
│  │ API Gateway     │───>│ OCI Function │───>│ Object Storage (Bucket) │  │
│  │ (Public REST)   │    │ (Python 3.11)│<───│ "agent-knowledge-base"  │  │
│  └────────────────┘    └──────┬───────┘    └──────────────────────────┘  │
│                               │                                          │
│                               │ Full document text                       │
│                               ▼                                          │
│                      ┌──────────────────┐                                │
│                      │ OCI GenAI Service │                                │
│                      │ (Gemini 2.5 Flash)│                                │
│                      └──────────────────┘                                │
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
| **4** | JDE → API Gateway | The Orchestration sends a REST `POST /v1/analyze` to the OCI API Gateway with the PDF filename. |
| **5** | API Gateway → OCI Function | The gateway routes the request to the OCI Function (`oci-agent-function`). |
| **6** | OCI Function → Object Storage | The function downloads the PDF from the bucket using OCI Object Storage SDK. |
| **7** | OCI Function (pypdf) | The function extracts all text from the PDF using `pypdf`. |
| **8** | Content Check | If extracted text > 300 characters → report has data (`checkerResponse: "Yes"`). Otherwise → empty report (`"No"`), analysis skipped. |
| **9** | OCI Function → GenAI | Full document text is sent to OCI GenAI Inference API (`google.gemini-2.5-flash`) with a JDE-specialist system prompt. |
| **10** | Response | The function returns `{"checkerResponse", "analysisResponse"}` back through the API Gateway to JDE. |
| **11** | JDE Orchestration | The Orchestration receives the AI analysis and can route it (email, notification, JDE queue, etc.). |

### Design Principles

- **Serverless** — No servers to manage. OCI Functions spin up on demand and scale to zero when idle.
- **Direct inference** — The full document text is sent to the LLM in a single prompt. No RAG, no vector databases, no embeddings. This is intentional: each call analyzes ONE specific report, not a corpus of documents.
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

## 5. OCI Function — The Analysis Engine

### What It Does

The function (`func.py`) is the core processing logic. It is a **stateless, serverless Python function** that:

1. **Downloads** the specified PDF from Object Storage
2. **Extracts** text from all pages using `pypdf`
3. **Checks** whether the report contains meaningful data (> 300 characters of text)
4. **Analyzes** the report by sending the full text to OCI GenAI with a JDE-specialist system prompt
5. **Returns** a structured JSON response

### Technology Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| Runtime | Python | 3.11 |
| Function Framework | OCI FDK (Fn Project) | >= 0.1.105 |
| OCI SDK | `oci` Python SDK | >= 2.168.0 |
| PDF extraction | `pypdf` | >= 4.0.0 |
| Container | Docker (multi-stage build) | fnproject/python:3.11 |
| LLM | Google Gemini 2.5 Flash | On-demand serving via OCI |

### System Prompt (AI Persona)

The function instructs the LLM to act as a **JD Edwards Integrity Report analyst**. The system prompt:

- Requires the AI to identify specific integrity issues
- Demands explanations in JDE context (table names like F0411, F0911, error codes, batch statuses)
- Enforces structured output: Summary → Detailed Problems → Recommended Fixes
- Caps response length at ~850 words to keep analysis focused and actionable

### Function Configuration

| Setting | Value | Purpose |
|---------|-------|---------|
| Memory | 1024 MB | Sufficient for PDF parsing + large text payloads |
| Timeout | 300 seconds | GenAI inference can take 10-60s for large reports |
| Image Registry | `phx.ocir.io/axzkbtajofjq/agent-functions/` | Oracle Container Image Registry (Phoenix) |
| Current Version | v0.0.29 | |

---

## 6. OCI Infrastructure Components

### 6.1 Object Storage Bucket

| Property | Value |
|----------|-------|
| Bucket Name | `agent-knowledge-base` |
| Namespace | `axzkbtajofjq` |
| Tier | Standard |
| Region | us-phoenix-1 |
| Purpose | Stores Integrity Report PDFs uploaded by JDE Orchestrations |

JDE uploads each report PDF to this bucket before requesting analysis. The function reads from this bucket using the OCI SDK with Resource Principal authentication — no API keys stored in code.

### 6.2 OCI Functions Application

| Property | Value |
|----------|-------|
| App Name | `agent-app` |
| App OCID | `ocid1.fnapp.oc1.phx.amaaaaaa7bibg4qaocgvbxdiwnete6q33m7ruullxy4zca5iqmk7fhtz75jq` |
| Function Name | `oci-agent-function` |
| Function OCID | `ocid1.fnfunc.oc1.phx.amaaaaaa7bibg4qa6n77gpsbj6hzwui2k7uyqsuw7qaw2iwa2yll3ng4yeoa` |
| Compartment | `jdee1` |

### 6.3 API Gateway

Two gateways provide REST access to the function:

| Gateway | Type | Hostname | Use Case |
|---------|------|----------|----------|
| `JDE_API_Gateway_Open` | **Public** | `jfiidvdcmm4d2oqweow44nsovq.apigateway.us-phoenix-1.oci.customer-oci.com` | External/dev access, JDE Orchestrations over internet |
| `JDE_API_Gateway` | **Private** | `daa6bnvhau6ufxbsf7n3my4b4y.apigateway.us-phoenix-1.oci.customer-oci.com` | JDE servers on the same VCN (traffic stays internal) |

Both gateways have an `AgentAnalyze` deployment with:
- **Path prefix**: `/v1`
- **Route**: `POST /analyze` → OCI Function backend
- **Full URL**: `https://<gateway-hostname>/v1/analyze`

### 6.4 OCI GenAI Service

| Property | Value |
|----------|-------|
| Service | OCI Generative AI Inference |
| Model | `google.gemini-2.5-flash` |
| Serving Mode | On-demand (no dedicated hosting, pay per use) |
| Context Window | ~1,000,000 tokens (~750,000 words) |
| Max Output Tokens | 8,192 (configured) |
| Temperature | 0.2 (low creativity, high consistency) |
| Region | us-phoenix-1 |

**Why Gemini 2.5 Flash?**
- Massive context window handles 50+ page reports without truncation
- Fast inference (Flash variant optimized for speed)
- Available for on-demand serving in OCI Phoenix (no provisioning needed)
- Cost-efficient compared to larger models (Pro, GPT-4)

### 6.5 Container Image Registry (OCIR)

| Property | Value |
|----------|-------|
| Registry | `phx.ocir.io` |
| Repository | `axzkbtajofjq/agent-functions/oci-agent-function` |
| Build | Multi-stage Docker (slim production image) |
| Base Image | `fnproject/python:3.11` |

---

## 7. Security & IAM Policies

### 7.1 Authentication Model

The function uses **OCI Resource Principal** authentication — no API keys, passwords, or secrets are stored in the code or environment. The function's identity is derived from its OCI resource, and IAM policies grant permissions based on a Dynamic Group membership.

```
┌──────────────────┐         ┌──────────────────┐
│  OCI Function     │──RP───>│  Dynamic Group    │
│  (resource        │ auth    │  agent-functions- │
│   principal)      │         │  dg               │
└──────────────────┘         └────────┬───────────┘
                                      │
                          IAM Policies │ grant access to:
                                      │
                    ┌─────────────────┼────────────────────┐
                    │                 │                     │
              ┌─────▼─────┐   ┌──────▼──────┐   ┌────────▼────────┐
              │ Object     │   │ GenAI       │   │ GenAI Agent     │
              │ Storage    │   │ Inference   │   │ (legacy, can    │
              │ (read)     │   │ (manage)    │   │  be removed)    │
              └───────────┘   └─────────────┘   └─────────────────┘
```

### 7.2 Dynamic Group

| Property | Value |
|----------|-------|
| Name | `agent-functions-dg` |
| Matching Rule | Matches all `fnfunc` resources in compartment `jdee1` |

### 7.3 IAM Policies

| Policy Name | Statement | Purpose |
|-------------|-----------|---------|
| `agent-functions-policy` | `Allow dynamic-group agent-functions-dg to manage generative-ai-family in compartment jdee1` | Function can call OCI GenAI Inference API |
| `agent-functions-policy` | `Allow dynamic-group agent-functions-dg to manage genai-agent-family in compartment jdee1` | Legacy (from previous Agent-based architecture). Can be removed. |
| `fn-objectstorage-read` | `Allow dynamic-group agent-functions-dg to read object-family in compartment jdee1` | Function can download PDFs from Object Storage |
| `apigw-functions-policy` | `Allow any-user to use functions-family in compartment jdee1 where ALL {request.principal.type = 'ApiGateway', ...}` | API Gateway can invoke the function |

### 7.4 Network Security

| Layer | Configuration |
|-------|--------------|
| **Public API Gateway** | HTTPS only (TLS 1.2+). No authentication currently configured — suitable for internal networks or VPN. |
| **Private API Gateway** | Accessible only from within the VCN (`PrivatRegSub` subnet 10.9.4.0/24). Used when JDE servers are on the same OCI VCN. |
| **OCI Function** | Not directly accessible from the internet. Only invokable via `fn invoke`, API Gateway, or OCI SDK. |
| **Object Storage** | Private bucket. Accessible only via IAM-authenticated OCI SDK calls. No public access. |
| **GenAI Service** | OCI service endpoint. Accessed via OCI SDK with Resource Principal auth. Traffic stays on OCI backbone. |

### 7.5 Security Recommendations for Production

| Recommendation | Priority | Details |
|----------------|----------|---------|
| Add API Gateway authentication | **High** | Add API key validation or OAuth2/JWT to the public gateway to prevent unauthorized access. |
| Enable API Gateway rate limiting | Medium | Protect against abuse and control costs. |
| Remove legacy `genai-agent-family` policy | Low | No longer needed after Agent/KB removal. |
| Enable OCI Audit logging | Medium | Track all API Gateway and Function invocations for compliance. |
| Restrict Dynamic Group scope | Low | Narrow the matching rule to the specific function OCID instead of all functions in the compartment. |

---

## 8. Codebase Structure

All source code resides in the `OCIFunction/` directory:

```
OCIFunction/
├── func.py             # Main function handler (production code)
├── quickstart.py       # Local development/testing script (api_key auth)
├── requirements.txt    # Python dependencies: fdk, oci, pypdf
├── Dockerfile          # Multi-stage Docker build for OCI Functions
├── func.yaml           # Function metadata: name, version, memory, timeout
├── PLAN.md             # Implementation log and decision record
├── ARCHITECTURE.md     # This document
├── .dockerignore       # Excludes .venv, __pycache__, rag/, etc. from Docker
└── .gitignore          # Excludes .venv, __pycache__, rag/, ingest/, *.txt
```

| File | Purpose |
|------|---------|
| `func.py` | Production function handler. Downloads PDF, extracts text, calls GenAI. Uses Resource Principal auth. |
| `quickstart.py` | Development mirror of func.py. Uses `~/.oci/config` API key auth for local testing. |
| `Dockerfile` | Two-stage build: installs deps in build stage, copies to slim runtime image. |
| `func.yaml` | Declares function name (`oci-agent-function`), memory (1024 MB), timeout (300s). |

---

## 9. API Contract

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

## 10. Cost Considerations

### 10.1 OCI Services Pricing Model

All components use **pay-per-use** pricing. There are no fixed monthly commitments required.

| Service | Pricing Model | Key Metric | Estimated Cost |
|---------|--------------|------------|----------------|
| **OCI Functions** | Per invocation + compute time | $0.0002/invocation + $0.00001417/GB-second | Very low. A 30-second invocation at 1 GB ≈ $0.0006 |
| **OCI Object Storage** | Per GB stored + requests | $0.0255/GB/month (Standard) + $0.0034/10K requests | Minimal. Report PDFs are small (< 5 MB each). |
| **OCI API Gateway** | Per million API calls | $3.00 per million calls | Minimal at expected volumes. |
| **OCI GenAI (On-Demand)** | Per token (input + output) | Varies by model. Gemini Flash is among the most cost-efficient. | Primary cost driver. See below. |
| **OCIR (Container Registry)** | Per GB stored | First 500 MB free, then $0.0255/GB/month | Negligible. Docker image is ~100 MB. |

### 10.2 GenAI Cost Estimation

The GenAI inference cost depends on document size (input tokens) and analysis length (output tokens).

| Report Type | Pages | Input Tokens (est.) | Output Tokens (est.) | Cost per Analysis (est.) |
|------------|-------|--------------------|--------------------|------------------------|
| Small report (R047001A) | 1-2 | ~500 | ~800 | < $0.001 |
| Medium report (R007011) | 10-30 | ~20,000 | ~800 | ~$0.002 - $0.005 |
| Large report | 50+ | ~50,000 | ~800 | ~$0.005 - $0.015 |

> **Note**: OCI GenAI on-demand pricing for Google Gemini models through OCI may vary. Check the [OCI GenAI Pricing page](https://www.oracle.com/cloud/pricing/#generative-ai) for current rates. OCI often provides generous free-tier allowances for GenAI services.

### 10.3 Monthly Cost Scenarios

| Scenario | Reports/Month | Estimated Monthly Cost |
|----------|---------------|----------------------|
| **Low volume** | 50 reports | $0.25 - $1.00 |
| **Medium volume** | 500 reports | $2.50 - $10.00 |
| **High volume** | 5,000 reports | $25.00 - $100.00 |

> These estimates include Functions compute, Object Storage, API Gateway, and GenAI inference. The dominant cost is GenAI inference. All other components contribute less than $1/month at these volumes.

### 10.4 Cost Optimization Levers

| Strategy | Impact |
|----------|--------|
| **Checker skips empty reports** | Reports with no data (< 300 chars of text) skip the GenAI call entirely. Zero inference cost for empty reports. |
| **System prompt word cap** | Limits output tokens to ~850 words, preventing unnecessarily verbose (and expensive) responses. |
| **On-demand serving** | No idle cost. You only pay when a report is actually being analyzed. |
| **Gemini Flash (not Pro)** | Flash variant is significantly cheaper than Pro while providing excellent analysis quality for this use case. |

---

## 11. Scalability & Limits

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

## 12. Future Enhancements

### 12.1 Next Step: Migrate to OCI Container Instances (Recommended)

The current OCI Functions architecture is ideal for a proof of concept, but the **recommended next evolution** is to migrate to **OCI Container Instances** (or OCI Container Apps). This involves rewriting the function as a standalone Python web service (e.g., Flask or FastAPI) with its own API routes, then deploying it as a long-running container.

**Why migrate to containers?**

| Benefit | Details |
|---------|---------|
| **Own API routes** | Define custom endpoints (`/v1/analyze`, `/v1/health`, `/v1/status`, `/v1/reports`) directly in the application code (Flask/FastAPI) instead of relying on fn invoke + API Gateway routing. More flexibility for versioning, middleware, and request validation. |
| **Observability & Monitoring** | OCI Container Instances integrate with **OCI Logging** via Docker's native logging driver. All `print()` and `logging.*` output is captured automatically. With OCI Functions, logs are limited to fn syslog. Containers give structured JSON logs, log levels, correlation IDs, and easy integration with OCI Monitoring dashboards and alarms. |
| **Health checks & readiness probes** | Containers support HTTP health check endpoints (`/health`). OCI can automatically restart unhealthy instances — not possible with Functions. |
| **Longer execution times** | Functions are capped at 300 seconds. Containers have no such limit, enabling analysis of very large report batches. |
| **Warm starts** | Containers stay running (no cold-start penalty). OCI Functions can have 5-15 second cold starts when idle. |
| **Local development parity** | Run the same Docker container locally (`docker run -p 8080:8080`) with identical behavior to production. No FDK dependency or fn server needed. |

**What changes in the migration:**

| Component | Current (OCI Functions) | Target (OCI Container Instances) |
|-----------|------------------------|----------------------------------|
| Framework | OCI FDK (`fdk`) | Flask or FastAPI |
| Entry point | `handler(ctx, data)` | `@app.post("/v1/analyze")` |
| Routing | API Gateway routes → fn invoke | Application-defined routes (Flask/FastAPI) |
| Auth to OCI | Resource Principal (same) | Instance Principal or Resource Principal (same pattern) |
| Container | Same Docker image, different ENTRYPOINT | `ENTRYPOINT ["python", "app.py"]` or `uvicorn app:app` |
| Logging | `fdk` syslog → limited | `logging.getLogger()` → Docker stdout → OCI Logging service |
| Monitoring | Basic fn invocation metrics | OCI Monitoring: custom metrics, CPU/memory, request latency, log-based alarms |
| API Gateway | Still used (optional) | Can keep API Gateway for TLS termination and rate limiting, or expose container directly via load balancer |
| Cost model | Per-invocation (scale to zero) | Per-hour while running (always-on). More predictable cost at higher volumes. |

**Estimated migration effort**: Low-Medium. The core logic (`func.py` — download PDF, extract text, call GenAI) stays identical. The change is replacing the FDK handler wrapper with Flask/FastAPI route handlers and adding a structured logging setup.

### 12.2 Other Enhancements

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

*This document describes the architecture as of v0.0.29 deployed on March 19, 2026.*

---

## 13. Multi-Agent Architecture (v2.0)

> **Status**: Deployed (MCP) / In Development (Agents) | **Target**: Foundry Agent Service (Azure) + JDE MCP Server (Azure Container Apps)

v2.0 evolves the single-script PDF→LLM pipeline into a **multi-agent architecture** using Microsoft Foundry Agent Framework. Instead of one GenAI call that reads the PDF and produces an analysis, the system now splits into two specialized agents that work sequentially.

**Key improvement**: The AnalyzerAgent can **query live JDE data** via MCP tools to cross-reference the PDF findings, producing far more accurate and actionable analysis than v1.0's LLM-only approach.

### 13.1 Architecture Diagram

```
                    ┌───────────────────────────────┐
                    │   Foundry Agent Service        │
                    │   Sequential Workflow           │
                    │   (ExtractorAgent → Analyzer)   │
                    └─────────────┬─────────────────┘
                                  │
                     ┌────────────┼─────────────┐
                     │                          │
              ┌──────▼──────┐           ┌───────▼───────┐
              │  Extractor  │──struct──▶│   Analyzer    │
              │   Agent     │  JSON     │     Agent     │
              │ (PDF→data)  │           │  (MCP tools)  │
              └──────┬──────┘           └───────┬───────┘
                     │                          │
              ┌──────▼──────┐           ┌───────▼───────┐
              │ OCI Object  │           │  JDE MCP      │
              │  Storage    │           │  Server       │
              │ (bucket)    │           │ (Azure CApps) │
              └─────────────┘           └───────┬───────┘
                                                │
                                         ┌──────▼──────┐
                                         │  JDE AIS    │
                                         │ REST API    │
                                         │ F0411,F0902 │
                                         │ F0901       │
                                         └─────────────┘
```

### 13.2 Agent Descriptions

| Agent | Purpose | Tools | Technology |
|-------|---------|-------|------------|
| **ExtractorAgent** | Downloads PDF from OCI Object Storage, extracts text with `pypdf`, uses LLM to produce structured JSON (report type, company, discrepancies, accounts) | `download_and_extract_pdf` (FunctionTool) | Python, OCI SDK, pypdf |
| **AnalyzerAgent** | Receives structured extraction, queries live JDE data via MCP tools, cross-references PDF findings, produces verified analysis with recommendations | 4 MCP tools (see §13.3) | Python, McpTool → JDE MCP Server |

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

### 13.3 JDE MCP Server Enhancement

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

### 13.4 Workflow

The workflow is a **sequential graph** built with `WorkflowBuilder`:

```
Input (object_name) → ExtractorAgent → structured JSON → AnalyzerAgent → final report
```

1. **Input**: User provides `object_name` (PDF filename in OCI bucket)
2. **ExtractorAgent**: Calls `download_and_extract_pdf` tool → LLM produces structured JSON extraction
3. **AnalyzerAgent**: Receives JSON → calls `jde_ap_gl_integrity_check` and other MCP tools → cross-references PDF findings against live data → produces verified analysis
4. **Output**: Structured analysis with confirmed/resolved/new issues and recommendations

### 13.5 Deployment Topology

| Component | Platform | Transport | Auth | URL |
|-----------|----------|-----------|------|-----|
| **API Wrapper** | Azure Container Apps (`jde-integrity-api`) | HTTP POST `/v1/analyze` | Static Azure AD token (see caveat below) | `https://jde-integrity-api.bluedesert-fb732cac.eastus.azurecontainerapps.io` |
| **JDE MCP Server** | Azure Container Apps (`jde-mcp-integrity`) | HTTP POST `/mcp` | Unauthenticated (public) | `https://jde-mcp-integrity.bluedesert-fb732cac.eastus.azurecontainerapps.io` |
| **JDE AIS** | On-prem / OCI | HTTP REST | Basic Auth (via AIS connector) | Configured via env vars |
| **OCI Object Storage** | OCI (us-phoenix-1) | OCI SDK | Base64-encoded PEM key (Container App secret) | — |
| **OCI Function (v1.0 fallback)** | OCI Functions | HTTP via API Gateway | Resource Principal | — |

**Azure Infrastructure**:
- ACR: `acrjdemcppo.azurecr.io`
  - `jde-mcp-integrity:v1` — MCP server image
  - `jde-integrity-api:v5` — API wrapper image
- Container Apps Environment: `jde-mcp-env` (East US)
- Resource Group: `rg-hackathon-2603` (subscription: CLSandbox2)
- API Managed Identity Principal: `8468895c-7fcc-43dc-aceb-ce7dd2412572`

#### ⚠️ Auth Caveat — Foundry Token

The API wrapper container (`jde-integrity-api`) authenticates to Azure AI Foundry using a **static Azure AD token** (`FOUNDRY_TOKEN` env var). This token **expires in ~1 hour** and must be refreshed manually:

```bash
# Refresh token from Azure CLI
token=$(az account get-access-token --resource "https://ai.azure.com" --query accessToken -o tsv)
az containerapp update --name jde-integrity-api --resource-group rg-hackathon-2603 \
  --set-env-vars "FOUNDRY_TOKEN=$token" --revision-suffix "refresh-$(date +%s)"
```

**Why**: The Container App has a system-assigned managed identity, but the user's account lacks `Microsoft.Authorization/roleAssignments/write` permission in this sandbox subscription to assign `Azure AI User` role.

**Permanent fix**: An **Owner** or **User Access Administrator** must run:
```bash
az role assignment create \
  --assignee 8468895c-7fcc-43dc-aceb-ce7dd2412572 \
  --role "Azure AI User" \
  --scope /subscriptions/74528fbf-d0fa-4d72-b3ef-dee45c2a8293/resourceGroups/rg-hackathon-2603
```
Then remove `FOUNDRY_TOKEN` env var — the container will use `DefaultAzureCredential` → managed identity automatically.

#### OCI Auth in Container

The ExtractorAgent in the container authenticates to OCI Object Storage using env vars instead of `~/.oci/config`:

| Env Var | Source | Stored As |
|---------|--------|-----------|
| `OCI_USER` | OCI config `user=` | Plain env var |
| `OCI_FINGERPRINT` | OCI config `fingerprint=` | Plain env var |
| `OCI_TENANCY` | OCI config `tenancy=` | Plain env var |
| `OCI_REGION` | OCI config `region=` | Plain env var |
| `OCI_KEY_CONTENT` | PEM key file (base64-encoded) | Container App secret (`oci-key-content`) |

The `extractor/agent.py` `_get_oci_config()` function decodes the base64 key and constructs an OCI config dict.

### 13.6 v2.0 Codebase Structure

```
OCIFunction/
├── func.py                          # v1.0 OCI Function handler (production fallback)
├── quickstart.py                    # v1.0 Local dev/test (api_key auth)
├── requirements.txt                 # v1.0 Python deps (fdk, oci, pypdf)
├── Dockerfile                       # v1.0 OCI Function container
├── func.yaml                        # v1.0 Function metadata
├── docker-compose.yml               # v2.0 Local dev: 4 services (mcp, extractor, analyzer, api)
├── .env.example                     # v2.0 Root env template for docker-compose
│
├── agents/                          # v2.0 Foundry Multi-Agent System
│   ├── api.py                       # FastAPI wrapper (POST /v1/analyze, GET /health)
│   ├── app.py                       # Workflow entry point (sequential orchestration)
│   ├── workflow.py                  # Sequential workflow: Extractor → Analyzer
│   ├── Dockerfile.api               # API wrapper container (python:3.12-slim, port 8080)
│   ├── requirements-api.txt         # API deps (fastapi, uvicorn + agent deps)
│   ├── extractor/
│   │   ├── agent.py                 # ExtractorAgent: PDF download + text extraction
│   │   ├── app.py                   # Standalone HTTP entry point (port 8088)
│   │   ├── Dockerfile               # Container (python:3.12-slim)
│   │   └── requirements.txt         # Deps: oci, pypdf, agent-framework
│   ├── analyzer/
│   │   ├── agent.py                 # AnalyzerAgent: MCP tools + cross-reference
│   │   ├── app.py                   # Standalone HTTP entry point (port 8088)
│   │   ├── Dockerfile               # Container (python:3.12-slim)
│   │   └── requirements.txt         # Deps: agent-framework (no oci/pypdf)
│   ├── requirements.txt             # v2.0 Python deps (agent-framework, azure-identity)
│   ├── agent.yaml                   # Foundry agent metadata
│   ├── Dockerfile                   # v2.0 workflow container (python:3.12-slim, port 8088)
│   └── .env                         # Environment variables (production MCP URL)
│
├── jde-mcp-server-template/         # JDE MCP Server (git subtree)
│   └── src/
│       ├── tools/integrity.ts       # 4 new AP/GL integrity tools
│       ├── schemas/tools.ts         # Zod schemas (including new integrity schemas)
│       ├── data/dictionary.json     # v1.2.0 — added F0411, F0902, F0901
│       └── index.ts                 # Tool registration (includes integrity layer)
│
├── ARCHITECTURE.md                  # This document
├── PLAN.md                          # Project log and decision record
└── ingest/                          # Sample report PDFs for testing
```

---

*v2.0 architecture documented on April 11, 2025. MCP deployed to Azure Container Apps on April 11, 2026.*
