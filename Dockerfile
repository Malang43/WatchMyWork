FROM node:24-bookworm-slim AS frontend-build
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM node:24-bookworm-slim AS demo-build
WORKDIR /build
COPY mock-site/package*.json ./
RUN npm ci
COPY mock-site/ ./
RUN npm run build -- --base=/demo-static/

FROM python:3.13-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    WATCHMYWORK_PRODUCTION=1 \
    DATABASE_PATH=/data/watchmywork.sqlite3 \
    BOB_DEBUG_DIR=/data/bob_debug_package
WORKDIR /app
COPY backend/requirements-lock.txt backend/requirements-lock.txt
RUN pip install --no-cache-dir -r backend/requirements-lock.txt \
    && python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*
COPY backend/ backend/
COPY sample-data/ sample-data/
COPY --from=frontend-build /build/dist frontend/dist/
COPY --from=demo-build /build/dist mock-site/dist/
CMD ["python", "-m", "backend"]
