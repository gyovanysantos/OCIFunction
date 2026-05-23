FROM python:3.12-slim
WORKDIR /app

RUN groupadd -r mcp && useradd -r -g mcp mcp

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config.py server.py ./
COPY services/ ./services/
COPY tools/ ./tools/
COPY data/ ./data/

USER mcp

ENV TRANSPORT=http
ENV PORT=3000

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:3000/health')" || exit 1

CMD ["python", "server.py"]
