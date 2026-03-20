# OCI GenAI — JDE Integrity Report Analyzer (Direct LLM Inference)

## Summary
OCI Function that analyzes JDE Integrity Reports stored in Object Storage.
Downloads the PDF directly, extracts text with pypdf, checks for content (code-based checker),
and sends the full document text to OCI GenAI Inference API (google.gemini-2.5-flash) for analysis.
No Agent or Knowledge Base — direct LLM inference with the document text in the prompt.

## Architecture (v0.0.24 — Direct Inference)
- Client (REST) → API Gateway → OCI Function (func.py) → Object Storage (download PDF) → pypdf (extract text) → GenAI Inference API (analyze)
- **Removed**: GenAI Agent, Knowledge Base (RAG), OpenSearch index
- **Why**: RAG retrieves chunks by semantic similarity across ALL indexed documents, making it impossible to reliably target a specific PDF. Direct inference with full document text eliminates cross-document contamination.

## OCI Resources
- Compartment: jdee1 (`ocid1.compartment.oc1..aaaaaaaamxleq3holrutfb7hih7u4nq42mam77a3ye6m5ufgaqx4itdfxr6a`)
- Region: us-phoenix-1
- Existing Agent Endpoint: `ocid1.genaiagentendpoint.oc1.phx.amaaaaaa7bibg4qab6x5xdg5lekkmyura2cuoxyqsumbx7dijl7wlhn5gwpq`

---

## Phase 1: OCI Console — Knowledge Base & Agent Config

### Step 1.1: Create/Use Object Storage Bucket
- Compartment: jdee1, Region: us-phoenix-1
- Upload sample PDF/JSON/CSV files for testing

### Step 1.2: Create Knowledge Base in OCI GenAI Agents
- OCI Console → AI Services → Generative AI Agents → Knowledge Bases → Create
- Data source: OCI Object Storage
- Point to the bucket from step 1.1
- Supported formats: PDF, JSON, CSV
- The service will create an OpenSearch index and ingest/parse documents automatically

### Step 1.3: Associate Knowledge Base with Existing Agent
- Navigate to the existing GenAI Agent (endpoint above)
- Add the knowledge base as a data source to the agent
- Update agent instructions to reflect document Q&A/summarization purpose
- Re-deploy the agent endpoint if required

---

## Phase 2: Code Changes

### Step 2.1: Update `func.py`
- Change request schema: accept `{"object_name": "report.pdf", "prompt": "Summarize this document"}`
- Construct agent prompt referencing the specific object: e.g., `"Regarding the document '{object_name}': {prompt}"`
- Update agent instructions from weather to document analysis (Q&A, summarization)
- Remove `get_weather` tool definition (no longer needed)
- Keep `resource_principal` auth pattern
- Keep existing error handling structure

### Step 2.2: Update `quickstart.py`
- Mirror changes for local development/testing
- Use `api_key` auth (existing pattern)
- Remove weather tool, update instructions

### Step 2.3: Update `func.yaml`
- Increase `timeout` to 300 (document analysis takes longer)
- Increase `memory` to 1024 for larger payloads

### Changes needed (discovered during deploy)
- `requirements.txt` — added `pydantic>=2.0.0`, `docstring_parser>=0.15`, `rich>=14.0.0` (undeclared transitive dependencies of `oci.addons.adk`)
- `.dockerignore` — created to exclude `.venv/`, `rag/`, `__pycache__/`, diagnostic `.txt` files (reduced Docker context from 461MB to ~5MB)
- `Dockerfile` — no changes needed

---

## Phase 3: OCI Console — API Gateway ✅ COMPLETE

### Step 3.1: Create API Gateway
- Reused existing public gateway `JDE_API_Gateway_Open`
- OCID: `ocid1.apigateway.oc1.phx.amaaaaaa7bibg4qavcw276hx6gxltu2sahmosmjvci2k2u24u3moqpfkmkkq`
- Endpoint: `https://jfiidvdcmm4d2oqweow44nsovq.apigateway.us-phoenix-1.oci.customer-oci.com`

### Step 3.2: Create API Deployment
- Deployment "AgentAnalyze" created: `ocid1.apideployment.oc1.phx.amaaaaaa7bibg4qaubz7f2rxv7wchatpxq3jh53v65t6e3fu3xlrovvzc2ya`
- Path prefix: `/v1`
- Route: `POST /analyze` → OCI Functions backend → `oci-agent-function`
- No authentication (dev mode)

### Step 3.3: IAM Policies for API Gateway
- Created `apigw-functions-policy`: allows API Gateway principal to `use functions-family` in jdee1

