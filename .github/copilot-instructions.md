# Copilot Instructions — OCIFunction

## Project Overview
Multi-architecture JDE Integrity Report Analyzer with two versions:
- **v1.0 (Production)**: OCI serverless Function (Python 3.11) — direct LLM inference via OCI GenAI (no RAG/KB).
- **v2.0 (In Development)**: Multi-agent architecture using Microsoft Foundry Agent Framework (Python 3.12) + JDE MCP Server (TypeScript/Node.js 22), deployed to Azure Container Apps.

## Key Files

### v1.0 — OCI Function
- `func.py` — Production handler (uses `resource_principal` auth, deployed via Docker/OCIR).
- `quickstart.py` — Local dev/test script (uses `api_key` auth from `~/.oci/config` DEFAULT profile).
- `requirements.txt` — v1.0 Python deps (fdk, oci, pypdf).
- `Dockerfile` — v1.0 OCI Function container (fnproject/python:3.11).

### v2.0 — Multi-Agent + MCP
- `agents/extractor/agent.py` — ExtractorAgent: downloads PDF from OCI + extracts text.
- `agents/analyzer/agent.py` — AnalyzerAgent: cross-references PDF findings against live JDE data via MCP.
- `agents/extractor/app.py` — Standalone HTTP entry point for ExtractorAgent (port 8088).
- `agents/analyzer/app.py` — Standalone HTTP entry point for AnalyzerAgent (port 8088).
- `agents/workflow.py` — Sequential workflow: Extractor → Analyzer.
- `agents/app.py` — Workflow orchestration entry point.
- `jde-mcp-server-template/` — JDE MCP Server (git subtree from `gyovanysantos/jde-mcp-server-template`).
- `docker-compose.yml` — Local dev: 3 services (mcp, extractor, analyzer).
- `.env.example` — Root env template for docker-compose.
- `agents/.env` — Agent env vars (production MCP URL).

### Documentation
- `PLAN.md` — Project log: all decisions, architecture changes, and deployment history. Update when significant changes happen.
- `ARCHITECTURE.md` — Formal architecture document for stakeholders. Update on any architectural change.
- `TECH-STACK.md` — All technologies, versions, and why each is used. Update on any dependency change.

## OCI Environment (v1.0)
- **Compartment**: jdee1 (`ocid1.compartment.oc1..aaaaaaaamxleq3holrutfb7hih7u4nq42mam77a3ye6m5ufgaqx4itdfxr6a`)
- **Region**: us-phoenix-1
- **Model**: `google.gemini-2.5-flash` (on-demand serving)
- **Bucket**: `OBJECTSTORAGE` (namespace: `idxoqn0ijjyv`)
- **OCI profile**: `DEFAULT` in `~/.oci/config`

## Azure Environment (v2.0)
- **Subscription**: CLSandbox2 (`74528fbf-d0fa-4d72-b3ef-dee45c2a8293`)
- **Resource Group**: `rg-hackathon-2603`
- **ACR**: `acrjdemcppo.azurecr.io`
- **Container Apps Environment**: `jde-mcp-env` (East US)
- **MCP Container App**: `jde-mcp-integrity` → `https://jde-mcp-integrity.bluedesert-fb732cac.eastus.azurecontainerapps.io`
- **Foundry Project**: `gsantos-hackaton26` (endpoint: `gsantos-hackaton26-resource.services.ai.azure.com`)
- **Foundry Model**: `gpt-4.1`

## Code Conventions

### v1.0 (Python 3.11 — OCI Function)
- `func.py` authenticates with `oci.auth.signers.get_resource_principals_signer()` — never use api_key auth there.
- `quickstart.py` authenticates with `oci.config.from_file("~/.oci/config", "DEFAULT")` — for local testing only.
- Keep both files in sync: same prompts, same constants, same analysis logic.
- API contract: `{"object_name", "prompt"}` → `{"checkerResponse", "analysisResponse"}`.

### v2.0 (Python 3.12 — Foundry Agents)
- Agents use `azure.identity.aio.DefaultAzureCredential` (async) for Foundry auth.
- Agent framework: `agent-framework-core==1.0.0rc3`, hosting adapter `azure-ai-agentserver-agentframework==1.0.0b16`.
- Each agent has its own `app.py`, `Dockerfile`, and `requirements.txt` for independent containers.
- MCP tools are defined in `jde-mcp-server-template/src/tools/integrity.ts`.

