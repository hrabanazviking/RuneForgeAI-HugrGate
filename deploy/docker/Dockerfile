# syntax=docker/dockerfile:1
# HugrGate service image. Gjallarbrú slice 446.
#
# Build:  docker build -f deploy/docker/Dockerfile -t hugrgate:latest .
# Run:    docker compose -f deploy/docker/docker-compose.yml up -d
#
# Notes:
# - python:3.12-slim keeps the image small; the daemon needs only
#   the `server` extra (fastapi/uvicorn/httpx/pydantic).
# - Runs as a non-root user; the daemon never needs root.
# - HEALTHCHECK hits /health so orchestrators can gate on readiness.

FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /src
COPY pyproject.toml README.md ./
COPY hugrgate ./hugrgate
RUN pip install --prefix=/install --no-deps "pyyaml>=6.0" && \
    pip install --prefix=/install ".[server]"


FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/usr/local/bin:${PATH}"

RUN groupadd -r hugr && useradd -r -g hugr -d /app hugr && \
    mkdir -p /app /etc/hugrgate && chown hugr:hugr /app /etc/hugrgate

COPY --from=builder /install /usr/local
COPY --chown=hugr:hugr deploy/docker/hugrgate.yaml /etc/hugrgate/hugrgate.yaml

USER hugr
WORKDIR /app
EXPOSE 8377

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; \
        sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8377/health', timeout=4).status == 200 else 1)"

ENTRYPOINT ["hugrgate"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8377", \
     "--config", "/etc/hugrgate/hugrgate.yaml"]
