"""Local integration tests — Tests MCP server + Python MCP bridge + API without Docker.

Usage:
    1. Start MCP server: cd jde-mcp-server-template && TRANSPORT=http PORT=3000 npx tsx src/index.ts
    2. Run tests:        python tests/test_local.py

Tests:
    1. MCP Server health endpoint
    2. MCP Initialize handshake
    3. MCP tools/list
    4. MCP tool call (jde_ap_gl_integrity_check)
    5. Python MCP bridge (jde_ap_gl_integrity_check via mcp_bridge.py)
    6. FastAPI health endpoint
"""
import json
import os
import sys
import time

# ── Path setup ────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "agents"))

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"), override=False)

os.environ.setdefault("MCP_SERVER_URL", "http://localhost:3000/mcp")

import httpx

MCP_BASE = "http://localhost:3000"
MCP_URL = f"{MCP_BASE}/mcp"
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}

INIT_PARAMS = {
    "protocolVersion": "2025-03-26",
    "capabilities": {},
    "clientInfo": {"name": "test-local", "version": "1.0"},
}

results = []


def record(test_name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    results.append({"test": test_name, "status": status, "detail": detail})
    icon = "✅" if passed else "❌"
    print(f"  {icon} {test_name}: {detail[:200] if detail else status}")


def mcp_call(client, method, params=None, call_id=1):
    body = {"jsonrpc": "2.0", "id": call_id, "method": method}
    if params:
        body["params"] = params
    resp = client.post(MCP_URL, json=body, headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


# ──────────────────────────────────────────────────────────────
# Test 1: MCP Server Health
# ──────────────────────────────────────────────────────────────
def test_health():
    print("\n── Test 1: MCP Health Endpoint ──")
    try:
        resp = httpx.get(f"{MCP_BASE}/health", timeout=10)
        data = resp.json()
        passed = resp.status_code == 200 and data.get("status") == "ok"
        record("mcp_health", passed, f"status={data.get('status')}, version={data.get('version')}")
    except Exception as e:
        record("mcp_health", False, str(e))


# ──────────────────────────────────────────────────────────────
# Test 2: MCP Initialize
# ──────────────────────────────────────────────────────────────
def test_initialize():
    print("\n── Test 2: MCP Initialize ──")
    try:
        with httpx.Client(timeout=30) as client:
            data = mcp_call(client, "initialize", INIT_PARAMS)
            server_info = data.get("result", {}).get("serverInfo", {})
            passed = server_info.get("name") == "jde-mcp-server"
            record("mcp_initialize", passed, f"server={server_info.get('name')}, version={server_info.get('version')}")
    except Exception as e:
        record("mcp_initialize", False, str(e))


# ──────────────────────────────────────────────────────────────
# Test 3: MCP tools/list
# ──────────────────────────────────────────────────────────────
def test_tools_list():
    print("\n── Test 3: MCP tools/list ──")
    try:
        with httpx.Client(timeout=30) as client:
            mcp_call(client, "initialize", INIT_PARAMS, call_id=1)
            data = mcp_call(client, "tools/list", {}, call_id=2)
            tools = data.get("result", {}).get("tools", [])
            tool_names = [t["name"] for t in tools]
            print(f"    Found {len(tools)} tools:")
            for name in tool_names:
                print(f"      - {name}")

            # Verify expected integrity tools exist
            expected = [
                "jde_ap_voucher_query",
                "jde_gl_balance_query",
                "jde_gl_detail_query",
                "jde_ap_gl_integrity_check",
                "jde_batch_query",
                "jde_batch_transaction_query",
                "jde_unposted_batch_check",
            ]
            missing = [t for t in expected if t not in tool_names]
            passed = len(missing) == 0
            detail = f"{len(tools)} tools found" if passed else f"Missing: {missing}"
            record("mcp_tools_list", passed, detail)
    except Exception as e:
        record("mcp_tools_list", False, str(e))


# ──────────────────────────────────────────────────────────────
# Test 4: MCP tool call (jde_ap_gl_integrity_check)
# ──────────────────────────────────────────────────────────────
def test_mcp_tool_call():
    print("\n── Test 4: MCP Tool Call (jde_ap_gl_integrity_check) ──")
    try:
        with httpx.Client(timeout=120) as client:
            mcp_call(client, "initialize", INIT_PARAMS, call_id=1)
            data = mcp_call(
                client,
                "tools/call",
                {
                    "name": "jde_ap_gl_integrity_check",
                    "arguments": {"company": "00060", "fiscalYear": 25, "periodFrom": 1, "periodTo": 1},
                },
                call_id=2,
            )
            if "error" in data:
                record("mcp_tool_call", False, f"MCP error: {json.dumps(data['error'])[:200]}")
            else:
                content = data.get("result", {}).get("content", [])
                texts = [c.get("text", "") for c in content if c.get("type") == "text"]
                result_text = "\n".join(texts)
                passed = len(result_text) > 0
                # Show first 200 chars of result
                record("mcp_tool_call", passed, f"Got {len(result_text)} chars: {result_text[:200]}")
    except Exception as e:
        record("mcp_tool_call", False, str(e))


# ──────────────────────────────────────────────────────────────
# Test 5: Python MCP Bridge
# ──────────────────────────────────────────────────────────────
def test_mcp_bridge():
    print("\n── Test 5: Python MCP Bridge (jde_ap_gl_integrity_check) ──")
    try:
        from mcp_bridge import jde_ap_gl_integrity_check

        result = jde_ap_gl_integrity_check(company="00060", fiscalYear=25, periodFrom=1, periodTo=1)
        passed = isinstance(result, str) and len(result) > 0
        record("mcp_bridge", passed, f"Got {len(result)} chars: {result[:200]}")
    except Exception as e:
        record("mcp_bridge", False, str(e))


# ──────────────────────────────────────────────────────────────
# Test 6: Python MCP Bridge (batch tools)
# ──────────────────────────────────────────────────────────────
def test_mcp_bridge_batch():
    print("\n── Test 6: Python MCP Bridge (jde_unposted_batch_check) ──")
    try:
        from mcp_bridge import jde_unposted_batch_check

        result = jde_unposted_batch_check()
        passed = isinstance(result, str) and len(result) > 0
        record("mcp_bridge_batch", passed, f"Got {len(result)} chars: {result[:200]}")
    except Exception as e:
        record("mcp_bridge_batch", False, str(e))


# ──────────────────────────────────────────────────────────────
# Test 7: FastAPI App Import + Health
# ──────────────────────────────────────────────────────────────
def test_fastapi_import():
    print("\n── Test 7: FastAPI App Import ──")
    try:
        # Test that the FastAPI app can be imported (validates all wiring)
        from api import app, _parse_has_data, _parse_report_info

        # Test helper functions
        assert _parse_has_data('{"has_data": true}') == True
        assert _parse_has_data('{"has_data": false}') == False
        assert _parse_report_info("R047001A_SCH0001_32188_PDF.pdf") == ("R047001A", "SCH0001")
        assert _parse_report_info("R007011_ZJDE0001_100_PDF.pdf") == ("R007011", "ZJDE0001")

        record("fastapi_import", True, "App imported, helpers validated")
    except Exception as e:
        record("fastapi_import", False, str(e))


# ──────────────────────────────────────────────────────────────
# Test 8: FastAPI Health via TestClient
# ──────────────────────────────────────────────────────────────
def test_fastapi_health():
    print("\n── Test 8: FastAPI Health (TestClient) ──")
    try:
        from fastapi.testclient import TestClient
        from api import app

        client = TestClient(app)
        resp = client.get("/health")
        data = resp.json()
        passed = resp.status_code == 200 and data.get("status") == "ok"
        record("fastapi_health", passed, f"status={data.get('status')}, version={data.get('version')}")
    except ImportError:
        record("fastapi_health", False, "Need: pip install httpx (for TestClient)")
    except Exception as e:
        record("fastapi_health", False, str(e))


# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("JDE Integrity Analyzer — Local Integration Tests")
    print(f"  MCP Server: {MCP_BASE}")
    print(f"  MCP URL:    {MCP_URL}")
    print("=" * 60)

    t0 = time.time()

    test_health()
    test_initialize()
    test_tools_list()
    test_mcp_tool_call()
    test_mcp_bridge()
    test_mcp_bridge_batch()
    test_fastapi_import()
    test_fastapi_health()

    elapsed = time.time() - t0

    # ── Summary ────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"RESULTS ({elapsed:.1f}s)")
    print("=" * 60)
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    for r in results:
        icon = "✅" if r["status"] == "PASS" else "❌"
        print(f"  {icon} {r['test']}")

    print(f"\n  {passed} passed, {failed} failed out of {len(results)} tests")

    if failed > 0:
        print("\n  ⚠️  Some tests failed. Fix issues before building Docker images.")
        sys.exit(1)
    else:
        print("\n  ✅ All tests passed! Safe to build Docker images:")
        print("     docker compose up --build")
        sys.exit(0)
