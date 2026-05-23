"""Layer 2 — Batch tools (R007011 — F0911)."""
import json
import logging
from datetime import date
from typing import Optional
from mcp.server.fastmcp import FastMCP

from config import CHARACTER_LIMIT
from services.ais_client import query_table, add_filter

logger = logging.getLogger(__name__)


def _to_julian(date_str: str) -> str:
    """Convert YYYY-MM-DD to JDE Julian CYYDDD format."""
    d = date.fromisoformat(date_str)
    century = d.year // 100 - 19       # 2026 → 1, 19xx → 0
    yy = d.year % 100
    ddd = (d - date(d.year, 1, 1)).days + 1
    return f"{century}{yy:02d}{ddd:03d}"


def _truncate(text: str, records: int | None = None) -> str:
    if len(text) <= CHARACTER_LIMIT:
        return text
    suffix = f"\n\n... [TRUNCATED — {records if records is not None else 'many'} total records. Narrow your filters.]"
    return text[:CHARACTER_LIMIT] + suffix


def register(mcp: FastMCP) -> None:

    @mcp.tool(
        name="jde_batch_query",
        description=(
            "Query the JDE Account Ledger table (F0911) for batch transaction data. "
            "Use to look up transactions within batches by company, batch number, batch type, or date range. "
            "Essential for R007011 (Unposted Batches) verification. "
            "Batch types (ICUT): G=General Ledger, V=Voucher Entry, W=Time Entry, K=Receipts, I=Invoice Entry, M=Manual Payment. "
            "Key columns: ICU (batch), ICUT (type), DOC, DCT, KCO, AA (amount), DGJ (GL date), FY, PN, EXR, JELN. "
            "Args: company, batch_number, batch_type (ICUT), date_from (YYYY-MM-DD), date_to, max_rows (default 100)."
        ),
        annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    )
    async def jde_batch_query(
        company: Optional[str] = None,
        batch_number: Optional[str] = None,
        batch_type: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        max_rows: int = 100,
    ) -> str:
        try:
            filters: list[dict] = []
            add_filter(filters, "KCO", "EQUAL", company)
            add_filter(filters, "ICU", "EQUAL", batch_number)
            add_filter(filters, "ICUT", "EQUAL", batch_type)
            if date_from:
                add_filter(filters, "DGJ", "GREATER_EQUAL", _to_julian(date_from))
            if date_to:
                add_filter(filters, "DGJ", "LESS_EQUAL", _to_julian(date_to))

            resp = await query_table(
                table_name="F0911",
                columns=["ICU", "ICUT", "DOC", "DCT", "KCO", "AA", "DGJ", "FY", "PN", "EXR", "AN8", "JELN"],
                filters=filters or None,
                max_rows=max_rows,
            )
            rows = (resp.get("fs_DATABROWSE") or {}).get("data", {}).get("gridData", {}).get("rowset", [])
            summary = (resp.get("fs_DATABROWSE") or {}).get("data", {}).get("gridData", {}).get("summary", {})

            output = {
                "tableName": "F0911",
                "description": "Account Ledger (Batch Transactions)",
                "totalRecords": summary.get("records", len(rows)),
                "returnedRecords": len(rows),
                "hasMore": summary.get("moreRecords", False),
                "rows": rows,
            }
            return _truncate(json.dumps(output, indent=2), summary.get("records"))
        except Exception as exc:
            raise RuntimeError(f"Error querying F0911 batch data: {exc}") from exc

    @mcp.tool(
        name="jde_batch_transaction_query",
        description=(
            "Query the JDE Account Ledger table (F0911) for journal entry transactions within batches. "
            "Use to look up individual GL transactions by batch number, type, company, document number, fiscal year, or period. "
            "Key columns: ICU, ICUT, DOC, DCT, KCO, AID, AA, DGJ, FY, PN, EXR, AN8, JELN, LT. "
            "Args: batch_number, batch_type (ICUT), company, document_number, fiscal_year, period, max_rows (default 100)."
        ),
        annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    )
    async def jde_batch_transaction_query(
        batch_number: Optional[str] = None,
        batch_type: Optional[str] = None,
        company: Optional[str] = None,
        document_number: Optional[str] = None,
        fiscal_year: Optional[str] = None,
        period: Optional[str] = None,
        max_rows: int = 100,
    ) -> str:
        try:
            filters: list[dict] = []
            add_filter(filters, "ICU", "EQUAL", batch_number)
            add_filter(filters, "ICUT", "EQUAL", batch_type)
            add_filter(filters, "KCO", "EQUAL", company)
            add_filter(filters, "DOC", "EQUAL", document_number)
            add_filter(filters, "FY", "EQUAL", fiscal_year)
            add_filter(filters, "PN", "EQUAL", period)

            resp = await query_table(
                table_name="F0911",
                columns=["ICU", "ICUT", "DOC", "DCT", "KCO", "CO", "AID", "OBJ", "SUB", "AA", "DGJ", "FY", "PN", "EXR", "AN8", "JELN", "LT"],
                filters=filters or None,
                max_rows=max_rows,
            )
            rows = (resp.get("fs_DATABROWSE") or {}).get("data", {}).get("gridData", {}).get("rowset", [])
            summary = (resp.get("fs_DATABROWSE") or {}).get("data", {}).get("gridData", {}).get("summary", {})

            output = {
                "tableName": "F0911",
                "description": "Account Ledger (Batch Transactions)",
                "totalRecords": summary.get("records", len(rows)),
                "returnedRecords": len(rows),
                "hasMore": summary.get("moreRecords", False),
                "rows": rows,
            }
            return _truncate(json.dumps(output, indent=2), summary.get("records"))
        except Exception as exc:
            raise RuntimeError(f"Error querying F0911: {exc}") from exc

    @mcp.tool(
        name="jde_unposted_batch_check",
        description=(
            "Verify batch data from an R007011 (Unposted Batches) report against live JDE data. "
            "Queries F0911 for batch transactions, groups by batch number, and returns per-batch summary: "
            "transaction count, total amount, document types, and GL date range. "
            "Use to verify that batches listed in the R007011 PDF exist in the GL and compare amounts. "
            "Args: company, batch_type (ICUT), date_from (YYYY-MM-DD), date_to, max_rows (default 200). "
            "Returns: { summary, batches[] } each with batchNumber, batchType, totalAmount, transactionCount, documentTypes, dateRange."
        ),
        annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    )
    async def jde_unposted_batch_check(
        company: Optional[str] = None,
        batch_type: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        max_rows: int = 200,
    ) -> str:
        try:
            filters: list[dict] = []
            add_filter(filters, "KCO", "EQUAL", company)
            if batch_type:
                add_filter(filters, "ICUT", "EQUAL", batch_type)
            if date_from:
                add_filter(filters, "DGJ", "GREATER_EQUAL", _to_julian(date_from))
            if date_to:
                add_filter(filters, "DGJ", "LESS_EQUAL", _to_julian(date_to))

            resp = await query_table(
                table_name="F0911",
                columns=["ICU", "ICUT", "DOC", "DCT", "KCO", "CO", "OBJ", "SUB", "AA", "DGJ", "FY", "PN", "EXR", "AN8", "JELN"],
                filters=filters or None,
                max_rows=max_rows,
            )
            rows = (resp.get("fs_DATABROWSE") or {}).get("data", {}).get("gridData", {}).get("rowset", [])

            if not rows:
                output = {
                    "reportName": "Batch Verification (R007011)",
                    "company": company or "ALL",
                    "batchTypeFilter": batch_type or "ALL",
                    "summary": {"totalBatchesFound": 0, "totalTransactions": 0, "totalAmount": 0, "message": "No batch transactions found."},
                    "batches": [],
                }
                return json.dumps(output, indent=2)

            # Group by batch number
            batch_map: dict[int, dict] = {}
            for row in rows:
                batch_num = int(row.get("F0911_ICU") or row.get("ICU") or 0)
                btype = str(row.get("F0911_ICUT") or row.get("ICUT") or "")
                co = str(row.get("F0911_KCO") or row.get("KCO") or "")
                amount = float(row.get("F0911_AA") or row.get("AA") or 0)
                doc_type = str(row.get("F0911_DCT") or row.get("DCT") or "")
                gl_date = str(row.get("F0911_DGJ") or row.get("DGJ") or "")

                if batch_num not in batch_map:
                    batch_map[batch_num] = {
                        "batchNumber": batch_num,
                        "batchType": btype,
                        "company": co,
                        "totalAmount": 0.0,
                        "transactionCount": 0,
                        "documentTypes": set(),
                        "earliest": gl_date,
                        "latest": gl_date,
                    }

                b = batch_map[batch_num]
                b["totalAmount"] += amount
                b["transactionCount"] += 1
                if doc_type:
                    b["documentTypes"].add(doc_type)
                if gl_date and gl_date < b["earliest"]:
                    b["earliest"] = gl_date
                if gl_date and gl_date > b["latest"]:
                    b["latest"] = gl_date

            batches = [
                {
                    "batchNumber": b["batchNumber"],
                    "batchType": b["batchType"],
                    "company": b["company"],
                    "totalAmount": round(b["totalAmount"], 2),
                    "transactionCount": b["transactionCount"],
                    "documentTypes": list(b["documentTypes"]),
                    "dateRange": {"earliest": b["earliest"], "latest": b["latest"]},
                }
                for b in batch_map.values()
            ]

            by_type: dict[str, dict] = {}
            for b in batches:
                key = b["batchType"] or "UNKNOWN"
                if key not in by_type:
                    by_type[key] = {"count": 0, "total": 0.0}
                by_type[key]["count"] += 1
                by_type[key]["total"] += b["totalAmount"]

            output = {
                "reportName": "Batch Verification (R007011)",
                "company": company or "ALL",
                "batchTypeFilter": batch_type or "ALL",
                "dateRange": {"from": date_from or "ALL", "to": date_to or "ALL"},
                "summary": {
                    "totalBatchesFound": len(batches),
                    "totalTransactions": len(rows),
                    "totalAmount": round(sum(b["totalAmount"] for b in batches), 2),
                    "byBatchType": by_type,
                },
                "batches": batches,
            }
            return _truncate(json.dumps(output, indent=2))
        except Exception as exc:
            raise RuntimeError(f"Error running batch verification: {exc}") from exc
