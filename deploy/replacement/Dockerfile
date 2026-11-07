ARG API_IMAGE=marketob-api:local
FROM ${API_IMAGE} AS build
USER 0
WORKDIR /work
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libc6-dev libpq-dev=18.6-1.pgdg12+2 \
    && rm -rf /var/lib/apt/lists/*
COPY build-requirements.txt ./
# The installer and compiler exist only in this disposable build stage.
RUN /usr/local/bin/python -m ensurepip \
    && /usr/local/bin/python -m pip install --require-hashes -r build-requirements.txt
COPY source/ ./source/
RUN /usr/local/bin/python -m pip wheel --no-deps --no-build-isolation \
      --no-cache-dir --wheel-dir /work/wheels /work/source \
    && /usr/local/bin/python -m pip --python /app/.venv/bin/python install \
      --no-deps --no-compile --force-reinstall /work/wheels/*.whl \
    && dpkg-query -W > /work/build-packages.txt

FROM ${API_IMAGE}
# COPY merges directories, so remove the old driver's metadata before the overlay.
RUN python -c "import shutil; from pathlib import Path; p=Path('/app/.venv/lib/python3.14/site-packages'); [shutil.rmtree(p / n) for n in ('psycopg_c', 'psycopg_c-3.3.6.dist-info')]"
COPY --from=build --chown=10001:10001 /app/.venv /app/.venv
# Keep the test wheel and tool inventory available for the recipient's evidence.
COPY --from=build /work/wheels/ /usr/local/share/marketob-replacement/
COPY --from=build /work/build-packages.txt /usr/local/share/marketob-replacement/
