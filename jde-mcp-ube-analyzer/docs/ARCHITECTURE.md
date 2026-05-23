# Architecture

## Overview

TypeScript MCP (Model Context Protocol) server bridging Claude to JD Edwards EnterpriseOne via the AIS REST API. Implements Sales Order CRUD operations through a 5-layer tool architecture with dynamic table discovery.

```
User → Claude (reasoning) → MCP Server → AIS REST API → JDE EnterpriseOne
```

## Deployment Architecture

```
┌─────────────┐       ┌────────────────────────────────────────────┐
│ Claude       │       │ OCI API Gateway (jde-mcp-gateway)          │
│ (MCP Client) │──MCP──│ dwecjmghl667coww5eoz3n3gq4.apigateway...  │
│              │ HTTPS │ /mcp  → container private IP:3000/mcp      │
│              │       │ /health → container private IP:3000/mcp    │
│              │       │ CORS: *, exposed: mcp-session-id           │
└─────────────┘       └──────────────┬─────────────────────────────┘
                                     │ HTTP (private subnet)
                      ┌──────────────▼─────────────────────────────┐
                      │ OCI Container Instance                      │
                      │ jde-mcp-sales-server                        │
                      │ Shape: CI.Standard.E4.Flex (1 OCPU, 2GB)    │
                      │ Port: 3000 (TRANSPORT=http)                       │
                      │ IP: changes on each deploy (gateway is stable) │
                      └──────────────┬─────────────────────────────┘
                                     │ HTTP (Basic Auth, v2 API)
                      ┌──────────────▼─────────────────────────────┐
                      │ JDE EnterpriseOne AIS Server                │
                      │ 132.145.130.131:8006                        │
                      │ API version: v2 (v3 not supported)          │
                      └────────────────────────────────────────────┘
```

### Two Gateways — Different Purposes

| Gateway | Purpose | Endpoint |
|---------|---------|----------|
| **jde-mcp-gateway** | Fronts the MCP server — stable URL for MCP clients | `https://dwecjmghl667coww5eoz3n3gq4.apigateway.../mcp` |
| **E1_GatewayAPI_Ext** | Fronts the raw AIS server — HTTPS + auth injection | `https://c6z5vogwocr44zavycg5wt6kom.apigateway.../jderest/*` |

The MCP server talks **directly to AIS** (not through E1_GatewayAPI_Ext) using Basic Auth and v2 API paths.

## CI/CD Pipeline

```
Push to main → GitHub Actions
                  ├── ci.yml:     lint, build, type-check
                  └── deploy.yml: build image → push OCIR → delete old container
                                  → create new container → get private IP
                                  → update API Gateway backend → health check
```

### Deploy Workflow Steps

1. **Build & Push** — Docker multi-stage build, push to OCIR with `sha` and `latest` tags
2. **Delete old container** — removes previous instance (OCID from `OCI_CONTAINER_INSTANCE_ID` secret)
3. **Create new container** — generates spec JSON from GitHub Secrets (no creds in repo)
4. **Get private IP** — queries VNIC for the new container's private IP
5. **Update API Gateway** — points `jde-mcp-gateway` backend to new private IP:3000
6. **Health check** — verifies MCP is reachable through the gateway URL

### GitHub Secrets Required (19 total)

| Secret | Purpose |
|--------|---------|
| `OCI_AUTH_TOKEN` | OCIR login password |
| `OCI_REGION` | `iad` |
| `OCI_TENANCY_NAMESPACE` | `idxoqn0ijjyv` |
| `OCI_USERNAME` | `Default/gsantos@centrilogic.com` |
| `OCI_PRIVATE_KEY` | Base64-encoded PEM for OCI CLI |
| `OCI_USER_OCID` | OCI user OCID |
| `OCI_FINGERPRINT` | API key fingerprint |
| `OCI_TENANCY_OCID` | Tenancy OCID |
| `OCI_CONTAINER_INSTANCE_ID` | Current container instance OCID (update after each deploy) |
| `OCI_COMPARTMENT_ID` | E1LAB compartment OCID |
| `OCI_SUBNET_ID` | PublicRegSub subnet OCID |
| `OCI_AVAILABILITY_DOMAIN` | `XxXK:US-ASHBURN-AD-1` |
| `OCI_APIGW_DEPLOYMENT_ID` | jde-mcp-gateway deployment OCID |
| `JDE_AIS_URL` | `http://132.145.130.131:8006/jderest` |
| `JDE_USERNAME_VAL` | `GSANTOS` |
| `JDE_PASSWORD_VAL` | JDE password |
| `JDE_ENVIRONMENT_VAL` | `JPY920` |
| `OCIR_PULL_USERNAME_B64` | Base64 registry pull username |
| `OCIR_PULL_PASSWORD_B64` | Base64 registry pull password |

