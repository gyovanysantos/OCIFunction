# Generalist JDE MCP — Future Project Plan

## Goal

Build a generalist MCP server capable of querying **any** JDE table without requiring a pre-curated static dictionary. The MCP dynamically discovers table structures from JDE's own Data Dictionary tables at runtime.

## Target Consumer

This MCP will be consumed by a **Microsoft Foundry agent** (not limited to Claude or any specific code assistant). The agent must be able to orchestrate the multi-step discovery and query flow autonomously.

---

## Current State (jde-mcp-sales)

- Static dictionary file (`src/data/dictionary.json`) covers only 5 tables: F4211, F4201, F0101, F4101, F41021
- Querying unknown tables requires manually guessing column aliases
- AIS silently ignores invalid aliases (returns empty columns, no error)
- Scoped to Sales Order domain

## Proposed Architecture

```
Agent (Foundry) → MCP Server → AIS REST API → JDE
                      │
                      ├── Layer 0: Dynamic Discovery (NEW)
                      ├── Layer 1: Cached DD Lookups
                      ├── Layer 2: Curated Domain Tools (existing, optional)
                      ├── Layer 3: Supporting / Validation Tools
                      └── Layer 4: Generic Query + Orchestration
```

---

## JDE Data Dictionary Tables

These system tables store metadata about all JDE objects:

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| **F9210** | Object Table Structure — maps tables to their columns | `SIOBNM` (table name), `SIDSDD` (data item/alias), `SIORDS` (column sequence) |
| **F9200** | Data Item Master — describes each data item | `FRDTAI` (alias), `FRDTAL` (long description), `FRSIZ` (size), `FRDTAS` (data type) |
| **F9202** | Data Field Specifications — display/formatting rules | Decimals, edit rules, formatting |
| **F0092** | Object Librarian — lists all JDE objects | `SIOBNM` (object name), `SIMD` (description), `SIOT` (object type) |

---

## Flow: How a Generalist Query Works

```
1. Agent receives user request
   → e.g. "Show me security records for SYSADMIN in F00950"

2. MCP checks in-memory cache for F00950 metadata
   → Cache miss on first access

3. MCP queries F9210 (table structure)
   → WHERE SIOBNM = 'F00950'
   → Returns all column aliases for that table

4. (Optional) MCP queries F9200 (data item descriptions)
   → For each alias from step 3, get human-readable name and data type
   → e.g. SUSER → "User/Role ID", SOBJ → "Object Name"

5. MCP caches the result in memory
   → Subsequent queries for F00950 skip steps 3-4

6. MCP builds the AIS query using discovered aliases
   → Applies user's filters with correct column names
   → Sends to AIS /v2/dataservice

7. MCP returns structured results to the agent
   → Agent formats and presents to the user
```

---

## New MCP Tools

### `jde_discover_table`
- **Input:** `tableName` (string)
- **Output:** List of columns with alias, description, data type, size
- **Behavior:** Queries F9210 + F9200, caches result, returns column catalog
- **Layer:** 0 (Discovery)

### `jde_smart_query` (enhanced `jde_query_table`)
- **Input:** `tableName`, optional `columns`, optional `filters`, `maxRows`
- **Behavior:**
  - If `columns` provided → use them directly (current behavior)
  - If `columns` omitted → auto-discover via `jde_discover_table`, return all columns
  - If a column alias fails → suggest corrections from the cached DD
- **Layer:** 4 (Generic)

### `jde_list_tables` (optional)
- **Input:** `keyword` (string)
- **Output:** Matching table names and descriptions from F0092
- **Behavior:** Search F0092 by object name or description
- **Use case:** User says "find tables related to security" → returns F00950, F00945, etc.
- **Layer:** 0 (Discovery)

---

## Caching Strategy

| Scope | What's Cached | TTL | Storage |
|-------|---------------|-----|---------|
| Table structure | F9210 results per table | Session lifetime | In-memory Map |
| Data item descriptions | F9200 results per alias | Session lifetime | In-memory Map |
| Full table list | F0092 dump | Session lifetime or 1 hour | In-memory Map |

- Cache is populated on first access (lazy loading)
- Optional: pre-warm cache at startup for high-use tables
- Cache invalidation: restart the MCP server (JDE DD changes are rare)

