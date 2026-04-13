"""MCP Bridge — ADK @tool functions that call JDE MCP tools via HTTP.

Bridges the OCI ADK function tool interface with the JDE MCP Server's
StreamableHTTP transport (JSON-RPC 2.0). Each @tool function maps to one
MCP tool so the LLM sees full parameter schemas.

The MCP server must be reachable at MCP_SERVER_URL (default: http://localhost:3000/mcp).
"""
import json
import logging
import os
from typing import Optional

import httpx
from oci.addons.adk import tool

logger = logging.getLogger(__name__)


def _validate_company(company: Optional[str]) -> Optional[str]:
    """Validate company code format. JDE company codes are 5-digit strings like '00001'.
    If the value looks like a name (contains letters other than digits), return None
    so the tool queries all companies instead of returning 0 results."""
    if company is None:
        return None
    stripped = company.strip()
    if not stripped:
        return None
    # Valid JDE company codes are numeric strings (e.g. "00001", "00060")
    if stripped.isdigit():
        return stripped.zfill(5)  # Pad to 5 digits if needed
    logger.warning(f"Invalid company code '{company}' (not numeric) — omitting from query")
    return None

_MCP_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}

_INIT_PARAMS = {
    "protocolVersion": "2025-03-26",
    "capabilities": {},
    "clientInfo": {"name": "adk-mcp-bridge", "version": "1.0.0"},
}


def _call_mcp_tool(tool_name: str, arguments: dict) -> str:
    """Send a JSON-RPC tools/call request to the MCP server.

    Performs the MCP initialize handshake, then issues the tool call.
    Returns the concatenated text content from the MCP response.
    """
    url = os.getenv("MCP_SERVER_URL", "http://localhost:3000/mcp")

    with httpx.Client(timeout=120) as client:
        # MCP initialize (required by protocol — each POST is independent)
        client.post(
            url,
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": _INIT_PARAMS},
            headers=_MCP_HEADERS,
        )

        # Call the tool
        resp = client.post(
            url,
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments},
            },
            headers=_MCP_HEADERS,
        )
        resp.raise_for_status()
        data = resp.json()

    if "error" in data:
        error_msg = json.dumps(data["error"])
        logger.error(f"MCP error calling {tool_name}: {error_msg}")
        return f"MCP tool error: {error_msg}"

    content = data.get("result", {}).get("content", [])
    texts = [c.get("text", "") for c in content if c.get("type") == "text"]
    return "\n".join(texts) if texts else json.dumps(data.get("result", {}))


# ──────────────────────────────────────────────────────────────
# ADK @tool wrappers — one per MCP integrity tool
# ──────────────────────────────────────────────────────────────


@tool
def jde_ap_voucher_query(
    company: Optional[str] = None,
    supplierNumber: Optional[int] = None,
    documentType: Optional[str] = None,
    payStatus: Optional[str] = None,
    glOffset: Optional[str] = None,
    dateFrom: Optional[str] = None,
    dateTo: Optional[str] = None,
    fiscalYear: Optional[int] = None,
    period: Optional[int] = None,
    maxRows: int = 100,
) -> str:
    """Query F0411 (A/P Ledger) for AP voucher pay items.

    Args:
        company: Company code (CO), e.g. '00001'
        supplierNumber: Supplier address book number (AN8)
        documentType: Document type filter (DCT), e.g. 'PV' for voucher
        payStatus: Payment status filter (PST): A=Approved, P=Paid, V=Void, D=Draft, H=Held
        glOffset: GL posting code / offset account (GLPT). KEY field for R047001A grouping
        dateFrom: GL date range start (YYYY-MM-DD)
        dateTo: GL date range end (YYYY-MM-DD)
        fiscalYear: Fiscal year filter (FY), e.g. 26 for 2026
        period: GL period filter (PN), 1-14
        maxRows: Max rows to return (default 100)
    """
    args = {k: v for k, v in {
        "company": company, "supplierNumber": supplierNumber,
        "documentType": documentType, "payStatus": payStatus,
        "glOffset": glOffset, "dateFrom": dateFrom, "dateTo": dateTo,
        "fiscalYear": fiscalYear, "period": period, "maxRows": maxRows,
    }.items() if v is not None}
    return _call_mcp_tool("jde_ap_voucher_query", args)


@tool
def jde_gl_balance_query(
    company: Optional[str] = None,
    businessUnit: Optional[str] = None,
    objectAccount: Optional[str] = None,
    subsidiary: Optional[str] = None,
    ledgerType: str = "AA",
    fiscalYear: Optional[int] = None,
    maxRows: int = 100,
) -> str:
    """Query F0902 (Account Balances) for GL period balances.

    Args:
        company: Company code (CO)
        businessUnit: Business unit / cost center (MCU)
        objectAccount: Object account (OBJ), e.g. '1110' for AP Trade
        subsidiary: Subsidiary account (SUB) for detail-level lookup
        ledgerType: Ledger type: AA=Actual (default), AU=Units, CA=Budget
        fiscalYear: Fiscal year (FY), e.g. 26 for 2026
        maxRows: Max rows to return (default 100)
    """
    args = {k: v for k, v in {
        "company": company, "businessUnit": businessUnit,
        "objectAccount": objectAccount, "subsidiary": subsidiary,
        "ledgerType": ledgerType, "fiscalYear": fiscalYear, "maxRows": maxRows,
    }.items() if v is not None}
    return _call_mcp_tool("jde_gl_balance_query", args)


