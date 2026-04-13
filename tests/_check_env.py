"""Check OCI env vars."""
from dotenv import load_dotenv
load_dotenv(".env")
import os

ext = os.getenv("EXTRACTOR_AGENT_ENDPOINT_ID", "NOT SET")
ana = os.getenv("ANALYZER_AGENT_ENDPOINT_ID", "NOT SET")
print(f"EXTRACTOR: {ext[:50]}..." if len(ext) > 50 else f"EXTRACTOR: {ext}")
print(f"ANALYZER:  {ana[:50]}..." if len(ana) > 50 else f"ANALYZER:  {ana}")
print(f"OCI_AUTH:  {os.getenv('OCI_AUTH_TYPE', 'NOT SET')}")
print(f"OCI_REGION: {os.getenv('OCI_REGION', 'NOT SET')}")
print(f"BUCKET:    {os.getenv('OCI_BUCKET_NAME', 'NOT SET')}")
print(f"NAMESPACE: {os.getenv('OCI_NAMESPACE', 'NOT SET')}")
print(f"MCP_URL:   {os.getenv('MCP_SERVER_URL', 'NOT SET')}")
