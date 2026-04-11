# Learning Log

Lessons learned during development, organized by topic. Updated whenever a concern is resolved.

---

## JDE AIS API

### AIS only supports API version v2
- **Problem:** Setting `JDE_API_VERSION=v3` caused 404 errors on `/v3/dataservice`.
- **Root cause:** The AIS server at `132.145.130.131:8006` does not support v3 endpoints.
- **Fix:** Default to `v2` in `constants.ts`. Removed hardcoded `v3` from the container deploy spec.
- **Rule:** Always use `v2` unless Oracle documents v3 support for this AIS release.

### AIS response keys are dynamic
- **Problem:** Code expected `fs_DATABROWSE` but AIS returned `fs_DATABROWSE_F0101`.
- **Root cause:** AIS appends the table name to the response key: `fs_DATABROWSE_{tableName}`.
- **Fix:** `queryTable()` normalizes the response by searching for any key starting with `fs_DATABROWSE`.

### Filter controlId must include the table prefix
- **Problem:** Filters with bare aliases (e.g. `DOCO`) returned empty results or errors.
- **Root cause:** AIS conditions require `{TableName}.{Alias}` format (e.g. `F4211.DOCO`).
- **Fix:** `addFilter()` helper auto-prefixes the table name.
- **Note:** `returnControlIDs` does NOT need the prefix — bare aliases work there.

### Environment and role are mandatory
- **Problem:** Omitting `environment` or `role` from the request body caused 503 errors.
- **Fix:** Always include `"environment": "JPY920"` and `"role": "*ALL"` in every AIS request.

### Basic Auth is simpler and more reliable than token auth
- **Problem:** Token-based auth (`/v2/tokenrequest`) returned 200 but subsequent data service calls failed.
- **Root cause:** Unknown — possibly token format or session management issue.
- **Fix:** Switched to stateless Basic Auth (`Authorization: Basic {base64}`) on every request. No token lifecycle needed.

### Table introspection trick — omit returnControlIDs
- **Discovery:** When you query a table via AIS Data Service WITHOUT specifying `returnControlIDs`, AIS returns ALL exposed columns for that table.
- **Use case:** This is how Layer 0 discovers column structure dynamically — query with no columns → parse response keys like `F0101_AN8` → extract alias `AN8`.
- **Limitation:** Only returns columns that AIS exposes (not necessarily all physical table columns).

---

## JDE System Tables

### F9210 is global, NOT per-table
- **Problem:** Assumed F9210 stores one row per table-column pair. Queried `F9210` filtered by table name → got 503 errors.
- **Root cause:** F9210 stores one row per **data item** globally. There is no "table name" column in F9210. A data item like `AN8` exists once and is used by many tables.
- **Fix:** Layer 0 first introspects the target table to get alias list, then queries F9210 filtered by those aliases for metadata enrichment.

### F0092 is user preferences, NOT Object Librarian
- **Problem:** Assumed F0092 was the Object Librarian for searching tables by name.
- **Root cause:** F0092 stores user preferences/profiles. The columns `SIOBNM` and `SIMD` don't exist in it.
- **Fix:** Use **F9860** (Object Configuration Manager) for table search. It has `OBNM` (object name) and `MD` (description) columns.

### F9860 is the correct table for searching JDE objects
- **Columns:** `OBNM` (object name, e.g. `F0101`), `MD` (description, e.g. `Address Book Master`)
- **Operator:** Use `STR_CONTAIN` for keyword search on both columns.

---

## OCI Container Instances

### Container instances are immutable
- **Problem:** After deploying a new image, tried to stop/start the container instance to pick up the new image.
- **Root cause:** OCI Container Instances reuse the original image on start. There's no "pull latest" mechanism.
- **Fix:** Deploy pipeline deletes the old instance and creates a new one every time. The `OCI_CONTAINER_INSTANCE_ID` secret must be updated after each deploy.

### Container spec must be generated at runtime
- **Problem:** Hardcoding credentials in `container-instance-spec.json` would expose secrets in the repo.
- **Fix:** The deploy pipeline generates the spec JSON from GitHub Secrets using a Python one-liner. No credentials in the repo.

### Required Docker build flags
- **Flags:** `--platform linux/amd64 --provenance=false --sbom=false`
- **Why:** OCI Container Instances only support `linux/amd64`. The `--provenance=false --sbom=false` flags prevent Docker from creating multi-architecture manifests that OCI doesn't understand.

---

## OCI Infrastructure

### Two OCI tenancies — use the right profile
- **DEFAULT profile:** cantex tenancy (Phoenix region) — NOT where the MCP server runs
- **cl-oci-lab profile:** centrijde tenancy (Ashburn region) — this is where the MCP server runs
- **Rule:** Always use `--profile cl-oci-lab` when running OCI CLI commands for this project.

### OCIR login format
- **Region code:** `iad` (NOT `us-ashburn-1`)
- **Username:** `idxoqn0ijjyv/Default/gsantos@centrilogic.com` (namespace/identity-domain/user)
- **Password:** OCI Auth Token (from `OCI_AUTH_TOKEN` secret)

### API Gateway backend IP must be updated on deploy
- **Problem:** After deploying a new container, the gateway still pointed to the old container's private IP → 502 errors.
- **Fix:** Deploy pipeline queries the new container's VNIC for its private IP, then updates the gateway deployment spec with the new backend URL. Fully automated.

---

## Git & GitHub

### Branch protection prevents direct pushes
- **Setup:** `main` branch requires CI to pass + PR approval before merge.
- **Workflow:** Create feature branch → push → open PR → CI runs → merge → CD deploys.
- **Important:** Never force-push to `main`.

### Renaming master to main
- **Commands used:**
  ```bash
  git branch -m master main
  git push -u origin main
  # Then update default branch in GitHub Settings → Branches
  # Delete old master: git push origin --delete master
  ```

### Status check name must match exactly
- **CI job name:** `CI / Build & Verify` — this is what GitHub branch protection uses to gate merges.
- **If renamed:** Update the branch protection rule to match the new job name or PRs won't be mergeable.

---

## MCP Protocol

### Streamable HTTP requires Accept header
- **Problem:** MCP clients that don't send `Accept: application/json, text/event-stream` get rejected.
- **Fix:** The API Gateway injects this header on all requests to `/mcp`, so MCP clients don't need to worry about it.

### Session management with mcp-session-id
- **How it works:** First request to `/mcp` creates a session. Server returns `mcp-session-id` header. Client must include it in subsequent requests.
- **CORS:** Gateway exposes `mcp-session-id` header via `Access-Control-Expose-Headers`.
