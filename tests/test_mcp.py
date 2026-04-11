"""MCP Server Integration Tests — Tests against the deployed Azure Container App.

Tests all 4 integrity tools + tools/list.
Usage: python tests/test_mcp.py
"""
import json
import sys
import requests

MCP_URL = "https://jde-mcp-integrity.bluedesert-fb732cac.eastus.azurecontainerapps.io"
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}

# Track results
results = []


def mcp_call(method: str, params: dict | None = None, call_id: int = 1) -> dict:
    """Send a JSON-RPC request to the MCP server."""
    body = {"jsonrpc": "2.0", "id": call_id, "method": method}
    if params:
        body["params"] = params
    resp = requests.post(f"{MCP_URL}/mcp", json=body, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    return resp.json()


def record(test_name: str, passed: bool, detail: str = ""):
    status = "PASS" if passed else "FAIL"
    results.append({"test": test_name, "status": status, "detail": detail})
    icon = "✅" if passed else "❌"
    print(f"  {icon} {test_name}: {detail[:120] if detail else status}")


def test_health():
    print("\n── Test: Health Endpoint ──")
    resp = requests.get(f"{MCP_URL}/health", timeout=30)
    data = resp.json()
    passed = resp.status_code == 200 and data.get("status") == "ok"
    record("health_endpoint", passed, f"status={data.get('status')}, version={data.get('version')}")


def test_initialize():
    print("\n── Test: MCP Initialize ──")
    data = mcp_call("initialize", {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "test-client", "version": "1.0"},
    })
    result = data.get("result", {})
    passed = result.get("protocolVersion") == "2025-03-26"
    record("mcp_initialize", passed, f"serverInfo={result.get('serverInfo')}")


def test_tools_list():
    print("\n── Test: Tools List ──")
    # Initialize first (stateless mode — each request is independent)
    mcp_call("initialize", {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "test-client", "version": "1.0"},
    })
    data = mcp_call("tools/list", call_id=2)
    tools = data.get("result", {}).get("tools", [])
    tool_names = [t["name"] for t in tools]

    # Check integrity tools exist
    integrity_tools = [
        "jde_ap_voucher_query",
        "jde_gl_balance_query",
        "jde_gl_detail_query",
        "jde_ap_gl_integrity_check",
    ]
    for tool_name in integrity_tools:
        found = tool_name in tool_names
        record(f"tool_registered_{tool_name}", found, f"found={found}")

    record("tools_list_count", len(tools) > 0, f"total_tools={len(tools)}, names={tool_names}")


def test_ap_voucher_query():
    print("\n── Test: AP Voucher Query (jde_ap_voucher_query) ──")
    # Initialize
    mcp_call("initialize", {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "test-client", "version": "1.0"},
    })
    # Call tool
    data = mcp_call("tools/call", {
        "name": "jde_ap_voucher_query",
        "arguments": {
            "company": "00060",
            "fiscalYear": 25,
            "period": 1,
            "maxRows": 5,
        },
    }, call_id=2)

    result = data.get("result", {})
    error = data.get("error")
    if error:
        record("ap_voucher_query", False, f"error={error}")
    else:
        content = result.get("content", [])
        has_content = len(content) > 0
        text = content[0].get("text", "") if content else ""
        record("ap_voucher_query", has_content, f"content_items={len(content)}, preview={text[:150]}")


def test_gl_balance_query():
    print("\n── Test: GL Balance Query (jde_gl_balance_query) ──")
    mcp_call("initialize", {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "test-client", "version": "1.0"},
    })
    data = mcp_call("tools/call", {
        "name": "jde_gl_balance_query",
        "arguments": {
            "company": "00060",
            "fiscalYear": 25,
            "maxRows": 5,
        },
    }, call_id=2)

    result = data.get("result", {})
    error = data.get("error")
    if error:
        record("gl_balance_query", False, f"error={error}")
    else:
        content = result.get("content", [])
        has_content = len(content) > 0
        text = content[0].get("text", "") if content else ""
        record("gl_balance_query", has_content, f"content_items={len(content)}, preview={text[:150]}")


def test_gl_detail_query():
    print("\n── Test: GL Detail Query (jde_gl_detail_query) ──")
    mcp_call("initialize", {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "test-client", "version": "1.0"},
    })
    data = mcp_call("tools/call", {
        "name": "jde_gl_detail_query",
        "arguments": {
            "company": "00060",
            "fiscalYear": 25,
            "period": 1,
            "maxRows": 5,
        },
    }, call_id=2)

    result = data.get("result", {})
    error = data.get("error")
    if error:
        record("gl_detail_query", False, f"error={error}")
    else:
        content = result.get("content", [])
        has_content = len(content) > 0
        text = content[0].get("text", "") if content else ""
        record("gl_detail_query", has_content, f"content_items={len(content)}, preview={text[:150]}")


def test_ap_gl_integrity_check():
    print("\n── Test: AP/GL Integrity Check (jde_ap_gl_integrity_check) ──")
    mcp_call("initialize", {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "test-client", "version": "1.0"},
    })
    data = mcp_call("tools/call", {
        "name": "jde_ap_gl_integrity_check",
        "arguments": {
            "company": "00060",
            "fiscalYear": 25,
            "periodFrom": 1,
            "periodTo": 3,
        },
    }, call_id=2)

    result = data.get("result", {})
    error = data.get("error")
    if error:
        record("ap_gl_integrity_check", False, f"error={error}")
    else:
        content = result.get("content", [])
        has_content = len(content) > 0
        text = content[0].get("text", "") if content else ""
        # Try to parse the JSON response
        try:
            parsed = json.loads(text)
            has_summary = "summary" in parsed or "matches" in parsed or "discrepancies" in parsed
            record("ap_gl_integrity_check", has_content,
                   f"keys={list(parsed.keys()) if isinstance(parsed, dict) else 'list'}")
            record("ap_gl_integrity_check_structure", has_summary,
                   f"has_summary={has_summary}")
        except json.JSONDecodeError:
            record("ap_gl_integrity_check", has_content, f"raw_response (not JSON): {text[:200]}")


def main():
    print("=" * 60)
    print("MCP Server Integration Tests")
    print(f"Target: {MCP_URL}")
    print("=" * 60)

    test_health()
    test_initialize()
    test_tools_list()
    test_ap_voucher_query()
    test_gl_balance_query()
    test_gl_detail_query()
    test_ap_gl_integrity_check()

    # Summary
    print("\n" + "=" * 60)
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    print(f"Results: {passed} passed, {failed} failed, {len(results)} total")
    print("=" * 60)

    # Return results for the test report
    return results


if __name__ == "__main__":
    test_results = main()
    sys.exit(0 if all(r["status"] == "PASS" for r in test_results) else 1)