## 5-Layer Tool Design

| Layer | Purpose | Tools | Count |
|-------|---------|-------|-------|
| 0 – Dynamic Discovery | Live introspection of any JDE table | `jde_discover_table`, `jde_search_tables` | 2 |
| 1 – Curated Dictionary | Static data dictionary lookups (5 curated tables) | `jde_dictionary_search`, `_list`, `_table` | 3 |
| 2 – Curated SO CRUD | Sales Order operations with business rules | `jde_sales_order_inquiry`, `jde_create_sales_order`, `jde_update_sales_order`, `jde_add_sales_order_line`, `jde_cancel_sales_order` | 5 |
| 3 – Supporting | Validation & availability checks | `jde_customer_lookup`, `jde_item_check` | 2 |
| 4 – Generic | Escape hatch for any table or orchestration | `jde_query_table`, `jde_call_orchestration` | 2 |

**Total: 14 tools**

### Layer 0 — How Dynamic Discovery Works

1. **`jde_discover_table`** — introspects a target table by querying it with no `returnControlIDs`. AIS returns all exposed columns with keys like `F0101_AN8`. The service strips the table prefix to extract aliases, then enriches with F9210 metadata (size, decimals, data type) and F9200 descriptions.
2. **`jde_search_tables`** — searches F9860 (Object Configuration Manager) by `OBNM` (object name) or `MD` (description) using `STR_CONTAIN` operator.
3. Results are cached in-memory for the session lifetime.

**Key rule:** Write operations route through orchestrations (business rules enforced). Read operations use AIS Data Service directly.

## Project Structure

```
src/
  index.ts              # Entry point — server init, tool registration, transport
  constants.ts          # Env-backed config constants (no hardcoded credentials)
  types.ts              # AIS request/response types, dictionary types, discovery types
  schemas/
    tools.ts            # All Zod input schemas for MCP tools (.strict() mode)
  services/
    ais-client.ts       # AIS REST client — Basic Auth, data/form/orch calls
    dd-discovery.ts     # Layer 0 — live table introspection + F9210/F9200 enrichment
    dictionary.ts       # Dictionary service — load, search, list, resolve columns
    orch-mapper.ts      # Maps tool inputs → orchestration payloads
  tools/
    discovery.ts        # Layer 0 — dynamic discovery tool registrations
    dictionary.ts       # Layer 1 — dictionary tool registrations
    domain.ts           # Layer 2+3 — SO CRUD + lookup tool implementations
    query.ts            # Layer 4 — generic table query tool
    orchestration.ts    # Layer 4 — generic orchestration caller tool
  data/
    dictionary.json     # Curated data dictionary (F4211, F4201, F0101, F4101, F41021)
    orchestrations.json # SO CRUD operation → orchestration name + field mapping
.github/
  workflows/
    ci.yml              # CI — build, lint, type-check on every PR
    deploy.yml          # CD — build, push, deploy, update gateway
  pull_request_template.md  # PR template
  CODEOWNERS            # Code review assignments
```

**Dependency flow:** `index.ts` → `tools/*` → `schemas/tools.ts` + `services/*` → `constants.ts` + `types.ts`

## Container Deployment

- **Registry:** `iad.ocir.io/idxoqn0ijjyv/jde-mcp-sales-template` (private)
- **Image:** Multi-stage build (Node 22 Alpine), ~265MB
- **Platform:** OCI Container Instances (us-ashburn-1, E1LAB compartment)
- **Transport:** HTTP on port 3000 (`TRANSPORT=http`)
- **MCP endpoint:** `POST /mcp` (Streamable HTTP, requires `Accept: application/json, text/event-stream`)
- **Immutability:** OCI Container Instances cannot update images via stop/start — must delete and recreate

## Security

- Container runs as non-root user `mcp`
- Credentials injected via environment variables at deploy time (never baked into image)
- Container spec is generated from GitHub Secrets at runtime (no credentials in repo)
- `.dockerignore` excludes `.env`, `.git`, and sensitive files
- `constants.ts` fails fast if `JDE_AIS_URL`, `JDE_USERNAME`, or `JDE_PASSWORD` are missing
- OCIR repo is private; image pull uses `imagePullSecrets` with base64 credentials
- API Gateway provides HTTPS termination for MCP clients
