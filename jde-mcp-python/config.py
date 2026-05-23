"""Environment-backed configuration constants."""
import os
from dotenv import load_dotenv

load_dotenv(override=False)


def _require(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"Required environment variable {name!r} is not set")
    return val


JDE_AIS_URL: str = _require("JDE_AIS_URL").rstrip("/")
JDE_USERNAME: str = _require("JDE_USERNAME")
JDE_PASSWORD: str = _require("JDE_PASSWORD")
JDE_ENVIRONMENT: str = os.getenv("JDE_ENVIRONMENT", "JDV920")
JDE_ROLE: str = os.getenv("JDE_ROLE", "*ALL")

TRANSPORT: str = os.getenv("TRANSPORT", "stdio")
PORT: int = int(os.getenv("PORT", "3000"))

CHARACTER_LIMIT: int = 50_000
DEFAULT_MAX_PAGE_SIZE: int = 100
