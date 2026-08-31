"""API do agente — `POST /ask`. Um processo por projeto (não compartilhado)."""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from langchain_core.messages import AIMessage, ToolMessage
from pydantic import BaseModel, Field

from .agent import build_agent
from .config import Settings

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
    # Saídas cruas das tools (determinísticas) — a UI usa para gráfico/tabela.
    # NÃO é texto do modelo; é o payload da própria tool.
    data: list[dict[str, Any]] = []


def _final_text(messages: list[Any]) -> str:
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and not msg.tool_calls:
            content = msg.content
            if isinstance(content, str):
                return content.strip()
            # Gemini às vezes devolve blocos; concatena os de texto
            parts = [
                b.get("text", "") if isinstance(b, dict) else str(b)
                for b in content
                if not isinstance(b, dict) or b.get("type") == "text"
            ]
            return "".join(parts).strip()
    return ""


def _tool_names(messages: list[Any]) -> list[str]:
    names: list[str] = []
    for msg in messages:
        for call in getattr(msg, "tool_calls", None) or []:
            name = call.get("name") if isinstance(call, dict) else getattr(call, "name", None)
            if name:
                names.append(name)
    return names


def _tool_payloads(messages: list[Any]) -> list[dict[str, Any]]:
    """Conteúdo das ToolMessages, já como dict. Ignora o que não for JSON de objeto."""
    out: list[dict[str, Any]] = []
    for msg in messages:
        if not isinstance(msg, ToolMessage):
            continue
        content = msg.content
        if isinstance(content, list):  # blocos de conteúdo MCP
            content = "".join(
                b.get("text", "")
                for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            )
        if not isinstance(content, str):
            continue
        try:
            parsed = json.loads(content)
        except (ValueError, TypeError):
            continue
        if isinstance(parsed, dict):
            out.append(parsed)
    return out


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok" if _state.get("agent") else "starting"}


@app.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest) -> AskResponse:
    agent = _state.get("agent")
    settings: Settings | None = _state.get("settings")
    if agent is None or settings is None:
        raise HTTPException(status_code=503, detail="agente ainda inicializando")

    try:
        result = await agent.ainvoke({"messages": [("user", req.question)]})
    except Exception as exc:
        # superfície de API: qualquer falha vira 502, sem vazar stacktrace
        raise HTTPException(status_code=502, detail=f"falha ao consultar: {exc}") from exc

    messages = result.get("messages", [])
    answer = _final_text(messages)
    if not answer:
        raise HTTPException(status_code=502, detail="o agente não produziu resposta")
    return AskResponse(
        answer=answer,
        model=settings.model,
        tool_calls=_tool_names(messages),
        data=_tool_payloads(messages),
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