### Step 3.4: Private API Gateway Deployment (for JDE AIS)
- Reused existing private gateway `JDE_API_Gateway` on `PrivatRegSub` (10.9.4.0/24)
- Gateway OCID: `ocid1.apigateway.oc1.phx.amaaaaaa7bibg4qacwvjq2xdyds4lfrpnqg34yzebsrgxkkgk5qwdhrthfva`
- Deployment "AgentAnalyze-Private": `ocid1.apideployment.oc1.phx.amaaaaaa7bibg4qasm7ztp2jsgfndgqwi2ok3kjvukefxyctjcfngxarunrq`
- Private endpoint: `https://daa6bnvhau6ufxbsf7n3my4b4y.apigateway.us-phoenix-1.oci.customer-oci.com/v1`
- Route: `POST /analyze` → OCI Functions backend → `oci-agent-function`
- Same function, same IAM policy — traffic stays within the VCN (no NAT needed)

---

## Phase 4: Deploy & Test ✅ COMPLETE

### Step 4.1: Deploy Updated Function
- fn CLI v0.6.48 installed, context configured for Phoenix region
- Docker login to OCIR via auth token for gsantos@centrilogic.com
- Function deployed as v0.0.10 (clean production build)
- Function OCID: `ocid1.fnfunc.oc1.phx.amaaaaaa7bibg4qa6n77gpsbj6hzwui2k7uyqsuw7qaw2iwa2yll3ng4yeoa`
- Image: `phx.ocir.io/axzkbtajofjq/agent-functions/oci-agent-function:0.0.10`

### Step 4.2: IAM for Resource Principal Auth
- Dynamic group `agent-functions-dg` matches `fnfunc` resources in jdee1
- Policy `agent-functions-policy` grants `manage genai-agent-family` and `manage generative-ai-family`

### Step 4.3: Bugs Fixed During Deploy
1. **Event loop conflict**: `agent.run()` calls `loop.run_until_complete()` but FDK already runs in asyncio loop → Fix: made handler `async def`, use `await agent.run_async()`
2. **RunResponse API**: `result.content.text` doesn't exist → Fix: use `result.final_output`
3. **Missing pip dependencies**: `pydantic` and `docstring_parser` are undeclared transitive deps of `oci.addons.adk`

### Step 4.4: End-to-End Test ✅ PASSED
- `fn invoke` with `{"prompt":"hello"}` → `{"response": "I cannot provide an answer..."}`
- `fn invoke` with `{"object_name":"FridayFinishNews.pdf","prompt":"Summarize this document"}` → RAG-grounded summary returned
- `POST /v1/analyze` via API Gateway with same payload → same RAG-grounded summary returned

---

## Verification Checklist
1. ✅ Local test: `quickstart.py` with FridayFinishNews.pdf — RAG-grounded response
2. ✅ Function invoke: `fn invoke` with test JSON payload — working
3. ✅ REST curl: `POST /v1/analyze` with object_name and prompt — working
4. Error cases: missing object_name, missing prompt, nonexistent document

---

## Decisions
- Reuse existing agent endpoint — add knowledge base, don't create a new agent
- RAG approach — knowledge base pre-indexes bucket contents; no custom Object Storage retrieval tool
- Object name included in the prompt so RAG retrieval focuses on that document's content
- API Gateway provides clean REST URL + auth + CORS over direct Function invocation

## Considerations
1. **KB ingestion lag** — New files need re-ingestion. Can be automated via OCI Events if documents change frequently.
2. **API Gateway auth** — No-auth for development; add API key or OAuth2 for production.
3. **Data source prefix** — OCI requires a non-empty prefix (1-255 chars) per `objectStoragePrefixes` entry. To cover all files at bucket root, add one entry per file or use a common folder prefix (e.g. `docs/`). `/` does NOT work as a wildcard. Max 1 ingestion job per data source — delete old jobs before creating new ones.
4. **Ingestion after data source update** — Updating the data source config auto-triggers a CLEANUP + INGESTION job pair. No need to manually create an ingestion job after updating prefixes.

---

## Implementation Log

### 2025-03-15 — Phase 2: Code Changes (COMPLETED)

**`func.py` changes:**
- Removed `get_weather` tool and `@tool` decorator import
- Removed `typing.Dict` import (no longer needed)
- Added `AGENT_INSTRUCTIONS` constant with document analysis prompt
- Changed request body schema: now accepts `{"object_name": "...", "prompt": "..."}`
- `object_name` is optional — when provided, prompt is prefixed with `"Regarding the document '{object_name}': "`
- Removed `tools=[get_weather]` from Agent constructor (agent now uses knowledge base, not custom tools)
- Changed missing-prompt error response from 200 to 400 status code
- Auth remains `resource_principal`

**`quickstart.py` changes:**
- Removed `get_weather` tool, `@tool` decorator, and `typing.Dict` import
- Added `AGENT_ENDPOINT_ID`, `REGION`, `AGENT_INSTRUCTIONS` constants (mirrors func.py)
- Updated `main()` to demonstrate document analysis: builds prompt with object_name + question
- Auth remains `api_key` with `DEFAULT` profile

