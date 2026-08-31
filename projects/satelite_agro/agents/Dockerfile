# syntax=docker/dockerfile:1
FROM python:3.11-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src ./src

# Alvo de testes: docker build --target test -t sa-agent-test . && docker run --rm sa-agent-test
FROM base AS test
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --extra dev
COPY tests ./tests
CMD ["uv", "run", "--no-sync", "pytest", "-q"]

# Imagem final.
FROM base AS runtime
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["python", "-m", "satelite_agro_agent.server"]
