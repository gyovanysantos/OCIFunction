# Memory — Project Context

## OCI Details

- **Tenancy:** centrijde (profile: `cl-oci-lab`)
- **Region:** us-ashburn-1
- **Compartment (E1LAB):** `ocid1.compartment.oc1..aaaaaaaa6prfynnjyw6tkrm3bmljxluyfjcy2roqyaf65zrmvpoa5qevaexa`
- **OCI User:** `gsantos@centrilogic.com`
- **OCI CLI profile:** Use `--profile cl-oci-lab` (not DEFAULT which points to cantex/Phoenix tenancy)

## Container Instance

- **Public IP:** Changes on each deploy (container is deleted and recreated)
- **Private IP:** Changes on each deploy (auto-discovered by deploy pipeline via VNIC query)
- **Port:** 3000
- **Image:** `iad.ocir.io/idxoqn0ijjyv/jde-mcp-sales-template:latest`
- **Shape:** CI.Standard.E4.Flex (1 OCPU, 2GB RAM)
- **Transport:** HTTP (`TRANSPORT=http`)
- **JDE_API_VERSION:** `v2` (default — v3 is NOT supported by AIS)
- **Immutability:** OCI Container Instances cannot update images via stop/start — must delete and recreate

## Stable MCP Endpoint (via API Gateway)

- **URL:** `https://dwecjmghl667coww5eoz3n3gq4.apigateway.us-ashburn-1.oci.customer-oci.com/mcp`
- **Health:** `https://dwecjmghl667coww5eoz3n3gq4.apigateway.us-ashburn-1.oci.customer-oci.com/mcp` (GET)
- This URL never changes — the deploy pipeline updates the gateway backend to point to the new container's private IP.

## Container Registry

- **Repo:** `iad.ocir.io/idxoqn0ijjyv/jde-mcp-sales-template`
- **Repo OCID:** `ocid1.containerrepo.oc1.iad.0.idxoqn0ijjyv.aaaaaaaaxa4kvug3vbyjj23uivf72gmwwrh53h3c4kti4kcbtycafsddyreq`
- **Visibility:** Private

## MCP API Gateway (jde-mcp-gateway)

- **Gateway OCID:** `ocid1.apigateway.oc1.iad.amaaaaaarxodn6aawibngunqex3tdzxwlf7jegg6d7j5ml7nlzz4t2fjipwa`
- **Deployment OCID:** `ocid1.apideployment.oc1.iad.amaaaaaarxodn6aafkr4ntkrr4j56xk5m4dqrngsyrdpb2dqnxtrl6ku4h5a`
- **Hostname:** `dwecjmghl667coww5eoz3n3gq4.apigateway.us-ashburn-1.oci.customer-oci.com`
- **Route:** `/mcp` → container private IP:3000/mcp
- **CORS:** `*`, exposed header `mcp-session-id`
- **Accept header:** Gateway injects `Accept: application/json, text/event-stream` on all requests
- **Backend IP:** Auto-updated on each deploy by the CD pipeline

## AIS API Gateway (E1_GatewayAPI_Ext) — NOT used by MCP

- **Gateway ID:** `ocid1.apigateway.oc1.iad.amaaaaaarxodn6aa5j64vroeeu3kzndsdwndenxrw32aehun57asidxhlbfa`
- **Deployment ID:** `ocid1.apideployment.oc1.iad.amaaaaaarxodn6aa5frxr4acqfmcubrouimk5o52w3wytagpxphmjkmvc4iq`
- **Hostname:** `c6z5vogwocr44zavycg5wt6kom.apigateway.us-ashburn-1.oci.customer-oci.com`
- **AIS Backend:** `http://132.145.130.131:8006/jderest`
- **Path prefix:** `/jderest`
- **Auth:** Gateway injects `Authorization: Basic` header on ALL routes
- **Note:** MCP server talks directly to AIS, not through this gateway

## Subnet