---

## Challenges & Mitigations

### 1. F9210 Access Permissions
- **Risk:** AIS user may not have security access to query F9210/F9200
- **Mitigation:** Test with current credentials first. If blocked, request read-only access to DD tables for the service account
- **Validation step:** Query `F9210 WHERE SIOBNM = 'F0101'` — if it returns columns, we're good

### 2. Performance Overhead
- **Risk:** Extra AIS round-trip(s) before each user query
- **Mitigation:** In-memory cache eliminates repeated lookups. First query to a new table has ~1-2s extra latency; subsequent queries are instant

### 3. Column Overload
- **Risk:** Some JDE tables have 100+ columns. Returning all hits the CHARACTER_LIMIT (50,000 chars) and overwhelms the agent
- **Mitigation:** Two-step flow:
  1. Discover columns → return list to agent
  2. Agent selects relevant columns based on user intent → query with subset
- The agent (Foundry) must be instructed to do this column selection in its system prompt

### 4. AIS Alias Quirks
- **Risk:** DD lists aliases that AIS Data Service doesn't support (some columns only work via Form Service)
- **Mitigation:** Graceful fallback — if a column returns empty, retry without it and note which columns were unsupported

### 5. Filter controlId Prefix
- **Risk:** AIS requires `{tableName}.{alias}` in filter conditions (already solved in current codebase)
- **Mitigation:** Already handled in `buildConditions()` — carry this forward

---

## Foundry Agent Considerations

The Foundry agent consuming this MCP must be able to:

1. **Multi-step tool orchestration** — Call `jde_discover_table` first, then `jde_smart_query` with selected columns
2. **Column selection** — Given a list of 100+ columns, pick the relevant ones based on the user's natural language query
3. **Error recovery** — If a query returns empty columns, re-query the DD and retry with corrected aliases
4. **Context retention** — Remember discovered table structures within a conversation to avoid redundant discovery calls

### Agent System Prompt Guidance

The Foundry agent's instructions should include:

```
When a user asks to query a JDE table:
1. If the table's columns are unknown, call jde_discover_table first
2. Review the returned columns and select only those relevant to the user's question
3. Call jde_smart_query with the selected columns and any filters
4. If results come back with empty columns, those aliases may not be supported — retry without them
5. Present results in a clear table format
```

---

## Relationship to Current Project (jde-mcp-sales)

- The generalist MCP can be built as an **extension** of the current codebase or as a **new project**
- **Keep curated tools** (Layer 2) — `jde_sales_order_inquiry`, `jde_create_sales_order`, etc. still add value because they embed business logic (header+detail joins, status labels, orchestration routing) that a generic query cannot provide
- The generalist Layer 0 + enhanced Layer 4 complement the curated tools — they handle the "everything else" use cases
- Static `dictionary.json` becomes optional (fallback if F9210 is inaccessible)

---

## Implementation Phases

### Phase 1 — Validate DD Access
- [ ] Test querying F9210 via AIS with current credentials
- [ ] Test querying F9200 via AIS with current credentials
- [ ] Document which DD columns are accessible
- [ ] Confirm alias accuracy by cross-referencing a known table (e.g. F0101)

### Phase 2 — Build Discovery Layer
- [ ] Implement `jde_discover_table` tool
- [ ] Implement in-memory cache for DD results
- [ ] Add F9210/F9200 query logic to `ais-client.ts` (or new `dd-client.ts`)
- [ ] Register tool in MCP server

### Phase 3 — Enhance Generic Query
- [ ] Modify `jde_query_table` → `jde_smart_query` with auto-discovery fallback
- [ ] Handle column-not-supported gracefully
- [ ] Add `jde_list_tables` for table search via F0092

### Phase 4 — Foundry Agent Integration
- [ ] Configure Foundry agent with MCP endpoint
- [ ] Write agent system prompt with multi-step query instructions
- [ ] Test end-to-end: user question → agent → MCP → JDE → formatted answer
- [ ] Tune agent behavior for column selection and error recovery

### Phase 5 — Production Hardening
- [ ] Cache warm-up for frequently used tables
- [ ] Rate limiting on DD queries
- [ ] Logging and observability for discovery calls
- [ ] Security review — ensure DD access doesn't expose sensitive metadata
