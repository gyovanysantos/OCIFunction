"""AIS REST client — token auth, data queries, and orchestration calls.

Auth flow:
  1. login()  — POST /v2/tokenrequest (Basic Auth once) → stores AIS token
  2. All requests use 'jde-AIS-Auth: <token>' header
  3. start_refresh_loop() — re-authenticates every 25 min (before 30-min expiry)
  4. logout() — POST /v2/tokenrequest/logout on shutdown
"""
import asyncio
import base64
import logging
from typing import Any

import httpx

from config import (
    JDE_AIS_URL,
    JDE_USERNAME,
    JDE_PASSWORD,
    JDE_ENVIRONMENT,
    JDE_ROLE,
    CHARACTER_LIMIT,
)

logger = logging.getLogger(__name__)

# Basic Auth is used ONLY for the login call
_BASIC_AUTH = "Basic " + base64.b64encode(
    f"{JDE_USERNAME}:{JDE_PASSWORD}".encode()
).decode()

_TIMEOUT = httpx.Timeout(55.0)
_REFRESH_INTERVAL = 25 * 60  # seconds — refresh before the 30-min AIS expiry

# ── Token state (module-level, single process) ────────────────────────────────

_token: str | None = None
_refresh_task: asyncio.Task | None = None


# ── Auth lifecycle ────────────────────────────────────────────────────────────

async def login() -> str:
    """Authenticate with AIS and store the session token.

    Uses Basic Auth once to obtain a token.  All subsequent AIS calls
    use the token via the 'jde-AIS-Auth' header.
    """
    global _token
    url = f"{JDE_AIS_URL}/v2/tokenrequest"
    body = {"environment": JDE_ENVIRONMENT, "role": JDE_ROLE}
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(url, json=body, headers={
            "Authorization": _BASIC_AUTH,
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        resp.raise_for_status()
        data = resp.json()

    _token = data["userInfo"]["token"]
    logger.info(f"AIS token acquired for user '{data.get('username')}'")
    return _token


async def logout() -> None:
    """Terminate the AIS session and cancel the refresh loop."""
    global _token, _refresh_task
    if _refresh_task and not _refresh_task.done():
        _refresh_task.cancel()
        _refresh_task = None

    if not _token:
        return

    url = f"{JDE_AIS_URL}/v2/tokenrequest/logout"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            await client.post(url, json={"token": _token}, headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            })
        logger.info("AIS session logged out")
    except Exception as exc:
        logger.warning(f"Logout failed (non-fatal): {exc}")
    finally:
        _token = None


async def _refresh_loop() -> None:
    """Background task: re-authenticate every 25 minutes."""
    while True:
        await asyncio.sleep(_REFRESH_INTERVAL)
        try:
            await login()
            logger.info("AIS token refreshed")
        except Exception as exc:
            logger.error(f"Token refresh failed: {exc}")


def start_refresh_loop() -> None:
    """Schedule the background token refresh task (call after login)."""
    global _refresh_task
    _refresh_task = asyncio.ensure_future(_refresh_loop())


def _auth_headers() -> dict:
    """Return request headers using the current AIS token."""
    if not _token:
        raise RuntimeError("AIS token not available — login() must be called at startup")
    return {
        "jde-AIS-Auth": _token,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


# ── Shared helpers ────────────────────────────────────────────────────────────

def add_filter(
    filters: list[dict],
    column: str,
    operator: str,
    value: Any,
) -> None:
    """Append a filter condition; no-op for None or empty string values."""
    if value is None or value == "":
        return
    filters.append({"column": column, "operator": operator, "value": str(value)})


def truncate(text: str, records: int | None = None) -> str:
    if len(text) <= CHARACTER_LIMIT:
        return text
    suffix = f"\n\n... [TRUNCATED — {records if records is not None else 'many'} total records. Narrow your filters.]"
    return text[:CHARACTER_LIMIT] + suffix


def _build_conditions(table_name: str, filters: list[dict]) -> list[dict]:
    """Convert simple filter dicts to AIS DataService condition format."""
    conditions = []
    for f in filters:
        col = f["column"]
        op = f["operator"]
        val = f["value"]
        control_id = f"{table_name}.{col}"

        if op == "BETWEEN" and isinstance(val, list) and len(val) == 2:
            conditions.append({
                "controlId": control_id,
                "operator": "BETWEEN",
                "value": [
                    {"content": str(val[0]), "specialValueId": "LITERAL"},
                    {"content": str(val[1]), "specialValueId": "LITERAL"},
                ],
            })
        elif op == "LIST" and isinstance(val, list):
            conditions.append({
                "controlId": control_id,
                "operator": "LIST",
                "value": [{"content": str(v), "specialValueId": "LITERAL"} for v in val],
            })
        else:
            conditions.append({
                "controlId": control_id,
                "operator": op,
                "value": [{"content": str(val), "specialValueId": "LITERAL"}],
            })
    return conditions


# ── AIS API calls ─────────────────────────────────────────────────────────────

async def query_table(
    table_name: str,
    columns: list[str],
    filters: list[dict] | None = None,
    max_rows: int = 100,
) -> dict:
    """Query a JDE table via AIS Data Service (DATABROWSE).

    Returns the raw AIS JSON response with the key normalized to `fs_DATABROWSE`.
    """
    body: dict[str, Any] = {
        "targetName": table_name,
        "targetType": "table",
        "dataServiceType": "BROWSE",
        "findOnEntry": "TRUE",
        "maxPageSize": str(max_rows),
        "environment": JDE_ENVIRONMENT,
        "role": JDE_ROLE,
    }

    if columns:
        body["returnControlIDs"] = "|".join(columns)

    if filters:
        body["query"] = {
            "autoFind": True,
            "condition": _build_conditions(table_name, filters),
        }

    url = f"{JDE_AIS_URL}/v2/dataservice"

    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_auth_headers()) as client:
        resp = await client.post(url, json=body)
        resp.raise_for_status()
        data = resp.json()

    # Normalize the dynamic key (e.g. fs_DATABROWSE_F0411 → fs_DATABROWSE)
    normalized: dict = {}
    for key, val in data.items():
        if key.startswith("fs_DATABROWSE"):
            normalized["fs_DATABROWSE"] = val
        else:
            normalized[key] = val

    return normalized


async def call_orchestration(name: str, inputs: dict) -> dict:
    """Call a JDE orchestration via AIS Orchestrator."""
    body = {
        **inputs,
        "environment": JDE_ENVIRONMENT,
        "role": JDE_ROLE,
    }

    url = f"{JDE_AIS_URL}/v3/orchestrator/{name}"

    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_auth_headers()) as client:
        resp = await client.post(url, json=body)
        resp.raise_for_status()
        return resp.json()
