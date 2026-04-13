"""Run the full ExtractorAgent → AnalyzerAgent workflow locally.

Tests the OCI ADK workflow end-to-end against a real PDF.
MCP server must be running at localhost:3000.

Usage:
    python tests/test_workflow_e2e.py [object_name]

Default: R007011_SCH0001_32189_PDF.pdf
"""
import json
import logging
import os
import sys
import time

# ── Path + env setup ──────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "agents"))

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"), override=False)

os.environ.setdefault("MCP_SERVER_URL", "http://localhost:3000/mcp")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)-25s %(levelname)-5s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("test_e2e")

# ── Config ────────────────────────────────────────────────────
PDF_OBJECT = sys.argv[1] if len(sys.argv) > 1 else "R007011_SCH0001_32189_PDF.pdf"


def main():
    from workflow import run_extractor, run_analyzer

    print("=" * 70)
    print("JDE Integrity Analyzer — Local E2E Workflow Test")
    print(f"  PDF:        {PDF_OBJECT}")
    print(f"  MCP Server: {os.getenv('MCP_SERVER_URL')}")
    print(f"  OCI Region: {os.getenv('OCI_REGION')}")
    print(f"  Auth:       {os.getenv('OCI_AUTH_TYPE')}")
    print("=" * 70)

    # ── Step 1: ExtractorAgent ────────────────────────────────
    print("\n[1/2] Running ExtractorAgent...")
    t0 = time.time()

    try:
        extractor_text = run_extractor(PDF_OBJECT)
    except Exception as e:
        print(f"\n❌ ExtractorAgent FAILED: {e}")
        logger.exception("ExtractorAgent error")
        sys.exit(1)

    t1 = time.time()
    print(f"  ✅ Done ({t1 - t0:.1f}s) — {len(extractor_text)} chars")
    print("\n--- Extractor Output (first 3000 chars) ---")
    print(extractor_text[:3000])
    if len(extractor_text) > 3000:
        print(f"\n... (truncated, total {len(extractor_text)} chars)")

    # Save extractor output
    out_path = os.path.join(ROOT, "tests", "extractor_output.json")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(extractor_text)
    print(f"\n  Saved to: {out_path}")

    # ── Check has_data ────────────────────────────────────────
    has_data = False
    try:
        data = json.loads(extractor_text)
        has_data = bool(data.get("has_data", False))
    except (json.JSONDecodeError, TypeError):
        import re
        match = re.search(r'"has_data"\s*:\s*(true|false)', extractor_text, re.IGNORECASE)
        if match:
            has_data = match.group(1).lower() == "true"
        else:
            has_data = len(extractor_text.strip()) > 300

    if not has_data:
        print("\n📋 has_data=False — No data to analyze. Skipping AnalyzerAgent.")
        print("  This is normal for clean/empty reports.")
        sys.exit(0)

    print(f"\n📋 has_data=True — Proceeding to AnalyzerAgent...")

    # ── Step 2: AnalyzerAgent ─────────────────────────────────
    print("\n[2/2] Running AnalyzerAgent...")
    t2 = time.time()

    try:
        analysis_text = run_analyzer(extractor_text)
    except Exception as e:
        print(f"\n❌ AnalyzerAgent FAILED: {e}")
        logger.exception("AnalyzerAgent error")
        sys.exit(1)

    t3 = time.time()
    print(f"  ✅ Done ({t3 - t2:.1f}s) — {len(analysis_text)} chars")
    print("\n--- Analyzer Output ---")
    print(analysis_text[:5000])
    if len(analysis_text) > 5000:
        print(f"\n... (truncated, total {len(analysis_text)} chars)")

    # Save analyzer output
    out_path_a = os.path.join(ROOT, "tests", "analyzer_output.json")
    with open(out_path_a, "w", encoding="utf-8") as f:
        f.write(analysis_text)
    print(f"\n  Saved to: {out_path_a}")

    # ── Summary ───────────────────────────────────────────────
    total = t3 - t0
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  PDF:            {PDF_OBJECT}")
    print(f"  Extractor:      {t1 - t0:.1f}s → {len(extractor_text)} chars")
    print(f"  Analyzer:       {t3 - t2:.1f}s → {len(analysis_text)} chars")
    print(f"  Total:          {total:.1f}s")
    print(f"  has_data:       {has_data}")
    print("=" * 70)


if __name__ == "__main__":
    main()