**`func.yaml` changes:**
- `memory`: 512 → 1024
- `timeout`: 120 → 300

**No changes made to:**
- `requirements.txt` — dependencies unchanged
- `Dockerfile` — build process unchanged

### 2025-03-15 — Phase 1: OCI Infrastructure (COMPLETED)

**Step 1.1: Object Storage Bucket — DONE**
- Created bucket: `agent-knowledge-base`
- Uploaded: `FridayFinishNews.pdf` (from local `rag/` folder)

**Step 1.2: Knowledge Base — DONE**
- Name: `agent-knowledge-base`
- KB OCID: `ocid1.genaiagentknowledgebase.oc1.phx.amaaaaaa7bibg4qadai3yjw2n6xjqvmxlfyn3fjhex3ehgjttuba5f4cpy3q`
- State: **ACTIVE**
- Data source created: `agent-knowledge-base-ds`
  - DS OCID: `ocid1.genaiagentdatasource.oc1.phx.amaaaaaa7bibg4qabzt2maibupowl57a76zhjewqp3lbwf2kq7u3yrbsyaia`
  - Prefix: `FridayFinishNews.pdf`
  - State: **ACTIVE**
- Ingestion job: `initial-ingestion` — **SUCCEEDED**
  - Job OCID: `ocid1.genaiagentdataingestionjob.oc1.phx.amaaaaaa7bibg4qayfs6ip3woqwlcb7as6wmm4gm3b5eo3lvqt6jn5leqzra`

**Step 1.3: Associate with Agent — DONE**
- Endpoint `AI-Agent-NoTools-Endpoint` belongs to agent `AI-Agent-NoTools`
  - Agent OCID: `ocid1.genaiagent.oc1.phx.amaaaaaa7bibg4qa7dpljs4rootjqw7iaqzdm5j2ehirjary5c6twwnpkgda`
- Updated agent:
  - `knowledge-base-ids` → added KB OCID
  - `instruction` → updated to document analysis assistant prompt
  - `description` → "Document analysis agent with Knowledge Base RAG"
- Created RAG tool: `document-rag-tool`
  - Tool OCID: `ocid1.genaiagenttool.oc1.phx.amaaaaaa7bibg4qagbbwxx7bfiednssd7pyrowgukconlttjycyj63xtqg6a`
  - State: **ACTIVE**
- Old `get_weather` tool auto-removed by ADK during sync

**Step 1.4: Local Test — PASSED**
- `quickstart.py` successfully summarized `FridayFinishNews.pdf` using RAG
- Agent returned grounded response about Centrilogic weekly newsletters

### Pending: Phase 3 (API Gateway) — READY, waiting for function deploy
- Existing public gateway: `JDE_API_Gateway_Open`
  - Gateway OCID: `ocid1.apigateway.oc1.phx.amaaaaaa7bibg4qavcw276hx6gxltu2sahmosmjvci2k2u24u3moqpfkmkkq`
  - Hostname: `jfiidvdcmm4d2oqweow44nsovq.apigateway.us-phoenix-1.oci.customer-oci.com`
- [ ] Create deployment: `POST /v1/analyze` → OCI Function (needs function OCID from Phase 4)

### Pending: Phase 4 (Deploy & Test) — BLOCKED (Docker/WSL2 broken, needs reboot)
- Functions app: `agent-app` (`ocid1.fnapp.oc1.phx.amaaaaaa7bibg4qaocgvbxdiwnete6q33m7ruullxy4zca5iqmk7fhtz75jq`)
- No functions deployed yet in this app
- `fn` CLI: **not installed** — need to install after reboot
- Docker Desktop v29.2.1: **BROKEN** — stuck in `"starting"` state, root cause is WSL2
- **Root cause**: WSL2 service (`WslService`) entered `StopPending` and can't recover without reboot
  - Docker backend log: infinite loop polling `/backend/state` returning `{"docker":"starting","state":"starting"}`
  - Docker engine responds HTTP 500 to `_ping` health checks
  - Lingering `wsl.exe` processes blocked Docker startup; Docker tried to kill them but timed out
  - All WSL commands (`wsl -l -v`, `wsl --shutdown`) hang or produce no output
  - WSL service restart (via elevated PowerShell) went to `StopPending` and stuck there
- **Fix**: Reboot machine. After reboot, Docker Desktop should start cleanly
- API Gateway: decided to **keep it** for public REST access (no OCI SDK/IAM signing needed by callers)
  - Without gateway, function can only be invoked via `fn invoke` or OCI SDK (requires IAM auth)
  - With gateway, get a clean `POST https://hostname/v1/analyze` callable from anywhere
