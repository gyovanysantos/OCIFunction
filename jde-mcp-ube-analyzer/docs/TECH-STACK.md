# Tech Stack

## Runtime & Language

| Technology | Version | Why |
|-----------|---------|-----|
| **Node.js** | 22 (Alpine) | Lightweight runtime for the MCP server. Alpine reduces container image size (~265MB total). |
| **TypeScript** | ^5.6.0 | Type safety for JDE field mappings, Zod schema inference, and AIS client. Catches mismatched column names at compile time. |

## Core Libraries

| Library | Version | Why |
|---------|---------|-----|
| **@modelcontextprotocol/sdk** | ^1.12.0 | Official MCP SDK. Provides `McpServer`, `StdioServerTransport`, and `StreamableHTTPServerTransport` for both local (stdio) and remote (HTTP) deployment. |
| **Express** | ^4.21.0 | Minimal HTTP framework for the `/mcp` and `/health` endpoints when running in HTTP transport mode. |
| **Zod** | ^3.23.0 | Runtime input validation for all 12 MCP tool schemas. `.strict()` mode rejects unknown fields. Type inference via `z.infer<>` eliminates duplicate type definitions. |

## Dev Dependencies

| Tool | Version | Why |
|------|---------|-----|
| **tsx** | ^4.19.0 | Watch mode for development (`npm run dev`). Runs TypeScript directly without a separate compile step. |
| **shx** | ^0.4.0 | Cross-platform shell commands in npm scripts. Used to copy `src/data/*.json` → `dist/data/` since tsc doesn't copy non-TS files. |
| **@types/express** | ^5.0.0 | TypeScript type definitions for Express. |
| **@types/node** | ^22.0.0 | TypeScript type definitions for Node.js APIs (`process.env`, `URL`, `fs/promises`). |

## Infrastructure (OCI)

| Service | Why |
|---------|-----|
| **OCI Container Instances** | Serverless container hosting. No VMs to manage. Runs the MCP server as an always-on HTTP service. Immutable — must delete and recreate to deploy a new image (stop/start reuses the original). |
| **OCI Container Registry (OCIR)** | Private Docker registry in the same tenancy/region (`iad.ocir.io`). Minimal latency for image pulls. Images tagged with `sha-{hash}` and `latest`. |
| **OCI API Gateway (jde-mcp-gateway)** | Fronts the **MCP server** with HTTPS termination and CORS. Provides a stable URL for MCP clients since the container's private IP changes on each deploy. Backend IP auto-updated by deploy pipeline. |
| **OCI API Gateway (E1_GatewayAPI_Ext)** | Fronts the raw **JDE AIS server** with HTTPS termination and Basic Auth header injection. The MCP server does NOT use this — it talks to AIS directly. |

## CI/CD

| Tool | Version | Why |
|------|---------|-----|
| **GitHub Actions** | — | CI (`ci.yml`) runs on every PR: lint, build, type-check. CD (`deploy.yml`) runs on push to `main`: build image, push to OCIR, deploy container, update gateway, health check. |
| **OCI CLI** | Latest | Installed in deploy pipeline to manage container instances, query VNICs, and update API Gateway deployments. Configured from GitHub Secrets at runtime. |
| **Docker** | Multi-stage | Build context uses `--platform linux/amd64 --provenance=false --sbom=false` for OCI Container Instance compatibility. |

## Container

| Component | Detail |
|-----------|--------|
| **Base Image** | `node:22-alpine` |
| **Build** | Multi-stage (builder + production). Builder compiles TS; production only has runtime deps. |
| **User** | Non-root `mcp` user |
| **Health Check** | `wget` against `/health` every 30s |
| **Transport** | HTTP on port 3000 (`TRANSPORT=http`) |
| **MCP Endpoint** | `POST /mcp` (Streamable HTTP) |
