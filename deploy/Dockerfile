FROM postgres:18.6-bookworm@sha256:bbf83594798e144bff365a9c191c5d779f181fb3135902064ab8ff11918020fc AS pgdg-source
FROM python:3.14.9-slim-bookworm@sha256:945c2676dc2b18e0c1f16879244122c57c0ffede60006bf3df159c507a31bcae AS python-base
# Reuse the official image's PGDG signing key; apt still verifies signed indexes.
COPY --from=pgdg-source /usr/local/share/keyrings/postgres.gpg.asc /usr/local/share/keyrings/postgres.gpg.asc
COPY --from=pgdg-source /etc/apt/sources.list.d/pgdg.list /etc/apt/sources.list.d/pgdg.list
# Use Debian's security backport in both build and runtime stages.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       libssl3=3.0.22-1~deb12u2 openssl=3.0.22-1~deb12u2 libpq5=18.6-1.pgdg12+2 \
    && rm -rf /var/lib/apt/lists/*

FROM python-base AS build
WORKDIR /app
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libc6-dev libpq-dev=18.6-1.pgdg12+2 \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv==0.13.5
COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/LICENSE apps/api/NOTICE apps/api/
COPY packages/bot-sdk/pyproject.toml packages/bot-sdk/LICENSE packages/bot-sdk/NOTICE packages/bot-sdk/
COPY bots/pilot/pyproject.toml bots/pilot/LICENSE bots/pilot/NOTICE bots/pilot/
COPY apps/api/src/ apps/api/src/
COPY packages/contracts/pyproject.toml packages/contracts/LICENSE packages/contracts/NOTICE packages/contracts/
COPY packages/contracts/src/contracts/__init__.py packages/contracts/src/contracts/schemas.json packages/contracts/src/contracts/
RUN uv sync --locked --package marketob-api --extra c --no-dev --no-editable

FROM python-base
WORKDIR /app
# Dependencies are installed in build; the runtime needs no global package installer.
RUN python -m pip uninstall --yes pip
ENV PATH="/app/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ENV PSYCOPG_IMPL=c
ENV MARKETOB_HOST=0.0.0.0 MARKETOB_PORT=8000
RUN groupadd --gid 10001 marketob && useradd --uid 10001 --gid marketob --no-create-home marketob
COPY --from=build --chown=10001:10001 /app/.venv /app/.venv
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3).close()"]
CMD ["python", "-m", "marketob_api"]