@tool
def jde_gl_detail_query(
    accountId: Optional[str] = None,
    company: Optional[str] = None,
    documentType: Optional[str] = None,
    fiscalYear: Optional[int] = None,
    period: Optional[int] = None,
    dateFrom: Optional[str] = None,
    dateTo: Optional[str] = None,
    maxRows: int = 100,
) -> str:
    """Query F0901 (Account Ledger) for individual GL journal entries.

    Args:
        accountId: Account ID (AID), e.g. '00001.1110.ACME'
        company: Company code (CO)
        documentType: Document type (DCT), e.g. 'PV', 'JE'
        fiscalYear: Fiscal year (FY)
        period: GL period (PN), 1-14
        dateFrom: GL date range start (YYYY-MM-DD)
        dateTo: GL date range end (YYYY-MM-DD)
        maxRows: Max rows to return (default 100)
    """
    args = {k: v for k, v in {
        "accountId": accountId, "company": company,
        "documentType": documentType, "fiscalYear": fiscalYear,
        "period": period, "dateFrom": dateFrom, "dateTo": dateTo,
        "maxRows": maxRows,
    }.items() if v is not None}
    return _call_mcp_tool("jde_gl_detail_query", args)


@tool
def jde_ap_gl_integrity_check(
    company: str,
    fiscalYear: int,
    periodFrom: int,
    periodTo: int,
    glOffset: Optional[str] = None,
) -> str:
    """Run a programmatic R047001A AP-to-GL integrity check.

    Queries F0411 (AP) and F0902 (GL) automatically, compares AP subledger
    totals against GL balances, and returns matches/discrepancies.
    This is the PRIMARY tool for integrity analysis.

    Args:
        company: Company code (CO). Required.
        fiscalYear: Fiscal year to check (FY), e.g. 26 for 2026. Required.
        periodFrom: Starting period (PN). Required.
        periodTo: Ending period (PN). Required.
        glOffset: Specific GL offset code (GLPT) to check. Omit to check ALL offset accounts.
    """
    args: dict = {
        "company": company,
        "fiscalYear": fiscalYear,
        "periodFrom": periodFrom,
        "periodTo": periodTo,
    }
    if glOffset is not None:
        args["glOffset"] = glOffset
    return _call_mcp_tool("jde_ap_gl_integrity_check", args)


# ──────────────────────────────────────────────────────────────
# ADK @tool wrappers — R007011 (Unposted Batches) tools
# ──────────────────────────────────────────────────────────────


@tool
def jde_batch_query(
    company: Optional[str] = None,
    batchNumber: Optional[int] = None,
    batchType: Optional[str] = None,
    dateFrom: Optional[str] = None,
    dateTo: Optional[str] = None,
    maxRows: int = 100,
) -> str:
    """Query F0911 (Account Ledger) for batch transaction data.

    Use this to look up transactions within batches by company, batch number,
    batch type, or date range. Essential for R007011 batch verification.

    Args:
        company: Company code (KCO), e.g. '00001'
        batchNumber: Specific batch number (ICU) to look up
        batchType: Batch type: G=GL, V=Voucher, W=Time Entry, K=Receipts, I=Invoice
        dateFrom: GL date range start (YYYY-MM-DD)
        dateTo: GL date range end (YYYY-MM-DD)
        maxRows: Max rows to return (default 100)
    """
    company = _validate_company(company)
    args = {k: v for k, v in {
        "company": company, "batchNumber": batchNumber,
        "batchType": batchType, "dateFrom": dateFrom,
        "dateTo": dateTo, "maxRows": maxRows,
    }.items() if v is not None}
    return _call_mcp_tool("jde_batch_query", args)


@tool
def jde_batch_transaction_query(
    batchNumber: int,
    batchType: Optional[str] = None,
    company: Optional[str] = None,
    maxRows: int = 100,
) -> str:
    """Query F0911 (Account Ledger) for transactions within a specific batch.

    Use this to drill into the individual journal entry lines of a batch.

    Args:
        batchNumber: Batch number (ICU) — required
        batchType: Batch type (ICUT), e.g. 'G' for GL
        company: Company code (KCO)
        maxRows: Max rows to return (default 100)
    """
    company = _validate_company(company)
    args: dict = {"batchNumber": batchNumber, "maxRows": maxRows}
    if batchType is not None:
        args["batchType"] = batchType
    if company is not None:
        args["company"] = company
    return _call_mcp_tool("jde_batch_transaction_query", args)


@tool
def jde_unposted_batch_check(
    company: Optional[str] = None,
    batchType: Optional[str] = None,
    dateFrom: Optional[str] = None,
    dateTo: Optional[str] = None,
    maxRows: int = 200,
) -> str:
    """Verify batch data from R007011 against live JDE F0911 transaction data.

    Queries F0911 (Account Ledger) for batch transactions, groups by batch number,
    returns per-batch summary with transaction count, total amounts, and date ranges.
    This is the PRIMARY tool for R007011 batch verification.

    Args:
        company: Company code (KCO). Optional filter.
        batchType: Batch type filter: G=GL, V=Voucher, W=Time Entry, K=Receipts, I=Invoice
        dateFrom: GL date range start (YYYY-MM-DD)
        dateTo: GL date range end (YYYY-MM-DD)
        maxRows: Max rows to return (default 200)
    """
    company = _validate_company(company)
    args = {k: v for k, v in {
        "company": company, "batchType": batchType,
        "dateFrom": dateFrom, "dateTo": dateTo, "maxRows": maxRows,
    }.items() if v is not None}
    return _call_mcp_tool("jde_unposted_batch_check", args)
