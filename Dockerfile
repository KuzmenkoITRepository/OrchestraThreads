FROM python:3.11-slim AS base

WORKDIR /app

COPY requirements.txt .
RUN apt-get update \
    && apt-get install -y --no-install-recommends docker-cli docker-compose \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY agents ./agents
COPY README.md ./
COPY pyproject.toml ./
COPY setup.cfg ./

ENV PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ORCHESTRA_THREADS_HOST=0.0.0.0 \
    ORCHESTRA_THREADS_PORT=8788 \
    ORCHESTRA_THREADS_DATABASE_URL=postgresql://orchestra:orchestra@postgres:5432/orchestra_threads \
    ORCHESTRA_THREADS_DB_SCHEMA=public

RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8787 8788 8790

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8788/healthz').status == 200 else 1)"

FROM base AS runtime

CMD ["python", "-m", "core.orchestra_thread.service.main"]

FROM base AS test

CMD ["python", "-m", "pytest", "-v"]
