"""End-to-end workflow test — Extractor → Analyzer.

Calls the ExtractorAgent to download & extract the PDF, then passes
the extraction result to the AnalyzerAgent for MCP-verified analysis.

Usage: python tests/test_workflow.py
"""
import json
import sys
import time
import requests

EXTRACTOR_URL = "http://localhost:8088"
ANALYZER_URL = "http://localhost:8089"
PDF_OBJECT = "R047001A_ZJDE0001_588_PDF.pdf"


def call_agent(url: str, message: str, label: str, timeout: int = 180) -> dict:
    """Call a Foundry hosted agent via the /responses endpoint."""
    print(f"\n{'='*60}")
    print(f"Calling {label}...")
    print(f"URL: {url}/responses")
    print(f"Input: {message[:200]}...")
    print(f"{'='*60}")

    start = time.time()
    resp = requests.post(
        f"{url}/responses",
        json={"input": message},
        headers={"Content-Type": "application/json"},
        timeout=timeout,
    )
    elapsed = time.time() - start

    print(f"Status: {resp.status_code} ({elapsed:.1f}s)")

    if resp.status_code != 200:
        print(f"ERROR: {resp.text[:500]}")
        return {"error": resp.text}

    data = resp.json()
    return data


def extract_output_text(response: dict) -> str:
    """Extract the text output from a Foundry agent response."""
    # The response follows OpenAI Responses API format
    if "output" in response:
        # output is a list of output items
        for item in response["output"]:
            if item.get("type") == "message":
                for content in item.get("content", []):
                    if content.get("type") == "output_text":
                        return content.get("text", "")
    # Fallback: try direct text
    if "text" in response:
        return response["text"]
    # Fallback: dump the whole thing
    return json.dumps(response, indent=2)


def main():
    print("=" * 60)
    print("JDE Integrity Analyzer — End-to-End Workflow Test")
    print(f"PDF: {PDF_OBJECT}")
    print("=" * 60)

    # ── Step 1: ExtractorAgent ────────────────────────────────
    extractor_response = call_agent(
        EXTRACTOR_URL,
        f"Please download and extract the PDF: {PDF_OBJECT}",
        "ExtractorAgent",
        timeout=180,
    )

    extraction_text = extract_output_text(extractor_response)
    print(f"\n--- Extractor Output ({len(extraction_text)} chars) ---")
    print(extraction_text[:2000])
    if len(extraction_text) > 2000:
        print(f"\n... ({len(extraction_text) - 2000} more chars)")

    # Save extractor output
    with open("tests/extractor_output.json", "w") as f:
        json.dump(extractor_response, f, indent=2)
    print("\nSaved full extractor response to tests/extractor_output.json")

    # ── Step 2: AnalyzerAgent ─────────────────────────────────
    analyzer_response = call_agent(
        ANALYZER_URL,
        f"Analyze this extraction from the JDE Integrity Report:\n\n{extraction_text}",
        "AnalyzerAgent",
        timeout=300,
    )

    analysis_text = extract_output_text(analyzer_response)
    print(f"\n--- Analyzer Output ({len(analysis_text)} chars) ---")
    print(analysis_text[:5000])
    if len(analysis_text) > 5000:
        print(f"\n... ({len(analysis_text) - 5000} more chars)")

    # Save analyzer output
    with open("tests/analyzer_output.json", "w") as f:
        json.dump(analyzer_response, f, indent=2)
    print("\nSaved full analyzer response to tests/analyzer_output.json")

    # ── Summary ────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("WORKFLOW COMPLETE")
    print(f"  Extractor output: {len(extraction_text)} chars")
    print(f"  Analyzer output:  {len(analysis_text)} chars")
    print("=" * 60)


if __name__ == "__main__":
    main()
