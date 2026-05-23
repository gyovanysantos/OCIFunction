# Lessons Learned

## Agent Framework SDK (agent-framework-core==1.0.0rc3)

### FunctionTool — Use @tool decorator, NOT FunctionTool(func)
- **Wrong**: `FunctionTool(my_function)` → `TypeError: takes 1 positional argument`
- **Right**: Decorate with `@tool` → function becomes a `FunctionTool` automatically
- `FunctionTool.__init__` requires keyword-only args: `name=`, `func=`, `description=`
- The `@tool` decorator infers name and description from the function

### MCPStreamableHTTPTool — NOT McpTool
- **Wrong**: `from agent_framework import McpTool` → `ImportError`
- **Right**: `from agent_framework import MCPStreamableHTTPTool`
- Constructor: `MCPStreamableHTTPTool(name="...", url="...", allowed_tools=[...], approval_mode="never_require")`
- Set `load_prompts=False` if MCP server doesn't support prompts capability
- Available MCP tool classes: `MCPStdioTool`, `MCPStreamableHTTPTool`, `MCPWebsocketTool`

### WorkflowBuilder — start_executor=, NOT .set_start_executor()
- **Right**: `WorkflowBuilder(start_executor=agent)`
- Use `.add_edge(source, target)` for sequential flow

### Client — AzureAIClient, NOT AzureOpenAIChatClient
- **Right**: `from agent_framework.azure import AzureAIClient`
- Use `async with client.as_agent(name=..., instructions=..., tools=[...]) as agent:`
- Different agents MUST use different client instances

## Docker / Container Apps

### az acr build crashes — use local docker push
- `az acr build` produces broken images that crash with exit code 1
- **Always** use: `docker build` → `docker tag` → `docker push`

### DefaultAzureCredential fails in Docker containers (Windows host)
- Windows Azure CLI stores tokens in DPAPI-encrypted `.bin` files
- Mounting `~/.azure` into Linux containers does NOT work — DPAPI is Windows-only
- **Workaround for local dev**: Run agents from host Python (not Docker) so `AzureCliCredential` works
- **For production**: Use Managed Identity in Azure Container Apps
- **Alternative for local Docker**: Create a service principal and set `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_TENANT_ID` env vars in docker-compose

### Foundry model deployments can be removed/replaced
- `gpt-4o` was replaced by `gpt-4.1` in the Foundry project without notice
- Always verify with: `az cognitiveservices account deployment list --name <resource> --resource-group <rg>`
- Update ALL config files when deployment name changes: `.env`, `.env.example`, `agents/.env`, `copilot-instructions.md`

### Agent.run() API for direct invocation
- `Agent.run(messages)` accepts `str` directly (or `Message` / `Content` / `Sequence`)
- Returns `AgentResponse` with `.text` property for the output
- Use `async with client.as_agent(...) as agent:` context manager before calling `run()`
- For local testing, this is simpler than the HTTP hosting adapter (`from_agent_framework`)

### MCP Protocol — Accept Header
- StreamableHTTPServerTransport requires: `Accept: application/json, text/event-stream`

### AzureKeyCredential does NOT work with Agent Framework SDK
- The Agent Framework SDK (`AzureAIClient`) requires `TokenCredential | AsyncTokenCredential`
- `AzureKeyCredential` (from `azure.core.credentials`) does NOT have a `.get_token()` method → `AttributeError`
- API keys from `az cognitiveservices account keys list` produce `Unauthorized — audience is incorrect (https://ai.azure.com)` when used as bearer tokens
- **Workaround**: Use a static Azure AD token wrapped in a custom `_StaticTokenCredential` class that implements `async get_token()` → returns `AccessToken(token, expiry)`
- **Proper fix**: Assign `Azure AI User` role to the managed identity → use `DefaultAzureCredential`

### RBAC assignment requires Owner/User Access Administrator
- `Contributor` role does NOT include `Microsoft.Authorization/roleAssignments/write`
- Cannot assign roles to managed identities with just Contributor access
- Need someone with `Owner` or `User Access Administrator` role on the resource group

### OCI auth in containers — use env vars, not config file
- `~/.oci/config` references Windows file paths → won't work in Linux containers
- Pass OCI credentials as env vars: `OCI_USER`, `OCI_FINGERPRINT`, `OCI_TENANCY`, `OCI_REGION`
- PEM key → base64-encode → store as Container App secret → decode at runtime with `base64.b64decode()`
- Implement `_get_oci_config()` that checks env vars first, falls back to `oci.config.from_file()` for local dev

### Static token auth — expires in ~1 hour
- `az account get-access-token --resource "https://ai.azure.com"` returns a token valid for ~60-75 minutes
- Must be refreshed manually via `az containerapp update --set-env-vars FOUNDRY_TOKEN=$token`
- Use correct audience: `https://ai.azure.com` (NOT `https://cognitiveservices.azure.com`)
- Without this, you get "Not Acceptable" error
- Protocol version: `2025-03-26` (or server negotiates)

## JDE AIS

### F0901 — FY column alias not found
- JDE AIS `/v2/dataservice` returns `SPEC_NOT_FOUND` for alias `FY` on F0901
- May need prefixed alias (e.g., `GLFY`) depending on the business view spec
- F0411 and F0902 queries work fine with short aliases

## Git / Security

### Always .gitignore .env files
- `.env` files with credentials must be in `.gitignore`
- The root `.gitignore` didn't have `.env` — we added it

## JDE Email Integration (CL001_SimpleEmailJob)

### JDE rejects `style=` attributes in HTML
- `CL001_SimpleEmailJob` has a strict HTML sanitizer that flags `style=` as unsafe
- Also rejects: `<!DOCTYPE>`, `<html>`, `<head>`, `<body>`, `<meta>`, `<title>`, `<style>` blocks
- Also rejects: HTML entities (`&#9888;`, `&#10003;`, `&mdash;`, `&bull;`), `role="presentation"`, CSS functions (`linear-gradient()`, `box-shadow`)
- **Solution**: Use ONLY old-school HTML 4 attributes:
  - `bgcolor`, `width`, `align`, `valign`, `cellpadding`, `cellspacing` on tables
  - `<font color="..." size="...">` for text color/size
  - `<b>`, `<i>`, `<br>`, `<hr>` for formatting
  - No `<span>`, `<code>`, `<pre>` tags

### LLM outputs plain text titles instead of markdown headers
- Without explicit instructions, the LLM sometimes writes `Executive Summary\n` instead of `## Executive Summary`
- Plain text titles don't generate `<h2>` tags → no bold in HTML output
- **Fix**: Add "Markdown Formatting (CRITICAL)" section to agent instructions requiring `## Section Title` syntax
- Include explicit WRONG/RIGHT examples in the instructions

### Email layout spacing issues
- `cellpadding` is only valid on `<table>` elements, NOT on `<td>` — email clients ignore it on `<td>`
- Fixed-width tables (e.g. `width="680"`) create grey margins in email clients
- Wrapper tables (`bgcolor="#f4f5f7"`) add unnecessary padding above content
- **Fix**: Use flat stacked tables at `width="100%"` with `cellpadding` on the `<table>`, not `<td>`
