# Client-Specific Configuration Guide

> **Purpose**: This document lists every file and value that must be updated when deploying this project for a new client. Follow each section to ensure nothing is missed.

---

## Quick Checklist

- [ ] OCI credentials & resources (v1.0)
- [ ] JDE server credentials & URL
- [ ] Azure Foundry project & model (v2.0)
- [ ] Azure Container Apps & ACR (v2.0)
- [ ] Environment files (`.env`)
- [ ] Copilot instructions (`.github/copilot-instructions.md`)
- [ ] Documentation files (`ARCHITECTURE.md`, `PLAN.md`)

---

## 1. Environment Files (Start Here)

These are the **primary** files to update. Most agent/service code reads from these.

### Root `.env` (used by `docker-compose.yml`)

| Variable | Current Value | What to Change |
|----------|---------------|----------------|
| `JDE_AIS_URL` | `http://132.145.130.131:8002/jderest` | Client's JDE AIS server URL |
| `JDE_USERNAME` | `GSANTOS` | Client's JDE username |
| `JDE_PASSWORD` | *(plaintext)* | Client's JDE password |
| `JDE_ENVIRONMENT` | `JDV920` | Client's JDE environment (e.g., `JPD920`, `JDV920`) |
| `JDE_ROLE` | `*ALL` | Client's JDE role (usually `*ALL`) |
| `FOUNDRY_PROJECT_ENDPOINT` | `https://gsantos-hackaton26-resource.services.ai.azure.com/api/projects/gsantos-hackaton26` | Client's Azure AI Foundry project endpoint |
| `FOUNDRY_MODEL_DEPLOYMENT_NAME` | `gpt-4.1` | Client's model deployment name |

### `agents/.env` (used by agent containers)

| Variable | Current Value | What to Change |
|----------|---------------|----------------|
| `FOUNDRY_PROJECT_ENDPOINT` | `https://gsantos-hackaton26-resource.services.ai.azure.com/api/projects/gsantos-hackaton26` | Client's Azure AI Foundry endpoint |
| `FOUNDRY_MODEL_DEPLOYMENT_NAME` | `gpt-4.1` | Client's model deployment name |
| `MCP_SERVER_URL` | `https://jde-mcp-integrity.bluedesert-fb732cac.eastus.azurecontainerapps.io/mcp` | Client's deployed MCP server URL |
| `OCI_BUCKET_NAME` | `OBJECTSTORAGE` | Client's OCI Object Storage bucket name |
| `OCI_NAMESPACE` | `idxoqn0ijjyv` | Client's OCI Object Storage namespace |

> **Tip**: Copy `.env.example` → `.env` and `agents/.env.example` → `agents/.env`, then fill in client values.

---

## 2. v1.0 — OCI Function (Hardcoded Values)

These files have **hardcoded** client-specific constants that must be edited directly.

### `func.py` (Production — OCI Function)

| Line(s) | Variable | Current Value | What to Change |
|---------|----------|---------------|----------------|
| ~L13 | `COMPARTMENT_ID` | `"type compartment ID here"` | Client's OCI Compartment OCID |
| ~L14 | `REGION` | `"us-phoenix-1"` | Client's OCI region |
| ~L15 | `BUCKET_NAME` | `"agent-knowledge-base"` | Client's OCI bucket for PDF reports |
| ~L16 | `NAMESPACE` | `"axzkbtajofjq"` | Client's OCI Object Storage namespace |
| ~L17 | `MODEL_ID` | `"google.gemini-2.5-flash"` | Client's OCI GenAI model ID |

### `quickstart.py` (Local Development)

| Line(s) | Variable | Current Value | What to Change |
|---------|----------|---------------|----------------|
| ~L12 | `COMPARTMENT_ID` | `"ocid1.compartment.oc1..aaaaaaaamxleq3holrutfb7hih7u4nq42mam77a3ye6m5ufgaqx4itdfxr6a"` | Client's OCI Compartment OCID |
| ~L13 | `REGION` | `"us-phoenix-1"` | Client's OCI region |
| ~L14 | `BUCKET_NAME` | `"agent-knowledge-base"` | Client's OCI bucket |
| ~L15 | `NAMESPACE` | `"axzkbtajofjq"` | Client's OCI namespace |
| ~L16 | `MODEL_ID` | `"google.gemini-2.5-flash"` | Client's OCI GenAI model |

> **Rule**: `func.py` and `quickstart.py` must always have the **same constants** (except auth method).

### `func.yaml` (OCI Function Metadata)

| Key | Current Value | What to Change |
|-----|---------------|----------------|
| `name` | `oci-agent-function` | Client-specific function name (optional) |
| `memory` | `1024` | Adjust if client needs more/less memory |
| `timeout` | `300` | Adjust if client needs longer timeout |

---

## 3. v2.0 — Agent Configuration

### `agents/agent.yaml` (Foundry Hosted Agent)

| Key | Current Value | What to Change |
|-----|---------------|----------------|
| `name` | `jde-integrity-analyzer` | Client-specific agent name |
| `OCI_BUCKET_NAME` | `agent-knowledge-base` | Client's OCI bucket |
| `OCI_NAMESPACE` | `axzkbtajofjq` | Client's OCI namespace |

### `agents/extractor/agent.py` (Default Values in Code)

| Variable | Default | What to Change |
|----------|---------|----------------|
| `OCI_BUCKET_NAME` | `"OBJECTSTORAGE"` | Client's bucket (or set via env var) |
| `OCI_NAMESPACE` | `"idxoqn0ijjyv"` | Client's namespace (or set via env var) |

