# syntax=docker/dockerfile:1

FROM node:25.2.1-bookworm-slim AS frontend-build

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
COPY intent-model/artifacts/intent-model.v1.json /build/intent-model/artifacts/intent-model.v1.json
RUN npm run build


FROM python:3.14.7-slim AS python-build

ENV PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY pyproject.toml ./
COPY src/ ./src/
RUN python -m pip install --no-cache-dir --no-compile --target /opt/sahayi-python .


FROM python:3.14.7-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

RUN addgroup --system --gid 10001 sahayi \
    && adduser --system --uid 10001 --ingroup sahayi --home /app --no-create-home sahayi

WORKDIR /app
COPY --from=python-build --chown=10001:10001 /opt/sahayi-python/ /app/src/
COPY --from=frontend-build --chown=10001:10001 /build/frontend/dist/ /app/frontend/dist/
COPY --chown=10001:10001 procedure-packs/packs/ /app/procedure-packs/packs/

USER 10001:10001
EXPOSE 10000

CMD ["sh", "-c", "exec python -m uvicorn sahayi_api.main:app --host 0.0.0.0 --port \"${PORT:-10000}\""]
