# jde-mcp-server

[![CI](https://github.com/gyovanysantos/jde-mcp-server-template/actions/workflows/ci.yml/badge.svg)](https://github.com/gyovanysantos/jde-mcp-server-template/actions/workflows/ci.yml)
[![Deploy](https://github.com/gyovanysantos/jde-mcp-server-template/actions/workflows/deploy.yml/badge.svg)](https://github.com/gyovanysantos/jde-mcp-server-template/actions/workflows/deploy.yml)

MCP server for JD Edwards EnterpriseOne — **Sales Order CRUD lifecycle** via AIS REST services.

## Architecture

```
User → Claude (reasoning) → MCP Server → AIS / Orchestrations → JDE EnterpriseOne
```

**Reads** go directly to the AIS Data Service (fast, flexible).
**Writes** (Create, Update, Delete) go through JDE Orchestrations to enforce business rules.

## Tool Catalog — 11 Tools

### Sales Order CRUD

| Tool | Operation | Target | Annotation |
|------|-----------|--------|------------|
| `jde_sales_order_inquiry` | **READ** | F4211 + F4201 via Data Service | readOnly |
| `jde_create_sales_order` | **CREATE** | Orchestration → P4210 | write |
| `jde_update_sales_order` | **UPDATE** | Orchestration → P4210 EditLine | destructive |
| `jde_add_sales_order_line` | **ADD LINE** | Orchestration → P4210 AddLine | write |
| `jde_cancel_sales_order` | **CANCEL** | Orchestration → P4210 Cancel | destructive |

### Supporting Lookups

| Tool | Purpose |
|------|---------|
| `jde_customer_lookup` | Find customer AN8 by name or number (F0101) |
| `jde_item_check` | Validate item exists and check on-hand qty (F41021) |

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

## How Claude Uses These Tools

**"Show me order 12345"** → `jde_sales_order_inquiry` (direct, fast)

**"Create a sales order for Acme Corp, 50 units of ABC123 at branch M30"** →
1. `jde_customer_lookup` (resolve "Acme Corp" → AN8 4242)
2. `jde_item_check` (verify ABC123 exists at M30, check stock)
3. `jde_create_sales_order` (call orchestration with all params)

**"Change the quantity on line 1 of order 12345 to 75"** →
1. `jde_sales_order_inquiry` (verify current state)
2. `jde_update_sales_order` (orderNumber=12345, lineNumber=1000, quantity=75)

**"Cancel order 12345"** →
1. `jde_sales_order_inquiry` (show user what will be cancelled)
2. `jde_cancel_sales_order` (after user confirms)

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

### 3. Configure Orchestrations

Edit `src/data/orchestrations.json` with your actual orchestration names:

```json
{
  "createSalesOrder": {
    "orchestrationName": "YOUR_CreateSO_Orch_Name",
    "inputMapping": { ... }
  },
  "updateSalesOrderLine": {
    "orchestrationName": "YOUR_UpdateSOLine_Orch_Name",
    ...
  },
  "addSalesOrderLines": {
    "orchestrationName": "YOUR_AddSOLines_Orch_Name",
    ...
  },
  "cancelSalesOrder": {
    "orchestrationName": "YOUR_CancelSO_Orch_Name",
    ...
  }
}
```

The `inputMapping` translates MCP tool parameter names to your orchestration's expected input field names. Update these to match your Orchestrator Studio definitions.

### 4. Run

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

## What You Need to Build in JDE

Before the write tools work, you need **4 orchestrations** in Orchestrator Studio:

1. **CreateSalesOrder** — Drives P4210 to create header + lines
2. **UpdateSOLine** — Drives P4210 EditLine to modify a detail line
3. **AddSOLines** — Drives P4210 AddLine to add lines to an existing order
4. **CancelSO** — Drives P4210 Cancel to close an order or line

Each orchestration should:
- Accept the inputs defined in `orchestrations.json`
- Use Form Requests against P4210 (Sales Order Entry)
- Return at minimum a success flag and message
- Handle errors gracefully (invalid customer, out of stock, etc.)

The READ tools work immediately — they use the AIS Data Service directly and need no orchestrations.

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
│   │   ├── dictionary.json         # Curated table/column definitions
│   │   └── orchestrations.json     # CRUD → orchestration name mapping
│   ├── schemas/
│   │   └── tools.ts                # Zod input schemas for all tools
│   ├── services/
│   │   ├── ais-client.ts           # AIS REST client (auth, data, form, orch)
│   │   ├── dictionary.ts           # Dictionary search/lookup service
│   │   └── orch-mapper.ts          # Maps tool inputs → orchestration payloads
│   └── tools/
│       ├── dictionary.ts           # Dictionary discovery tools
│       ├── query.ts                # Generic table query tool
│       ├── domain.ts               # SO CRUD + supporting lookup tools
│       └── orchestration.ts        # Generic orchestration call tool
```