### `agents/analyzer/agent.py` (Hardcoded MCP Tools)

| Item | Current Value | What to Change |
|------|---------------|----------------|
| `MCP_SERVER_URL` default | `"http://localhost:3000/mcp"` | Usually fine — overridden by env var |
| Allowed MCP tools | `jde_ap_voucher_query`, `jde_gl_balance_query`, `jde_gl_detail_query`, `jde_ap_gl_integrity_check` | Update if client has different/additional MCP tools |

---

## 4. JDE MCP Server

### `jde-mcp-ube-analyzer/src/constants.ts`

All JDE values are read from **environment variables** — no hardcoded client data. Defaults:

| Env Variable | Default | What to Change |
|--------------|---------|----------------|
| `JDE_AIS_URL` | *(required, no default)* | Set in `.env` |
| `JDE_USERNAME` | *(required, no default)* | Set in `.env` |
| `JDE_PASSWORD` | *(required, no default)* | Set in `.env` |
| `JDE_ENVIRONMENT` | `"JDV920"` | Set in `.env` if different |
| `JDE_ROLE` | `"*ALL"` | Set in `.env` if different |
| `JDE_API_VERSION` | `"v2"` | Only change if client uses v1 AIS |

### `jde-mcp-ube-analyzer/src/index.ts`

| Item | Current Value | What to Change |
|------|---------------|----------------|
| Server name | `"jde-mcp-server"` | Optional — cosmetic only |
| Server version | `"1.1.0"` | Track your releases |
| `PORT` | `3000` (from env) | Usually fine |
| `TRANSPORT` | `"http"` (from env) | Usually fine |

---

## 5. Azure Infrastructure

These values are used for **deployment** — not in the app code itself.

| Component | Current Value | What to Change |
|-----------|---------------|----------------|
| **Subscription ID** | `74528fbf-d0fa-4d72-b3ef-dee45c2a8293` | Client's Azure subscription |
| **Resource Group** | `rg-hackathon-2603` | Client's resource group |
| **ACR URL** | `acrjdemcppo.azurecr.io` | Client's Azure Container Registry |
| **Container Apps Env** | `jde-mcp-env` | Client's Container Apps environment |
| **MCP Container App** | `jde-mcp-integrity` | Client's MCP container app name |
| **MCP FQDN** | `https://jde-mcp-integrity.bluedesert-fb732cac.eastus.azurecontainerapps.io` | Auto-generated — update after deployment |
| **Foundry Project** | `gsantos-hackaton26` | Client's Foundry project name |
| **Foundry Endpoint** | `gsantos-hackaton26-resource.services.ai.azure.com` | Client's Foundry endpoint |
| **Region** | `East US` | Client's preferred Azure region |

---

## 6. OCI Infrastructure

| Component | Current Value | What to Change |
|-----------|---------------|----------------|
| **Compartment OCID** | `ocid1.compartment.oc1..aaaaaaaamxleq3holrutfb7hih7u4nq42mam77a3ye6m5ufgaqx4itdfxr6a` | Client's OCI compartment |
| **Region** | `us-phoenix-1` | Client's OCI region |
| **Object Storage Namespace** | `axzkbtajofjq` (dev) / `idxoqn0ijjyv` (prod) | Client's OCI tenancy namespace |
| **Bucket** | `agent-knowledge-base` (dev) / `OBJECTSTORAGE` (prod) | Client's bucket name |
| **OCI Config Profile** | `DEFAULT` in `~/.oci/config` | Client's OCI profile |
| **GenAI Model** | `google.gemini-2.5-flash` | Available model in client's OCI region |

---

## 7. Documentation Files to Update

These files contain client-specific references that should be updated to avoid confusion:

| File | What to Update |
|------|----------------|
| `.github/copilot-instructions.md` | All OCIDs, Azure resource names, endpoints, subscription IDs |
| `ARCHITECTURE.md` | Infrastructure references, endpoints, resource names |
| `PLAN.md` | Remove or archive current client's decision log |
| `TECH-STACK.md` | Update if model or OCI region changes |
| `DEPLOY-PLAN.md` | Update deployment targets and commands |

---

## 8. Ports Reference (Usually No Change Needed)

| Service | Port | Purpose |
|---------|------|---------|
| MCP Server | `3000` | JDE MCP HTTP transport |
| Extractor Agent | `8088` | Foundry hosted agent port |
| Analyzer Agent | `8089` (mapped to `8088` internal) | Foundry hosted agent port |
| API Wrapper | `8080` | HTTP API for workflow orchestration |
| OCI Function | — | Managed by OCI Functions infrastructure |

---

## Step-by-Step Migration Procedure

1. **Clone the repo** for the new client
2. **Create `.env` files** from templates:
   ```bash
   cp .env.example .env
   cp agents/.env.example agents/.env
   ```
3. **Fill in JDE credentials** in root `.env` (AIS URL, username, password, environment)
4. **Fill in Azure Foundry details** in both `.env` files (project endpoint, model name)
5. **Update OCI constants** in `func.py` and `quickstart.py` (compartment, region, bucket, namespace, model)
6. **Update `agents/agent.yaml`** with client OCI bucket/namespace
7. **Deploy MCP server** to client's Azure Container Apps:
   - Create ACR, Container Apps Environment
   - Build and push MCP image
   - Note the new FQDN
8. **Update `MCP_SERVER_URL`** in `agents/.env` with the new FQDN
9. **Deploy OCI Function** (if using v1.0):
   - Build Docker image → push to client's OCIR
   - Deploy via `fn deploy` or OCI Console
10. **Test locally** with `docker compose up --build`
11. **Update documentation** files listed in Section 7
