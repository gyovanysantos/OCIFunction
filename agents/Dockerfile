# ──────────────────────────────────────────────────────────────
# JDE Integrity Analyzer — Foundry Hosted Agent
# ──────────────────────────────────────────────────────────────
# Multi-stage build: slim Python 3.12 image, port 8088
# Platform: linux/amd64 (required for Foundry Agent Service)

FROM --platform=linux/amd64 python:3.12-slim

WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy agent source code
COPY . .

# Foundry Agent Service expects port 8088
EXPOSE 8088

# Entry point: HTTP server via hosting adapter
CMD ["python", "app.py"]
