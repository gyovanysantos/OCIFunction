# jde-mcp-server

[![CI](https://github.com/gyovanysantos/jde-mcp-server-template/actions/workflows/ci.yml/badge.svg)](https://github.com/gyovanysantos/jde-mcp-server-template/actions/workflows/ci.yml)
[![Deploy](https://github.com/gyovanysantos/jde-mcp-server-template/actions/workflows/deploy.yml/badge.svg)](https://github.com/gyovanysantos/jde-mcp-server-template/actions/workflows/deploy.yml)

MCP server for JD Edwards EnterpriseOne — **AP/GL Integrity Analysis** + generic JDE table queries via AIS REST services.

## Architecture

```
Agent → MCP Server → AIS REST API → JDE EnterpriseOne
```

**Reads** go directly to the AIS Data Service (fast, flexible).
**Writes** go through JDE Orchestrations (generic escape hatch).

## Tool Catalog — 9 Tools

### AP/GL Integrity (R047001A)

| Tool | Purpose | Annotation |
|------|---------|------------|
| `jde_ap_voucher_query` | Query AP vouchers (F0411) with filters for company, supplier, GLPT, dates | readOnly |
| `jde_gl_balance_query` | Query GL account balances (F0901) by company, account, ledger type | readOnly |
| `jde_gl_detail_query` | Query GL journal entries (F0911) with filters | readOnly |
| `jde_ap_gl_integrity_check` | Composite check: compares AP subledger vs GL for a company/period | readOnly |

### Dynamic Discovery

| Tool | Purpose |
|------|---------|
| `jde_discover_table` | Discover table structure from JDE metadata (F9210/F9200) |
| `jde_search_tables` | Search for JDE tables by keyword (F0092) |

### Data Dictionary

| Tool | Purpose |
|------|---------|
| `jde_dictionary_search` | Search for tables/columns by keyword |
| `jde_dictionary_list` | List all curated tables |
| `jde_dictionary_table` | Get full column definitions for a table |

### Generic Fallback

| Tool | Purpose |
|------|---------|
| `jde_query_table` | Query any JDE table with custom columns/filters |
| `jde_call_orchestration` | Call any named orchestration |

## Setup

### 1. Install

```bash
cd jde-mcp-server
npm install
npm run build
```

### 2. Configure AIS Connection

```bash
cp .env.example .env
# Edit with your AIS server URL and credentials
```

### 3. Run

**stdio (Claude Desktop / Claude Code):**
```bash
npm start
```

**HTTP (remote):**
```bash
TRANSPORT=http PORT=3000 npm start
```

## Claude Desktop Config

```json
{
  "mcpServers": {
    "jde": {
      "command": "node",
      "args": ["/path/to/jde-mcp-server/dist/index.js"],
      "env": {
        "JDE_AIS_URL": "https://your-ais-server:port/jderest",
        "JDE_USERNAME": "your_user",
        "JDE_PASSWORD": "your_password",
        "JDE_ENVIRONMENT": "JDV920",
        "JDE_ROLE": "*ALL"
      }
    }
  }
}
```

## VS Code / Claude Code Config

Add to `.mcp.json` in workspace root:

```json
{
  "servers": {
    "jde": {
      "command": "node",
      "args": ["./jde-mcp-server/dist/index.js"],
      "env": {
        "JDE_AIS_URL": "https://your-ais-server:port/jderest",
        "JDE_USERNAME": "your_user",
        "JDE_PASSWORD": "your_password",
        "JDE_ENVIRONMENT": "JDV920"
      }
    }
  }
}
```

## File Structure

```
jde-mcp-server/
├── package.json
├── tsconfig.json
├── .env.example
├── README.md
├── src/
│   ├── index.ts                    # Entry point — registers all tools
│   ├── types.ts                    # AIS and dictionary type definitions
│   ├── constants.ts                # Environment config, limits
│   ├── data/
│   │   └── dictionary.json         # Curated table/column definitions
│   ├── schemas/
│   │   └── tools.ts                # Zod input schemas for all tools
│   ├── services/
│   │   ├── ais-client.ts           # AIS REST client (auth, data, orch)
│   │   ├── dd-discovery.ts         # Live table discovery via F9210/F9200
│   │   └── dictionary.ts           # Dictionary search/lookup service
│   └── tools/
│       ├── dictionary.ts           # Dictionary lookup tools
│       ├── discovery.ts            # Dynamic table discovery tools
│       ├── integrity.ts            # AP/GL integrity tools (R047001A)
│       ├── query.ts                # Generic table query tool
│       └── orchestration.ts        # Generic orchestration call tool
```
