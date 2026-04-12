# Copilot Instructions — OCIFunction

## Project Overview
JDE Integrity Report Analyzer — Multi-agent architecture using OCI Agent Development Kit (ADK) (Python 3.12) + JDE MCP Server (TypeScript/Node.js 22), running on OCI GenAI Agents Service.

## Key Files
- `agents/extractor/agent.py` — ExtractorAgent: downloads PDF from OCI + extracts text (ADK `@tool`).
- `agents/analyzer/agent.py` — AnalyzerAgent instructions for cross-referencing via MCP.
- `agents/mcp_bridge.py` — ADK `@tool` functions that bridge to JDE MCP Server via HTTP (JSON-RPC).
- `agents/workflow.py` — ADK deterministic workflow: `AgentClient` → `Agent.setup()` → sequential `Agent.run()`.
- `agents/api.py` — FastAPI wrapper exposing `POST /v1/analyze` (calls ADK workflow in thread).
- `jde-mcp-server-template/` — JDE MCP Server (git subtree from `gyovanysantos/jde-mcp-server-template`).
- `docker-compose.yml` — Local dev: 2 services (mcp, api).
- `.env.example` — Root env template for docker-compose.

### Documentation
- `PLAN.md` — Project log: all decisions, architecture changes, and deployment history. Update when significant changes happen.
- `ARCHITECTURE.md` — Formal architecture document for stakeholders. Update on any architectural change.
- `TECH-STACK.md` — All technologies, versions, and why each is used. Update on any dependency change.

## Azure Environment — DEPRECATED
> Migrated to OCI. Azure resources may still exist but are no longer used.

## OCI Environment
- **Compartment**: jdee1 (`ocid1.compartment.oc1..aaaaaaaamxleq3holrutfb7hih7u4nq42mam77a3ye6m5ufgaqx4itdfxr6a`)
- **Region**: us-phoenix-1
- **GenAI Agents**: 2 agent endpoints (ExtractorAgent, AnalyzerAgent) — OCIDs in `EXTRACTOR_AGENT_ENDPOINT_ID` / `ANALYZER_AGENT_ENDPOINT_ID`
- **ADK Auth**: `api_key` for local dev, `instance_principal` for OCI compute
- **OCI Profile**: `DEFAULT` in `~/.oci/config`

## Code Conventions

### Python 3.12 — OCI ADK Agents
- Agents use `oci.addons.adk` (`AgentClient`, `Agent`, `@tool`) for OCI GenAI Agents Service.
- Agent framework: `oci[adk]>=2.133.0`.
- Both agents run in-process in the API container (no separate agent containers).
- MCP bridge: `mcp_bridge.py` contains ADK `@tool` functions that call MCP server via httpx.
- MCP tools are defined in `jde-mcp-server-template/src/tools/integrity.ts`.

### TypeScript — JDE MCP Server
- Node.js 22, TypeScript 5.x, MCP SDK ^1.12.0, Express ^4.21.0, Zod ^3.23.0.
- 5-layer tool architecture (see ARCHITECTURE.md Section 13).
- HTTP transport on port 3000; endpoints: `/mcp` (MCP), `/health` (health check).

## Deployment

### Local Dev
- `docker compose up --build` — starts MCP (port 3000) and API (port 8080).
- MCP_SERVER_URL inside docker-compose is `http://mcp:3000/mcp` (Docker internal network).
- OCI config mounted as volume for auth + PDF downloads.

## Important Rules
- When modifying MCP tools, update `jde-mcp-server-template/src/tools/integrity.ts` and rebuild the container.
- Test locally with `docker compose up` before deploying to OCI.

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
