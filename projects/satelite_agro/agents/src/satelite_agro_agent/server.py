"""API do agente — `POST /ask`. Um processo por projeto (não compartilhado)."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .agent import build_agent
from .config import Settings
from .direct_tools import ToolNotAvailableError, call_tool
from .observability import route_run

_state: dict[str, Any] = {}


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = Settings.from_env()
    _state["settings"] = settings
    _state["agent"] = await build_agent(settings)
    try:
        yield
    finally:
        _state.clear()


app = FastAPI(title="satelite-agro-agent", lifespan=lifespan)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class AskResponse(BaseModel):
    answer: str
    model: str
    tool_calls: list[str] = []
    # Especialistas que o Supervisor acionou nesta pergunta.
    specialists: list[str] = []
    # Saídas cruas das tools (determinísticas) — a UI usa para gráfico/tabela.
    # NÃO é texto do modelo; é o payload da própria tool.
    data: list[dict[str, Any]] = []


class ModelStatusOut(BaseModel):
    max_rpm: int
    waiting: int


class StatusResponse(BaseModel):
    ready: bool
    # Nº de `/ask` sendo processadas agora (do início ao fim da chamada ao
    # agente) — cobre a duração real de "o agente está rodando", diferente de
    # `models[*].waiting` (só o tempo bloqueado esperando o rate limiter).
    in_flight: int = 0
    models: dict[str, ModelStatusOut] = {}


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok" if _state.get("agent") else "starting"}


@app.get("/status", response_model=StatusResponse)
async def status() -> StatusResponse:
    """Fila/cota do rate limiter + perguntas em andamento — só informativo, sem dado de usuário.

    Alimenta o rodapé da UI que explica lentidão por respeito ao rate limit do
    provedor de LLM (não é falha do serviço).
    """
    agent = _state.get("agent")
    in_flight = _state.get("in_flight", 0)
    pool = getattr(agent, "model_pool", None)
    if pool is None:
        return StatusResponse(ready=False, in_flight=in_flight)
    stats = pool.stats()
    return StatusResponse(
        ready=True,
        in_flight=in_flight,
        models={
            name: ModelStatusOut(max_rpm=s.max_rpm, waiting=s.waiting) for name, s in stats.items()
        },
    )


async def _call_tool_direct(name: str, **kwargs: Any) -> dict[str, Any]:
    """Chama uma tool MCP direto, sem LLM — ver `direct_tools.py`."""
    agent = _state.get("agent")
    tools_by_name = getattr(agent, "tools_by_name", None)
    if agent is None or not tools_by_name:
        raise HTTPException(status_code=503, detail="agente ainda inicializando")
    try:
        return await call_tool(tools_by_name, name, **kwargs)
    except ToolNotAvailableError as exc:
        raise HTTPException(status_code=503, detail=f"tool indisponível: {exc}") from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"falha ao consultar: {exc}") from exc


@app.get("/land_use/summary")
async def land_use_summary(region: str, year: int = 2025, level: int = 2) -> dict[str, Any]:
    return await _call_tool_direct("get_land_use_summary", region=region, year=year, level=level)


@app.get("/land_use/at_point")
async def land_use_at_point(
    lat: float, lon: float, year: int = 2025, level: int = 2
) -> dict[str, Any]:
    return await _call_tool_direct(
        "get_land_use_at_point", lat=lat, lon=lon, year=year, level=level
    )


@app.get("/land_use/change")
async def land_use_change(
    region: str, year_from: int, year_to: int, level: int = 2
) -> dict[str, Any]:
    return await _call_tool_direct(
        "get_land_use_change", region=region, year_from=year_from, year_to=year_to, level=level
    )


@app.get("/region/point")
async def region_point(query: str) -> dict[str, Any]:
    """Resolve uma região do RS pra um ponto (lat/lon), sem LLM — só apoio de
    UI (dar zoom/centralizar mapa), reusa o mesmo geocoding do clima."""
    return await _call_tool_direct("resolve_region_point", region=query)


@app.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest) -> AskResponse:
    agent = _state.get("agent")
    settings: Settings | None = _state.get("settings")
    if agent is None or settings is None:
        raise HTTPException(status_code=503, detail="agente ainda inicializando")

    role_models = getattr(agent, "role_models", {})
    _state["in_flight"] = _state.get("in_flight", 0) + 1
    try:
        with route_run(settings.mlflow_tracking_uri, role_models=role_models) as trace:
            result = await agent.ainvoke({"question": req.question})
            specialists = list(result.get("specialists") or [])
            tool_calls = list(result.get("tool_calls") or [])
            trace.log_routing(specialists=specialists, tool_calls=tool_calls)
    except Exception as exc:
        # superfície de API: qualquer falha vira 502, sem vazar stacktrace
        raise HTTPException(status_code=502, detail=f"falha ao consultar: {exc}") from exc
    finally:
        _state["in_flight"] = _state.get("in_flight", 0) - 1

    answer = str(result.get("answer") or "").strip()
    if not answer:
        raise HTTPException(status_code=502, detail="o agente não produziu resposta")
    return AskResponse(
        answer=answer,
        model=settings.model,
        tool_calls=tool_calls,
        specialists=specialists,
        data=list(result.get("data") or []),
    )


def main() -> None:
    import uvicorn

    uvicorn.run(
        app,
        host=os.environ.get("AGENT_HOST", "0.0.0.0"),  # noqa: S104
        port=int(os.environ.get("AGENT_PORT", "8000")),
    )


if __name__ == "__main__":
    main()
