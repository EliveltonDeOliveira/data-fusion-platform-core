# syntax=docker/dockerfile:1
FROM python:3.11-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 UV_PYTHON_DOWNLOADS=never
# libexpat1: exigida pelo GDAL embutido no wheel do rasterio.
RUN apt-get update && apt-get install -y --no-install-recommends libexpat1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src ./src

# Testes: docker build --target test -t sa-ingest-test . && docker run --rm sa-ingest-test
FROM base AS test
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --extra dev
COPY tests ./tests
CMD ["uv", "run", "--no-sync", "pytest", "-q"]

# Imagem final. Roda sob demanda (profile `ingest`), não é serviço de longa duração.
FROM base AS runtime
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev
ENV PATH="/app/.venv/bin:$PATH"
ENTRYPOINT ["python", "-m", "satelite_agro_ingestion"]
CMD []
