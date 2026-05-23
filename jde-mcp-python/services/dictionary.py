"""Curated data dictionary — load, search, list, and resolve columns."""
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_dictionary: dict | None = None


def _normalize_table(t: dict) -> dict:
    """Normalize both dictionary schemas to the canonical form.

    Old entries use tableName/displayName/functionalArea.
    Newer entries (F0011, F0911, etc.) only have table/description.
    """
    if "tableName" not in t:
        return {
            "tableName": t.get("table", ""),
            "displayName": t.get("table", ""),
            "description": t.get("description", ""),
            "functionalArea": "",
            "columns": t.get("columns", []),
        }
    return t


def load_dictionary() -> None:
    global _dictionary
    path = Path(__file__).parent.parent / "data" / "dictionary.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["tables"] = [_normalize_table(t) for t in raw["tables"]]
    _dictionary = raw
    logger.info(f"Dictionary loaded: v{_dictionary['version']} — {len(_dictionary['tables'])} tables")


def _ensure_loaded() -> dict:
    if _dictionary is None:
        raise RuntimeError("Dictionary not loaded. Call load_dictionary() at startup.")
    return _dictionary


def search_dictionary(keyword: str) -> list[dict]:
    d = _ensure_loaded()
    term = keyword.lower()
    results = []
    for table in d["tables"]:
        if (
            term in table["tableName"].lower()
            or term in table["displayName"].lower()
            or term in table["description"].lower()
            or term in table["functionalArea"].lower()
            or any(
                term in c["alias"].lower()
                or term in c["name"].lower()
                or term in c["description"].lower()
                for c in table["columns"]
            )
        ):
            results.append(table)
    return results


def list_tables() -> list[dict]:
    d = _ensure_loaded()
    return [
        {"tableName": t["tableName"], "displayName": t["displayName"], "functionalArea": t["functionalArea"]}
        for t in d["tables"]
    ]


def get_table(table_name: str) -> dict | None:
    d = _ensure_loaded()
    upper = table_name.upper()
    return next((t for t in d["tables"] if t["tableName"].upper() == upper), None)


def resolve_columns(table_name: str, columns: list[str]) -> dict:
    d = _ensure_loaded()
    table = next((t for t in d["tables"] if t["tableName"].upper() == table_name.upper()), None)
    if not table:
        return {"valid": columns, "invalid": []}
    known = {c["alias"].upper() for c in table["columns"]}
    valid, invalid = [], []
    for col in columns:
        (valid if col.upper() in known else invalid).append(col)
    return {"valid": valid, "invalid": invalid}
