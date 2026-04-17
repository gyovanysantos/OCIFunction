"""Test the Docker API endpoint with a real PDF.

Usage: python tests/test_api_docker.py [object_name]
Default: R007011_SCH0001_32189_PDF.pdf
"""
import httpx
import json
import re
import sys
import time

API_URL = "http://localhost:8080"
OBJECT_NAME = sys.argv[1] if len(sys.argv) > 1 else "R007011_SCH0001_32189_PDF.pdf"


def main():
    print("=" * 60)
    print("Docker API E2E Test")
    print(f"  API:    {API_URL}")
    print(f"  PDF:    {OBJECT_NAME}")
    print("=" * 60)

    # Health check
    print("\n── Health Check ──")
    try:
        h = httpx.get(f"{API_URL}/health", timeout=10)
        print(f"  Status: {h.status_code} — {h.json()}")
    except Exception as e:
        print(f"  FAILED: {e}")
        sys.exit(1)

    # POST /v1/analyze
    print(f"\n── POST /v1/analyze ──")
    print(f"  Sending: {OBJECT_NAME}")
    t0 = time.time()

    try:
        resp = httpx.post(
            f"{API_URL}/v1/analyze",
            json={"object_name": OBJECT_NAME},
            timeout=120,
        )
    except httpx.ReadTimeout:
        elapsed = time.time() - t0
        print(f"  TIMEOUT after {elapsed:.0f}s — the API may still be processing")
        print("  Check: docker compose logs -f api")
        sys.exit(1)

    elapsed = time.time() - t0
    print(f"  Status: {resp.status_code} ({elapsed:.1f}s)")

    if resp.status_code != 200:
        print(f"  Error: {resp.text[:500]}")
        sys.exit(1)

    data = resp.json()
    checker = data["checkerResponse"]
    analysis = data["analysisResponse"]

    print(f"  checkerResponse: {checker}")
    print(f"  analysisResponse: {len(analysis)} chars (HTML)")

    # Strip HTML for readable output
    text = re.sub(r"<[^>]+>", " ", analysis)
    text = re.sub(r"\s+", " ", text).strip()
    print(f"\n── Analysis (plain text preview) ──")
    print(text[:3000])
    if len(text) > 3000:
        print(f"\n... (truncated, total {len(text)} chars)")

    print(f"\n{'=' * 60}")
    print(f"RESULT: checkerResponse={checker}, {len(analysis)} chars HTML, {elapsed:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
