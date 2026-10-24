FROM python:3.14.9-slim-bookworm@sha256:945c2676dc2b18e0c1f16879244122c57c0ffede60006bf3df159c507a31bcae AS build
WORKDIR /app
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy
RUN pip install --no-cache-dir uv==0.13.5
COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY packages/bot-sdk/pyproject.toml packages/bot-sdk/pyproject.toml
COPY bots/pilot/pyproject.toml bots/pilot/pyproject.toml
COPY apps/api/src/ apps/api/src/
COPY packages/contracts/pyproject.toml packages/contracts/pyproject.toml
COPY packages/contracts/src/contracts/__init__.py packages/contracts/src/contracts/schemas.json packages/contracts/src/contracts/
RUN uv sync --locked --package marketob-api --no-dev --no-editable

FROM python:3.14.9-slim-bookworm@sha256:945c2676dc2b18e0c1f16879244122c57c0ffede60006bf3df159c507a31bcae
WORKDIR /app
# Dependencies are installed in build; the runtime needs no global package installer.
RUN python -m pip uninstall --yes pip
ENV PATH="/app/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ENV MARKETOB_HOST=0.0.0.0 MARKETOB_PORT=8000
RUN groupadd --gid 10001 marketob && useradd --uid 10001 --gid marketob --no-create-home marketob
COPY --from=build --chown=10001:10001 /app/.venv /app/.venv
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3).close()"]
CMD ["python", "-m", "marketob_api"]
