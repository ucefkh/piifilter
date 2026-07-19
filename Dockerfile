FROM python:3.11-slim AS builder

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install core package
COPY core/ ./core/
RUN uv pip install --system -e core/

# Install uvicorn
RUN uv pip install --system uvicorn[standard]

# Install SDK (depends on core)
COPY sdk/ ./sdk/
RUN uv pip install --system -e sdk/ --no-deps

# Copy plugins (discoverable by the plugin registry at runtime)
COPY plugins/ ./plugins/

# Copy rest-api source
COPY apps/rest-api/ ./apps/rest-api/

# Copy config
COPY config.yaml ./

FROM python:3.11-slim

WORKDIR /app

# Copy installed packages and source from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages/ /usr/local/lib/python3.11/site-packages/
COPY --from=builder /app/ /app/

ENV PYTHONPATH=/app/apps/rest-api/src

EXPOSE 8000

CMD ["python", "-c", "import sys; sys.path.insert(0, '/app/apps/rest-api/src'); from piifilter_api.server import create_app; import uvicorn; app = create_app(config_path='/app/config.yaml'); uvicorn.run(app, host='0.0.0.0', port=8000, log_level='info')"]