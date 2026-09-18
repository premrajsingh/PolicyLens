FROM node:22-bookworm-slim AS frontend
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    APP_HOST=0.0.0.0 APP_PORT=8000 OCR_ENABLED=true SERVE_FRONTEND=true
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 policylens
COPY backend/pyproject.toml backend/README.md backend/requirements.lock ./
COPY backend/app ./app
RUN pip install --no-cache-dir -r requirements.lock && pip install --no-deps .
COPY --from=frontend /web/dist ./static
COPY data/sample_policies ./sample_policies
RUN mkdir -p /data && chown -R policylens:policylens /data /app
ENV DATA_DIR=/data OUTPUT_DIR=/data/outputs DATABASE_URL=sqlite:////data/policylens.db \
    AUTO_SEED_SAMPLES=true
USER policylens
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)" || exit 1
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --proxy-headers"]
