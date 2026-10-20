# --- Build stage ---
FROM python:3.11-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY config.py server.py ./
COPY vapix/ ./vapix/

# Health check label
LABEL maintainer="hex29a"
LABEL description="VPX MCP Server — Axis camera control via MCP"

# --- Test stage ---
FROM base AS test
COPY tests/ ./tests/
COPY pytest.ini .
ENTRYPOINT ["pytest"]
CMD ["-v"]

# --- Production stage ---
FROM base AS production
# Default: stdio transport (for MCP clients)
# Override with --transport streamable-http --port 8080 for HTTP mode
# (requires VAPX_MCP_TOKEN; the config path is selectable with VAPIX_CONFIG)
ENTRYPOINT ["python", "server.py"]
