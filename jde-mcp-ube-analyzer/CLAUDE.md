## BE DIDACTIC
You are the specialist and the user is a Junior. be didatic.

## docs/ARCHITECTURE.md
A ARCHITECTURE.md file should contain all the project architecure. Make sure to always update it if any changes.

## docs/TECH-STACK.md
All the Tech Stack being used on the code and its version should be on TECH-STACK.md and each component should have an explanation why it's being used. Make sure to always update it if any changes.

## docs/LEARNING.md
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

# Project Guidelines

## Overview

TypeScript MCP (Model Context Protocol) server bridging AI agents to JD Edwards EnterpriseOne via the AIS REST API. Implements AP/GL Integrity analysis tools and generic JDE queries through a 4-layer tool architecture.

## Architecture

```
Agent → MCP Server → AIS REST API → JDE EnterpriseOne
```

**4-layer tool design:**

| Layer | Purpose | Examples |
|-------|---------|---------|
| 0 – Discovery | Live table structure from JDE | `jde_discover_table`, `jde_search_tables` |
| 1 – Dictionary | Curated data dictionary lookups | `jde_dictionary_search`, `_list`, `_table` |
| 2 – Curated | AP/GL Integrity analysis (R047001A) | `jde_ap_voucher_query`, `jde_ap_gl_integrity_check` |
| 3 – Generic | Escape hatch for any table/orch | `jde_query_table`, `jde_call_orchestration` |

**Key rule:** Write operations route through orchestrations (business rules enforced). Read operations use AIS Data Service directly.

## Build and Run

```bash
npm install          # Install dependencies
npm run build        # TypeScript → dist/ (tsc)
npm run dev          # Watch mode (tsx)
npm start            # Run MCP server (stdio by default)
```

HTTP transport: set `TRANSPORT=http` and optionally `PORT=3000`.

## Environment Variables

Required in `.env` (see `.env.example`):

| Variable | Required | Default |
|----------|----------|---------|
| `JDE_AIS_URL` | Yes | — |
| `JDE_USERNAME` | Yes | — |
| `JDE_PASSWORD` | Yes | — |
| `JDE_ENVIRONMENT` | No | `JDV920` |
| `JDE_ROLE` | No | `*ALL` |
| `TRANSPORT` | No | `stdio` |
| `PORT` | No | `3000` |

## Code Style and Conventions

- **ES modules** — `"type": "module"` in package.json; use `.js` extensions in import paths even for TS files
- **Zod schemas** with `.strict()` for all tool inputs — reject unknown fields
- **MCP tool annotations** — always set `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`
- **Response truncation** — all tool responses capped at `CHARACTER_LIMIT` (50,000 chars)
- **Token caching** — AIS token refreshes every 25 min (before 30-min expiry); graceful logout on SIGINT/SIGTERM

### Naming

| Element | Pattern | Example |
|---------|---------|---------|
| Tool registration functions | `register{Name}()` | `registerApVoucherQuery()` |
| MCP tool names | `jde_{operation}_{target}` | `jde_ap_voucher_query` |
| Zod schemas | `Jde{Name}Schema` | `JdeApVoucherQuerySchema` |
| Inferred types | `Jde{Name}Input` | `JdeApVoucherQueryInput` |
| Constants | `UPPER_SNAKE_CASE` | `DEFAULT_MAX_PAGE_SIZE` |
| Helpers | `camelCase` | `addFilter()`, `buildConditions()` |
| JDE tables | F-prefix + digits | `F0411`, `F0901`, `F0911` |
| JDE column aliases | 2-4 uppercase chars | `DOCO`, `AN8`, `GLPT` |

### Project Structure

```
src/
  index.ts              # Entry point — server init, tool registration, transport
  constants.ts           # Env-backed config constants
  types.ts               # AIS request/response types, dictionary types, pagination
  schemas/
    tools.ts             # All Zod input schemas for MCP tools
  services/
    ais-client.ts        # AIS REST client — token mgmt, data/orch calls
    dd-discovery.ts      # Live table discovery via F9210/F9200
    dictionary.ts        # Dictionary service — load, search, list, resolve columns
  tools/
    dictionary.ts        # Layer 1 — dictionary tool registrations
    discovery.ts         # Layer 0 — dynamic table discovery tools
    integrity.ts         # Layer 2 — AP/GL integrity tools (R047001A)
    query.ts             # Layer 3 — generic table query tool
    orchestration.ts     # Layer 3 — generic orchestration caller tool
  data/
    dictionary.json      # Curated data dictionary
```

**Dependency flow:** `index.ts` → `tools/*` → `schemas/tools.ts` + `services/*` → `constants.ts` + `types.ts`

## Key Patterns

### Adding a new curated tool

1. Add Zod schema in `src/schemas/tools.ts` with `.strict()` and descriptive field comments
2. Export inferred input type: `export type JdeNewToolInput = z.infer<typeof JdeNewToolSchema>`
3. Implement `registerNewTool(server)` in `src/tools/integrity.ts` (or new file for a different domain)
4. Register in `src/index.ts` within the appropriate layer
5. Set correct MCP annotations (read-only vs destructive)

### Error handling

- Tool handlers return `{ content: [{ type: "text", text }], isError: true }` on failure
- Direct users to `jde_dictionary_search` when queries fail on unknown columns

### AIS query filters

Use the `AisOperator` enum values: `EQUAL`, `NOT_EQUAL`, `LESS`, `GREATER`, `BETWEEN`, `LIST`, `STR_CONTAIN`, `STR_START_WITH`, `STR_END_WITH`, `STR_BLANK`, `STR_NOT_BLANK`.

## Pitfalls

- AIS tokens expire after ~30 min; the client auto-refreshes at 25 min but long-idle sessions may need manual re-auth
- `CHARACTER_LIMIT` truncation can silently drop data on large result sets — prefer filtering over broad queries
- Build copies `src/data/` → `dist/data/` via `shx` — JSON data files are not compiled by tsc
