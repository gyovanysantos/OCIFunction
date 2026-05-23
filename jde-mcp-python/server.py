"""JDE MCP Python Server — FastMCP streamable-http transport.

Equivalent to the TypeScript jde-mcp-ube-analyzer server.
Exposes 14 tools across 4 layers:
  Layer 0 — Discovery  (jde_discover_table, jde_search_tables)
  Layer 1 — Dictionary (jde_dictionary_search, _list, _table)
  Layer 2 — Integrity  (jde_ap_voucher_query, jde_gl_balance_query, jde_gl_detail_query, jde_ap_gl_integrity_check)
  Layer 2 — Batch      (jde_batch_query, jde_batch_transaction_query, jde_unposted_batch_check)
  Layer 3 — Generic    (jde_query_table, jde_call_orchestration)

Auth: AIS token obtained at startup via /v2/tokenrequest, refreshed every
25 min, terminated on shutdown via /v2/tokenrequest/logout.
"""
import asyncio
import logging
import signal

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from config import PORT, TRANSPORT
from services.dictionary import load_dictionary
from services.ais_client import login, logout, start_refresh_loop
from tools import discovery, dictionary_tools, integrity, batch, query, orchestration

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


mcp = FastMCP(
    name="jde-integrity-analyzer",
    stateless_http=True,
    json_response=True,
)

# ── Register all tools ─────────────────────────────────────────────────────────
discovery.register(mcp)
dictionary_tools.register(mcp)
integrity.register(mcp)
batch.register(mcp)
query.register(mcp)
orchestration.register(mcp)

# ── Health endpoint ────────────────────────────────────────────────────────────
@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "version": "2.0-python"})


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    load_dictionary()

    if TRANSPORT == "http":
        import uvicorn

        async def _serve() -> None:
            await login()
            start_refresh_loop()
            logger.info(f"Starting JDE MCP server — transport=http port={PORT}")

            app = mcp.streamable_http_app()
            config = uvicorn.Config(app, host="0.0.0.0", port=PORT, log_level="info")
            server = uvicorn.Server(config)

            loop = asyncio.get_event_loop()

            async def _shutdown() -> None:
                logger.info("Shutdown signal received — logging out AIS session")
                await logout()
                server.should_exit = True

            for sig in (signal.SIGINT, signal.SIGTERM):
                try:
                    loop.add_signal_handler(sig, lambda: asyncio.ensure_future(_shutdown()))
                except NotImplementedError:
                    # Windows does not support add_signal_handler on the event loop
                    pass

            await server.serve()

        asyncio.run(_serve())

    else:
        async def _stdio() -> None:
            await login()
            start_refresh_loop()
            logger.info("Starting JDE MCP server — transport=stdio")
            try:
                await mcp.run_stdio_async()
            finally:
                await logout()

        asyncio.run(_stdio())