- Steps when ready:
  1. Ensure Docker Desktop is running after reboot
  2. Install fn CLI: download from GitHub releases or `choco install fn`
  3. Configure fn context for Phoenix: `fn create context phoenix --provider oracle` then set api-url, registry, compartment
  4. `fn deploy --app agent-app` (builds Docker image, pushes to OCIR, creates function)
  5. Get function OCID from `oci fn function list --application-id <app-ocid>`
  6. Create API Gateway deployment: `POST /v1/analyze` → function OCID
  7. End-to-end test: `curl -X POST https://<gateway-hostname>/v1/analyze -d '{"object_name":"FridayFinishNews.pdf","prompt":"Summarize"}'`

---

### 2025-03-19 — Checker Simplified (v0.0.21)

**Decision**: The bucket will only contain JDE Integrity Reports going forward, so the checker no longer needs to classify document types. It now simply asks: *"Does this Integrity Report contain any data entries or error records?"*

**Changes:**
- Removed JDE-specific classification logic (`_JDE_KEYWORDS` list, document type matching)
- Simplified `CHECKER_INSTRUCTIONS` — just checks for content/data, not document type
- Checker prompt uses explicit document targeting: `"Look up the document named exactly '{object_name}'"`
- Analyzer prompt also uses explicit document targeting to ensure RAG retrieval focuses on the correct file
- `quickstart.py` updated to match

**Testing:**
- `R007011_CAN0001_32083_PDF.pdf` → checkerResponse: Yes, analysisResponse: correct Cantex Unposted Batches analysis with error codes 10009/7968/7740
- Deployed as v0.0.21

---

### 2025-03-19 — Architecture Change: Remove Agent+KB, Direct LLM Inference (v0.0.24)

**Problem**: After 7+ prompt engineering iterations (v0.0.17–v0.0.23), RAG fundamentally cannot target a specific document. It retrieves chunks by semantic similarity across ALL indexed documents, causing:
- Wrong document content returned when querying for a specific file
- Empty reports getting "Yes" analysis from other documents' chunks
- "Document not found" disclaimers because KB indexes content chunks, not filenames

**Decision**: Remove Agent + Knowledge Base entirely. The use case is analyzing ONE specific PDF per call — not searching across documents. RAG adds complexity for no benefit.

**New Architecture:**
1. **Code-based checker**: Download PDF from Object Storage → extract text with pypdf → check `len(text) > 300` chars
2. **Direct LLM call**: Send full document text to `GenerativeAiInferenceClient.chat()` with system prompt
3. Same REST API contract: `{"object_name", "prompt"}` → `{"checkerResponse", "analysisResponse"}`

**Code Changes:**
- `func.py` — Complete rewrite:
  - Removed: `oci.addons.adk`, Agent, async handler
  - Added: `ObjectStorageClient.get_object()`, `PdfReader`, `GenerativeAiInferenceClient.chat()`
  - Handler changed from `async def` to regular `def`
  - Auth: `resource_principal` for both ObjectStorage and GenAI clients
- `quickstart.py` — Complete rewrite mirroring func.py with `api_key` auth
- `requirements.txt` — Simplified: `fdk>=0.1.105`, `oci>=2.168.0`, `pypdf>=4.0.0` (removed pydantic, docstring_parser, rich)
- Model: `google.gemini-2.5-flash` (1M token context, confirmed working in us-phoenix-1)

**IAM Policy Added:**
- Created `fn-objectstorage-read`: `Allow dynamic-group agent-functions-dg to read object-family in compartment jdee1`
- Existing policies still apply: `manage generative-ai-family` (for inference), `manage genai-agent-family` (legacy, can remove later)

**Testing (all passed):**
- Local `quickstart.py` with R007011: checker=Yes (73,925 chars, 31 pages), detailed JDE analysis
- `fn invoke` with R007011: checker=Yes, correct analysis, no cross-document contamination
- `fn invoke` with nonexistent file: 404 error returned correctly
- `POST /v1/analyze` via public API Gateway: checker=Yes, correct analysis
- Deployed as v0.0.24

### 2025-03-19 — System Prompt Tuning (v0.0.25, v0.0.26)

**v0.0.25**: Added "4) Limit output to 1200 tokens" to system prompt to constrain response length.

**v0.0.26**: Replaced token limit with adaptive word cap:
- "Accommodate the response to the content of the report — if it is very long, focus on summarizing key issues. It should not be a response with more than 850 words."
- Deployed as v0.0.26

**v0.0.27**: Fixed truncated `analysisResponse` — the GenAI API was cutting output at its default max_tokens limit.
- Added `max_tokens=4096` to `GenericChatRequest` to allow the full response through.
- System prompt word cap (850 words) still controls length; `max_tokens` just prevents API-level truncation.
- Deployed as v0.0.27