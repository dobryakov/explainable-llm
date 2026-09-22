# audit (эскиз §6). Контекст сборки — корень репозитория (нужен shared/).
# Многостадийная сборка на python:3.12-slim через uv, непривилегированный
# пользователь. curl нужен для healthcheck в compose.
FROM python:3.12-slim AS base

FROM base AS builder
RUN pip install --no-cache-dir uv
WORKDIR /build
COPY services/audit/requirements.txt ./services/audit/requirements.txt
COPY shared ./shared
RUN uv venv /opt/venv \
    && . /opt/venv/bin/activate \
    && uv pip install --no-cache -r services/audit/requirements.txt \
    && uv pip install --no-cache ./shared

FROM base AS runtime
ARG CODE_VERSION=dev
ENV CODE_VERSION=${CODE_VERSION}
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --create-home --shell /usr/sbin/nologin app
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY services/audit/audit ./audit
RUN mkdir -p /config /data /fixtures /prompts /tasks /app/ui \
    && chown -R app:app /app /config /data /fixtures /prompts /tasks
USER app
ENV PORT=12103
EXPOSE 12103
CMD ["sh", "-c", "uvicorn audit.main:app --host 0.0.0.0 --port ${PORT}"]