- **PublicRegSub:** `ocid1.subnet.oc1.iad.aaaaaaaaat6fym4atul3mlh66yvjjp3qlnvvjyijhzighytclzddehhi6fhq`

## JDE Credentials (for container env vars)

- **Username:** GSANTOS
- **Environment:** JPY920
- **Role:** *ALL
- **AIS URL:** `http://132.145.130.131:8006/jderest`

## Auth Strategy

- **Basic Auth** — all AIS requests use `Authorization: Basic` header (base64 of user:pass)
- Token-based auth (`/v2/tokenrequest` + token-in-body) was removed — it returned 200 but caused data service failures
- Both `/dataservice` and `/v2/dataservice` confirmed working with Basic Auth
- No token lifecycle management needed (stateless)

## AIS v2/dataservice Quirks

- **Response key is dynamic:** AIS returns data under `fs_DATABROWSE_{tableName}` (e.g. `fs_DATABROWSE_F0101`), NOT bare `fs_DATABROWSE`. Code normalizes this in `queryTable()`.
- **Filter controlId must be table-prefixed:** Conditions require `{tableName}.{alias}` format (e.g. `F4211.DOCO`), NOT bare alias. `returnControlIDs` accepts bare aliases.
- **Environment is required:** Body must include `environment` (e.g. `JPY920`) and `role`. Omitting gives 503.
- **Docker build flags:** `--platform linux/amd64 --provenance=false --sbom=false` required for OCI Container Instances.
- **OCIR is Private:** Container specs need `imagePullSecrets` with base64-encoded credentials.

## CI/CD Pipeline

- **GitHub Repo:** `gyovanysantos/jde-mcp-server-template` (private)
- **Branch strategy:** `main` is protected (requires CI pass + PR review)
- **CI status check:** `CI / Build & Verify`
- **CD trigger:** Push to `main` → deploy.yml
- **19 GitHub Secrets:** OCI_AUTH_TOKEN, OCI_REGION, OCI_TENANCY_NAMESPACE, OCI_USERNAME, OCI_PRIVATE_KEY, OCI_USER_OCID, OCI_FINGERPRINT, OCI_TENANCY_OCID, OCI_CONTAINER_INSTANCE_ID, JDE_AIS_URL, JDE_USERNAME_VAL, JDE_PASSWORD_VAL, JDE_ENVIRONMENT_VAL, OCIR_PULL_USERNAME_B64, OCIR_PULL_PASSWORD_B64, OCI_SUBNET_ID, OCI_AVAILABILITY_DOMAIN, OCI_COMPARTMENT_ID, OCI_APIGW_DEPLOYMENT_ID

## Dynamic DD Discovery (Layer 0)

- **Approach:** Table introspection — query target table with no `returnControlIDs` → AIS returns all exposed columns → extract aliases from response keys (e.g. `F0101_AN8` → `AN8`)
- **Enrichment:** F9210 provides size/decimals/data type; F9200 provides descriptions
- **Table search:** F9860 (Object Configuration Manager) — searched by `OBNM` (object name) or `MD` (description)
- **Cache:** In-memory `Map<string, DiscoveredTable>` — lives for the MCP server session lifetime
- **Tools:** `jde_discover_table` (full column structure), `jde_search_tables` (find tables by keyword)
- **Tested:** F0101 returns 95 columns, F0911 returns 141 columns

### JDE System Tables for Discovery

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| F9210 | Data Field Specifications (metadata) | FRDTAI (alias), FRCLAS (data type), FRFLDB (size), FRDLAS (decimals) |
| F9200 | Data Item Master (descriptions) | FRDTAI (alias key), FRDSCR (description) |
| F9860 | Object Configuration Manager (table search) | OBNM (object name), MD (description) |

**Note:** F0092 is user preferences, NOT Object Librarian — do not use for table search.

## Pending Work

- [ ] Set up OCI Vault for secrets instead of plain env vars (production hardening)
- [ ] PR #2: Hybrid dictionary — make Layer 1 fall back to Layer 0 when table not in curated dictionary
- [ ] Add monitoring/alerting for container health
