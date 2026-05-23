"""Layer 2 — AP/GL Integrity tools (programmatic R047001A)."""
import json
import logging
from typing import Optional
from mcp.server.fastmcp import FastMCP

from config import CHARACTER_LIMIT
from services.ais_client import query_table, add_filter

logger = logging.getLogger(__name__)


def _truncate(text: str, records: int | None = None) -> str:
    if len(text) <= CHARACTER_LIMIT:
        return text
    suffix = f"\n\n... [TRUNCATED — {records if records is not None else 'many'} total records. Narrow your filters.]"
    return text[:CHARACTER_LIMIT] + suffix


def register(mcp: FastMCP) -> None:

    @mcp.tool(
        name="jde_ap_voucher_query",
        description=(
            "Query the JDE Accounts Payable Ledger (F0411) for voucher pay items. "
            "Essential for R047001A integrity analysis. The GLPT (GL Offset) field is the primary grouping key. "
            "Key columns: DOC, DCT, KCO, SFX, CO, AN8, MCU, AG (gross), AAP (open), GLPT, AID, FY, PN, DGJ, PST, VINV. "
            "Args: company, supplier_number, document_type, pay_status (A/P/V), gl_offset, "
            "date_from (YYYY-MM-DD), date_to, fiscal_year, period, max_rows (default 100)."
        ),
        annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    )
    async def jde_ap_voucher_query(
        company: Optional[str] = None,
        supplier_number: Optional[str] = None,
        document_type: Optional[str] = None,
        pay_status: Optional[str] = None,
        gl_offset: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        fiscal_year: Optional[str] = None,
        period: Optional[str] = None,
        max_rows: int = 100,
    ) -> str:
        try:
            filters: list[dict] = []
            add_filter(filters, "CO", "EQUAL", company)
            add_filter(filters, "AN8", "EQUAL", supplier_number)
            add_filter(filters, "DCT", "EQUAL", document_type)
            add_filter(filters, "PST", "EQUAL", pay_status)
            add_filter(filters, "GLPT", "EQUAL", gl_offset)
            add_filter(filters, "FY", "EQUAL", fiscal_year)
            add_filter(filters, "PN", "EQUAL", period)
            if date_from:
                add_filter(filters, "DGJ", "GREATER_EQUAL", date_from)
            if date_to:
                add_filter(filters, "DGJ", "LESS_EQUAL", date_to)

            resp = await query_table(
                table_name="F0411",
                columns=["DOC", "DCT", "KCO", "SFX", "CO", "AN8", "MCU", "AG", "AAP", "PAAP", "GLPT", "AID", "FY", "PN", "DGJ", "PST", "VINV"],
                filters=filters or None,
                max_rows=max_rows,
            )
            grid = (resp.get("fs_DATABROWSE") or {}).get("data", {}).get("gridData")
            if not grid:
                return "No vouchers found matching the criteria."

            output = {
                "tableName": "F0411",
                "description": "A/P Voucher Pay Items",
                "totalRecords": grid.get("summary", {}).get("records"),
                "returnedRecords": len(grid.get("rowset", [])),
                "hasMore": grid.get("summary", {}).get("moreRecords"),
                "rows": grid.get("rowset", []),
            }
            return _truncate(json.dumps(output, indent=2), grid.get("summary", {}).get("records"))
        except Exception as exc:
            raise RuntimeError(f"Error querying F0411: {exc}") from exc

    @mcp.tool(
        name="jde_gl_balance_query",
        description=(
            "Query the JDE Account Balances table (F0902) for period-level GL balances. "
            "Returns balances by period for each account/ledger type/fiscal year combination. "
            "Key columns: AID, CO, MCU, OBJ, SUB, LT, FY, CTRY, AN01-AN14 (period amounts), BORG. "
            "Args: company, business_unit (MCU), object_account (OBJ) e.g. '1110', subsidiary, "
            "ledger_type (default 'AA'), fiscal_year, max_rows (default 100)."
        ),
        annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    )
    async def jde_gl_balance_query(
        company: Optional[str] = None,
        business_unit: Optional[str] = None,
        object_account: Optional[str] = None,
        subsidiary: Optional[str] = None,
        ledger_type: Optional[str] = None,
        fiscal_year: Optional[str] = None,
        max_rows: int = 100,
    ) -> str:
        try:
            filters: list[dict] = []
            add_filter(filters, "CO", "EQUAL", company)
            add_filter(filters, "MCU", "EQUAL", business_unit)
            add_filter(filters, "OBJ", "EQUAL", object_account)
            add_filter(filters, "SUB", "EQUAL", subsidiary)
            add_filter(filters, "LT", "EQUAL", ledger_type)
            add_filter(filters, "FY", "EQUAL", fiscal_year)

            period_cols = [f"AN{p:02d}" for p in range(1, 15)]
            resp = await query_table(
                table_name="F0902",
                columns=["AID", "CO", "MCU", "OBJ", "SUB", "LT", "FY", "CTRY"] + period_cols + ["BORG"],
                filters=filters or None,
                max_rows=max_rows,
            )
            grid = (resp.get("fs_DATABROWSE") or {}).get("data", {}).get("gridData")
            if not grid:
                return "No account balances found matching the criteria."

            output = {
                "tableName": "F0902",
                "description": "Account Balances by Period",
                "totalRecords": grid.get("summary", {}).get("records"),
                "returnedRecords": len(grid.get("rowset", [])),
                "hasMore": grid.get("summary", {}).get("moreRecords"),
                "rows": grid.get("rowset", []),
            }
            return _truncate(json.dumps(output, indent=2), grid.get("summary", {}).get("records"))
        except Exception as exc:
            raise RuntimeError(f"Error querying F0902: {exc}") from exc

    @mcp.tool(
        name="jde_gl_detail_query",
        description=(
            "Query the JDE Account Ledger (F0901) for individual GL journal entries. "
            "Use for drill-down when an integrity discrepancy is found. "
            "Key columns: AID, DOC, DCT, KCO, CO, MCU, LT, FY, PN, AA (amount), DGJ, EXR, AN8, JELN. "
            "Args: account_id (AID), company, document_type, fiscal_year, period, "
            "date_from (YYYY-MM-DD), date_to, max_rows (default 100)."
        ),
        annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    )
    async def jde_gl_detail_query(
        account_id: Optional[str] = None,
        company: Optional[str] = None,
        document_type: Optional[str] = None,
        fiscal_year: Optional[str] = None,
        period: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        max_rows: int = 100,
    ) -> str:
        try:
            filters: list[dict] = []
            add_filter(filters, "AID", "EQUAL", account_id)
            add_filter(filters, "CO", "EQUAL", company)
            add_filter(filters, "DCT", "EQUAL", document_type)
            add_filter(filters, "FY", "EQUAL", fiscal_year)
            add_filter(filters, "PN", "EQUAL", period)
            if date_from:
                add_filter(filters, "DGJ", "GREATER_EQUAL", date_from)
            if date_to:
                add_filter(filters, "DGJ", "LESS_EQUAL", date_to)

            resp = await query_table(
                table_name="F0901",
                columns=["AID", "DOC", "DCT", "KCO", "CO", "MCU", "LT", "FY", "PN", "AA", "DGJ", "EXR", "AN8", "JELN"],
                filters=filters or None,
                max_rows=max_rows,
            )
            grid = (resp.get("fs_DATABROWSE") or {}).get("data", {}).get("gridData")
            if not grid:
                return "No journal entries found matching the criteria."

            output = {
                "tableName": "F0901",
                "description": "GL Journal Entry Detail",
                "totalRecords": grid.get("summary", {}).get("records"),
                "returnedRecords": len(grid.get("rowset", [])),
                "hasMore": grid.get("summary", {}).get("moreRecords"),
                "rows": grid.get("rowset", []),
            }
            return _truncate(json.dumps(output, indent=2), grid.get("summary", {}).get("records"))
        except Exception as exc:
            raise RuntimeError(f"Error querying F0901: {exc}") from exc

    @mcp.tool(
        name="jde_ap_gl_integrity_check",
        description=(
            "Perform a programmatic A/P to G/L integrity check — same logic as JDE report R047001A. "
            "1. Queries F0411 and sums voucher amounts grouped by GL offset code (GLPT). "
            "2. Queries F0902 for corresponding GL accounts. "
            "3. Compares AP subledger totals against GL balance — identifies matches and discrepancies. "
            "Args: company (required), fiscal_year (required), period_from (required), period_to (required), "
            "gl_offset (optional, omit for ALL offset accounts). "
            "Returns: { summary, matches, discrepancies } each with glOffset, AP total, GL balance, and difference."
        ),
        annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    )
    async def jde_ap_gl_integrity_check(
        company: str,
        fiscal_year: str,
        period_from: int,
        period_to: int,
        gl_offset: Optional[str] = None,
    ) -> str:
        try:
            # Step 1: query F0411
            ap_filters: list[dict] = []
            add_filter(ap_filters, "CO", "EQUAL", company)
            add_filter(ap_filters, "FY", "EQUAL", fiscal_year)
            add_filter(ap_filters, "PN", "GREATER_EQUAL", str(period_from))
            add_filter(ap_filters, "PN", "LESS_EQUAL", str(period_to))
            if gl_offset:
                add_filter(ap_filters, "GLPT", "EQUAL", gl_offset)

            ap_resp = await query_table(
                table_name="F0411",
                columns=["GLPT", "AG", "AAP", "CO", "FY", "PN", "AID"],
                filters=ap_filters,
                max_rows=500,
            )
            ap_rows = (ap_resp.get("fs_DATABROWSE") or {}).get("data", {}).get("gridData", {}).get("rowset", [])

            # Group AP by GLPT
            ap_by_glpt: dict[str, dict] = {}
            for row in ap_rows:
                glpt = str(row.get("F0411_GLPT") or row.get("GLPT") or "UNKNOWN")
                gross = float(row.get("F0411_AG") or row.get("AG") or 0)
                open_amt = float(row.get("F0411_AAP") or row.get("AAP") or 0)
                aid = str(row.get("F0411_AID") or row.get("AID") or "")
                if glpt not in ap_by_glpt:
                    ap_by_glpt[glpt] = {"gross": 0.0, "open": 0.0, "count": 0, "aids": set()}
                ap_by_glpt[glpt]["gross"] += gross
                ap_by_glpt[glpt]["open"] += open_amt
                ap_by_glpt[glpt]["count"] += 1
                if aid:
                    ap_by_glpt[glpt]["aids"].add(aid)

            # Step 2: query F0902
            gl_filters: list[dict] = []
            add_filter(gl_filters, "CO", "EQUAL", company)
            add_filter(gl_filters, "LT", "EQUAL", "AA")
            add_filter(gl_filters, "FY", "EQUAL", fiscal_year)

            period_cols = [f"AN{p:02d}" for p in range(1, 15)]
            gl_resp = await query_table(
                table_name="F0902",
                columns=["AID", "CO", "OBJ", "SUB", "FY"] + period_cols + ["BORG"],
                filters=gl_filters,
                max_rows=500,
            )
            gl_rows = (gl_resp.get("fs_DATABROWSE") or {}).get("data", {}).get("gridData", {}).get("rowset", [])

            # AID → sum of requested period amounts
            gl_by_aid: dict[str, float] = {}
            for row in gl_rows:
                aid = str(row.get("F0902_AID") or row.get("AID") or "")
                period_sum = 0.0
                for p in range(period_from, period_to + 1):
                    key = f"AN{p:02d}"
                    period_sum += float(row.get(f"F0902_{key}") or row.get(key) or 0)
                gl_by_aid[aid] = gl_by_aid.get(aid, 0.0) + period_sum

            # Step 3: compare
            matches: list[dict] = []
            discrepancies: list[dict] = []

            for glpt, ap in ap_by_glpt.items():
                gl_total = 0.0
                matched_aids: list[str] = []
                for aid in ap["aids"]:
                    if aid in gl_by_aid:
                        gl_total += gl_by_aid[aid]
                        matched_aids.append(aid)

                difference = round(ap["gross"] - gl_total, 2)
                entry = {
                    "glOffset": glpt,
                    "apGrossTotal": round(ap["gross"], 2),
                    "apOpenTotal": round(ap["open"], 2),
                    "glPeriodTotal": round(gl_total, 2),
                    "difference": difference,
                    "voucherCount": ap["count"],
                    "matchedAccountIds": matched_aids,
                }
                (matches if abs(difference) < 0.01 else discrepancies).append(entry)

            output = {
                "reportName": "A/P to G/L Integrity Check (R047001A)",
                "company": company,
                "fiscalYear": fiscal_year,
                "periodRange": f"{period_from}-{period_to}",
                "glOffsetFilter": gl_offset or "ALL",
                "apVouchersAnalyzed": len(ap_rows),
                "glAccountsAnalyzed": len(gl_rows),
                "summary": {
                    "totalOffsetGroups": len(ap_by_glpt),
                    "balanced": len(matches),
                    "discrepancies": len(discrepancies),
                },
                "discrepancies": discrepancies,
                "matches": matches,
            }
            return _truncate(json.dumps(output, indent=2))
        except Exception as exc:
            raise RuntimeError(
                f"Error running integrity check: {exc}. Verify company '{company}' and fiscal year {fiscal_year} exist in F0411."
            ) from exc
