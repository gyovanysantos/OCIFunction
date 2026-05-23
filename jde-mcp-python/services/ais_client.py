"""AIS REST client — Basic Auth, data queries, and orchestration calls."""
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

_BASIC_AUTH = "Basic " + base64.b64encode(
    f"{JDE_USERNAME}:{JDE_PASSWORD}".encode()
).decode()

_HEADERS = {
    "Authorization": _BASIC_AUTH,
    "Content-Type": "application/json",
    "Accept": "application/json",
}

_TIMEOUT = httpx.Timeout(55.0)


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

    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS) as client:
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

    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS) as client:
        resp = await client.post(url, json=body)
        resp.raise_for_status()
        return resp.json()
