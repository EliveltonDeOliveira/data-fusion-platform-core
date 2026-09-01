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


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok" if _state.get("agent") else "starting"}


@app.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest) -> AskResponse:
    agent = _state.get("agent")
    settings: Settings | None = _state.get("settings")
    if agent is None or settings is None:
        raise HTTPException(status_code=503, detail="agente ainda inicializando")

    role_models = getattr(agent, "role_models", {})
    try:
        with route_run(settings.mlflow_tracking_uri, role_models=role_models) as trace:
            result = await agent.ainvoke({"question": req.question})
            specialists = list(result.get("specialists") or [])
            tool_calls = list(result.get("tool_calls") or [])
            trace.log_routing(specialists=specialists, tool_calls=tool_calls)
    except Exception as exc:
        # superfície de API: qualquer falha vira 502, sem vazar stacktrace
        raise HTTPException(status_code=502, detail=f"falha ao consultar: {exc}") from exc

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
