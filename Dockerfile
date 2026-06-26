# ---------- builder stage ----------
FROM python:3.10-slim AS builder

WORKDIR /build

# Install build tooling
RUN pip install --no-cache-dir hatchling

# Copy project metadata and source
COPY pyproject.toml README.md ./
COPY src/ src/

# Build wheel
RUN python -m hatchling build -t wheel

# ---------- runtime stage ----------
FROM python:3.10-slim AS runtime

LABEL org.opencontainers.image.title="gaiaagent"
LABEL org.opencontainers.image.description="AURC Protocol — Agent Unified Runtime & Communication"
LABEL org.opencontainers.image.source="https://github.com/gaiaagent/gaiaagent"
LABEL org.opencontainers.image.license="Apache-2.0"

# Create non-root user
RUN groupadd -r gaiaagent && useradd -r -g gaiaagent -d /home/gaiaagent -s /sbin/nologin gaiaagent

WORKDIR /app

# Install the built wheel plus http extras
COPY --from=builder /build/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl "gaiaagent[http,websocket,anthropic]" \
    && rm -f /tmp/*.whl

# Expose dashboard / API port
EXPOSE 8080

# Drop privileges
USER gaiaagent

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

CMD ["python", "-m", "gaiaagent.cli", "serve", "--dashboard", "--port", "8080"]
