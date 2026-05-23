"""Live table discovery via F9200/F9210/F9860 — mirrors dd-discovery.ts."""
import asyncio
import logging

from services.ais_client import query_table

logger = logging.getLogger(__name__)

_table_cache: dict[str, dict] = {}

_F9210_COLUMNS = ["DTAI", "DTAS", "DTAD", "CLAS"]
_CHUNK_SIZE = 100


async def discover_table(table_name: str) -> dict:
    name = table_name.upper().strip()
    if name in _table_cache:
        return _table_cache[name]

    # Step 1: introspect by querying with no column restriction, 1 row
    resp = await query_table(table_name=name, columns=[], max_rows=1)
    rows = (resp.get("fs_DATABROWSE") or {}).get("data", {}).get("gridData", {}).get("rowset")
    if not rows:
        raise ValueError(
            f'Table "{name}" returned no data. It may be empty, not exposed via AIS, or the name is wrong.'
        )

    # Step 2: extract aliases from response keys e.g. "F0101_AN8" → "AN8"
    prefix = f"{name}_"
    aliases = [
        key[len(prefix):]
        for key in rows[0]
        if key.startswith(prefix) and key[len(prefix):]
    ]
    if not aliases:
        raise ValueError(f'Table "{name}" returned data but no recognizable column aliases.')

    # Step 3: fetch descriptions + metadata in parallel
    desc_map, meta_map = await asyncio.gather(
        _fetch_descriptions(aliases),
        _fetch_metadata(aliases),
    )

    columns = [
        {
            "alias": alias,
            "description": desc_map.get(alias, "(no description)"),
            "dataType": meta_map.get(alias, {}).get("dataType", ""),
            "size": meta_map.get(alias, {}).get("size", 0),
            "decimalPlaces": meta_map.get(alias, {}).get("decimalPlaces", 0),
            "sequence": i + 1,
        }
        for i, alias in enumerate(aliases)
    ]

    result = {
        "tableName": name,
        "description": f"{name} ({len(columns)} columns discovered)",
        "columns": columns,
        "columnCount": len(columns),
    }
    _table_cache[name] = result
    return result


async def search_tables(keyword: str, max_rows: int = 20) -> list[dict]:
    by_name = await _search_by_column("OBNM", keyword, max_rows)
    if by_name:
        return by_name
    return await _search_by_column("MD", keyword, max_rows)


def is_table_cached(table_name: str) -> bool:
    return table_name.upper().strip() in _table_cache


def get_cache_stats() -> dict:
    return {"cachedTables": len(_table_cache), "tableNames": list(_table_cache)}


def clear_cache() -> None:
    _table_cache.clear()


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _fetch_descriptions(aliases: list[str]) -> dict[str, str]:
    desc_map: dict[str, str] = {}
    for i in range(0, len(aliases), _CHUNK_SIZE):
        chunk = aliases[i : i + _CHUNK_SIZE]
        try:
            resp = await query_table(
                table_name="F9200",
                columns=["DTAI"],
                filters=[{"column": "DTAI", "operator": "LIST", "value": chunk}],
                max_rows=len(chunk),
            )
            for row in (resp.get("fs_DATABROWSE") or {}).get("data", {}).get("gridData", {}).get("rowset", []):
                alias = str(row.get("F9200_DTAI") or "").strip()
                if alias:
                    desc_map[alias] = alias
        except Exception:
            pass
    return desc_map


async def _fetch_metadata(aliases: list[str]) -> dict[str, dict]:
    meta_map: dict[str, dict] = {}
    for i in range(0, len(aliases), _CHUNK_SIZE):
        chunk = aliases[i : i + _CHUNK_SIZE]
        try:
            resp = await query_table(
                table_name="F9210",
                columns=_F9210_COLUMNS,
                filters=[{"column": "DTAI", "operator": "LIST", "value": chunk}],
                max_rows=len(chunk),
            )
            for row in (resp.get("fs_DATABROWSE") or {}).get("data", {}).get("gridData", {}).get("rowset", []):
                alias = str(row.get("F9210_DTAI") or "").strip()
                if alias:
                    meta_map[alias] = {
                        "dataType": str(row.get("F9210_CLAS") or "").strip(),
                        "size": int(row.get("F9210_DTAS") or 0),
                        "decimalPlaces": int(row.get("F9210_DTAD") or 0),
                    }
        except Exception:
            pass
    return meta_map


async def _search_by_column(column: str, keyword: str, max_rows: int) -> list[dict]:
    try:
        resp = await query_table(
            table_name="F9860",
            columns=["OBNM", "MD"],
            filters=[{"column": column, "operator": "STR_CONTAIN", "value": keyword.upper()}],
            max_rows=max_rows,
        )
        rows = (resp.get("fs_DATABROWSE") or {}).get("data", {}).get("gridData", {}).get("rowset", [])
        return [
            {
                "tableName": str(row.get("F9860_OBNM") or "").strip(),
                "description": str(row.get("F9860_MD") or "").strip(),
                "objectType": "TABLE",
            }
            for row in rows
        ]
    except Exception:
        return []