### v2.0 (TypeScript — JDE MCP Server)
- Node.js 22, TypeScript 5.x, MCP SDK ^1.12.0, Express ^4.21.0, Zod ^3.23.0.
- 5-layer tool architecture (see ARCHITECTURE.md Section 13).
- HTTP transport on port 3000; endpoints: `/mcp` (MCP), `/health` (health check).

## Deployment

### v1.0 — OCI Function
- Docker build → push to OCIR → `fn deploy` (or manual update via OCI Console).
- API Gateway endpoint: `POST /v1/analyze`.
- Function timeout: 300s, memory: 1024 MB.

### v2.0 — Local Dev
- `docker compose up --build` — starts MCP (port 3000), Extractor (port 8088), Analyzer (port 8089).
- MCP_SERVER_URL inside docker-compose is `http://mcp:3000/mcp` (Docker internal network).

### v2.0 — Azure Container Apps (MCP)
- ACR image: `acrjdemcppo.azurecr.io/jde-mcp-integrity:v1`
- Container App: `jde-mcp-integrity` in `jde-mcp-env`
- Push via: `docker tag` + `docker push` (NOT `az acr build` — cloud builds crash).
- FQDN: `https://jde-mcp-integrity.bluedesert-fb732cac.eastus.azurecontainerapps.io`

## Important Rules
- Do NOT introduce RAG, Knowledge Bases, or OpenSearch — direct LLM inference is the chosen architecture (v1.0).
- Do NOT change auth patterns in func.py (resource_principal) or quickstart.py (api_key).
- Do NOT touch the `jde-mcp-po` Container App — it belongs to another project. Our app is `jde-mcp-integrity`.
- When modifying v1.0 analysis logic, update both `func.py` and `quickstart.py`.
- When modifying MCP tools, update `jde-mcp-server-template/src/tools/integrity.ts` and rebuild the container.
- Test locally with `docker compose up` before deploying to Azure.
- Test v1.0 locally with `quickstart.py` before deploying to OCI.

## BE DIDACTIC
You are the specialist and the user is a Junior. be didatic.

## ARCHITECTURE.md
A ARCHITECTURE.md file should contain all the project architecure. Make sure to always update it if any changes.

## TECH-STACK.md
All the Tech Stack being used on the code and its version should be on TECH-STACK.md and each component should have an explanation why it's being used. Make sure to always update it if any changes.

## LEARNING.md
A LEARNING.md file should be updated everytime a user has a concern with the right answer. Separate the file by Topics (e.g API, libraries, packages, git)

## GIT COMMANDS
The user has only worked with git an github alone. Assist user to use Git commands and GitHub collaboratively. 

## Workflow Orchestration ##

1. Plan Mode Default
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately — don't keep pushing
- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity

2. Subagent Strategy
- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One task per subagent for focused execution

3. Self-Improvement Loop
- After ANY correction from the user: update `LESSONS.md` with the pattern
- Write rules for yourself that prevent the same mistake
- Ruthlessly iterate on these lessons until mistake rate drops
- Review lessons at session start for relevant project

4. Verification Before Done
- Never mark a task complete without proving it works
- Diff your behavior between main and your changes when relevant
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness

5. Autonomous Bug Fixing
- When given a bug report: just fix it. Don't ask for hand-holding
- Point at logs, errors, failing tests — then resolve them
- Zero context switching required from the user
- Go fix failing CI tests without being told how

Task Management

1. Plan First: Write plan to `tasks/todo.md` with checkable items 
2. Verify Plan: Check in before starting implementation 
3. Track Progress: Mark items complete as you go 
4. Explain Changes: High-level summary at each step 
5. Document Results: Add review section to `tasks/todo.md` 
6. Capture Lessons: Update `LESSONS.md` after corrections 

Core Principles

- Simplicity First: Make every change as simple as possible. Impact minimal code.
- No Laziness: Find root causes. No temporary fixes. Senior developer standards.
- Minimal Impact: Changes should only touch what's necessary. Avoid introducing bugs.

## MEMORY PERSISTENCE
CREATE A MEMORY.md to save project context so you pick up where you left off
