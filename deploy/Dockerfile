# Single-stage image for the OpenFeedback API and admin UI.
#
# BASE_IMAGE is a build argument so a deployment behind a registry mirror can
# point at a mirror without editing this file.
ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Build tools are not needed at runtime; the wheels are all pure Python.
# PIP_INDEX_URL lets a deployment behind a firewall point at a mirror;
# pip picks it up from the environment on its own.
ARG PIP_INDEX_URL
ENV PIP_INDEX_URL=${PIP_INDEX_URL}
COPY requirements.txt .
RUN if [ -n "$PIP_INDEX_URL" ]; then \
        pip install --no-cache-dir --index-url "$PIP_INDEX_URL" --trusted-host "$(echo "$PIP_INDEX_URL" | awk -F/ '{print $3}')" -r requirements.txt; \
    else \
        pip install --no-cache-dir -r requirements.txt; \
    fi

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app

# Run as a non-root user; the data directory is a mounted volume.
RUN useradd --system --uid 10001 --create-home openfeedback \
    && mkdir -p /data/attachments \
    && chown -R openfeedback:openfeedback /app /data
USER openfeedback

ENV OF_DATA_DIR=/data \
    OF_ATTACHMENTS_DIR=/data/attachments \
    OF_HOST=0.0.0.0 \
    OF_PORT=8080

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/api/v1/health', timeout=4).status == 200 else 1)"

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
