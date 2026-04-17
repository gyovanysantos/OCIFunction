# Client-Specific Configuration Guide

> **Purpose**: This document lists every file and value that must be updated when deploying this project for a new client. Follow each section to ensure nothing is missed.

---

## Quick Checklist

- [ ] JDE server credentials & URL
- [ ] OCI credentials & resources
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

## 2. Agent Configuration

### `agents/agent.yaml` (Hosted Agent)

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

## 3. JDE MCP Server

### `jde-mcp-server-template/src/constants.ts`

All JDE values are read from **environment variables** — no hardcoded client data. Defaults:

| Env Variable | Default | What to Change |
|--------------|---------|----------------|
| `JDE_AIS_URL` | *(required, no default)* | Set in `.env` |
| `JDE_USERNAME` | *(required, no default)* | Set in `.env` |
| `JDE_PASSWORD` | *(required, no default)* | Set in `.env` |
| `JDE_ENVIRONMENT` | `"JDV920"` | Set in `.env` if different |
| `JDE_ROLE` | `"*ALL"` | Set in `.env` if different |
| `JDE_API_VERSION` | `"v2"` | Only change if client uses v1 AIS |

### `jde-mcp-server-template/src/index.ts`

| Item | Current Value | What to Change |
|------|---------------|----------------|
| Server name | `"jde-mcp-server"` | Optional — cosmetic only |
| Server version | `"1.1.0"` | Track your releases |
| `PORT` | `3000` (from env) | Usually fine |
| `TRANSPORT` | `"http"` (from env) | Usually fine |

---

## 4. OCI Infrastructure

| Component | Current Value | What to Change |
|-----------|---------------|----------------|
| **Compartment OCID** | `ocid1.compartment.oc1..aaaaaaaamxleq3holrutfb7hih7u4nq42mam77a3ye6m5ufgaqx4itdfxr6a` | Client's OCI compartment |
| **Region** | `us-phoenix-1` | Client's OCI region |
| **Object Storage Namespace** | `axzkbtajofjq` (dev) / `idxoqn0ijjyv` (prod) | Client's OCI tenancy namespace |
| **Bucket** | `agent-knowledge-base` (dev) / `OBJECTSTORAGE` (prod) | Client's bucket name |
| **OCI Config Profile** | `DEFAULT` in `~/.oci/config` | Client's OCI profile |
| **GenAI Model** | `google.gemini-2.5-flash` | Available model in client's OCI region |

---

## 5. Documentation Files to Update

These files contain client-specific references that should be updated to avoid confusion:

| File | What to Update |
|------|----------------|
| `.github/copilot-instructions.md` | All OCIDs, Azure resource names, endpoints, subscription IDs |
| `ARCHITECTURE.md` | Infrastructure references, endpoints, resource names |
| `PLAN.md` | Remove or archive current client's decision log |
| `TECH-STACK.md` | Update if model or OCI region changes |
| `DEPLOY-PLAN.md` | Update deployment targets and commands |
idxoqn0ijjyv` | Client's OCI tenancy namespace |
| **Bucket** | `OBJECTSTORAGE`

## 6. Ports Reference (Usually No Change Needed)

| Service | Port | Purpose |
|---------|------|---------|
| MCP Server | `3000` | JDE MCP HTTP transport |
| API Wrapper | `8080` | HTTP API for workflow orchestration |

---

## Step-by-Step Migration Procedure

1. **Clone the repo** for the new client
2. **Create `.env` files** from templates:
   ```bash
   cp .env.example .env
   cp agents/.env.example agents/.env
   ```
3. **Fill in JDE credentials** in root `.env` (AIS URL, username, password, environment)
4. **Fill in OCI details** in `.env` files (compartment, region, agent endpoint IDs)
5. **Update `agents/agent.yaml`** with client OCI bucket/namespace
6. **Deploy MCP server** to client's container environment
7. **Update `MCP_SERVER_URL`** in `.env` with the deployment URL
8. **Test locally** with `docker compose up --build`
9. **Update documentation** files listed in Section 5
