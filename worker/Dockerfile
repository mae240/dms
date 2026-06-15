# Build-Context = Repo-Root (siehe docker-compose.yml)
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends libmagic1 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY packages/dms_core /app/packages/dms_core
COPY worker /app/worker

RUN uv pip install --system -e /app/packages/dms_core -e "/app/worker[dev]"

# Gleiche UID wie das Backend, damit das geteilte Storage-Volume lesbar ist (KRITISCH)
RUN useradd -m -u 10001 appuser \
    && mkdir -p /data/storage /data/exports \
    && chown -R appuser:appuser /data /app
USER appuser

CMD ["celery", "-A", "worker.celery_tasks.celery_app", "worker", "--beat", "--loglevel=INFO", "--concurrency=2", "-Q", "processing,maintenance"]
