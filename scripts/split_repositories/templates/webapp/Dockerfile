########################################
# Stage 1: Build/minify frontend assets
########################################
FROM node:20-alpine AS assets

WORKDIR /app
COPY package.json ./
COPY scripts ./scripts
COPY webapp/static ./webapp/static

RUN npm install --no-audit --no-fund \
    && npm run build:assets \
    && find webapp/static -type f -name '*.min.js' -print0 | while IFS= read -r -d '' f; do t="${f%.min.js}.js"; cp "$f" "$t"; done

########################################
# Stage 2: Python runtime
########################################
FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential curl git && \
    rm -rf /var/lib/apt/lists/*

RUN useradd -m -r appuser
WORKDIR /app

# Install engine first (override NATURAL20_ENGINE_REF at build time).
ARG NATURAL20_ENGINE_REF=../natural_20.py
COPY requirements.txt pyproject.toml README.md ./
RUN pip install --no-cache-dir -r requirements.txt gunicorn eventlet

COPY . .
COPY --from=assets /app/webapp/static /app/webapp/static

RUN pip install --no-cache-dir -e . \
    && mkdir -p /app/webapp/flask_session /app/webapp/saves \
    && chown -R appuser:appuser /app/webapp/flask_session /app/webapp/saves

ENV PORT=5001
EXPOSE ${PORT}
ENV FLASK_ENV=production
ENV FLASK_APP=webapp/app.py
ENV SAVE_DIR=/app/webapp/saves
ENV TEMPLATE_DIR=/campaigns

USER appuser
WORKDIR /app/webapp
CMD ["gunicorn", "--worker-class", "eventlet", "--workers", "1", "--bind", "0.0.0.0:5001", "--timeout", "120", "app:app"]
