# Build-Context = Repo-Root (siehe docker-compose.yml)
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# libmagic fuer python-magic (Magic-Byte-Validierung)
RUN apt-get update \
    && apt-get install -y --no-install-recommends libmagic1 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

# Erst Metadaten/Quellen kopieren, dann installieren
COPY packages/dms_core /app/packages/dms_core
COPY backend /app/backend
COPY alembic /app/alembic
COPY alembic.ini /app/alembic.ini

RUN uv pip install --system -e /app/packages/dms_core -e "/app/backend[dev]"

# Non-root + Datenverzeichnisse (geteilte UID mit dem Worker)
RUN useradd -m -u 10001 appuser \
    && mkdir -p /data/storage /data/exports \
    && chown -R appuser:appuser /data /app
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
