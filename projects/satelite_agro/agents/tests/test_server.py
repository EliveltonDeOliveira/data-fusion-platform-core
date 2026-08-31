from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from satelite_agro_agent import server
from satelite_agro_agent.config import Settings

from .conftest import StubAgent

_SETTINGS = Settings(gemini_api_key="x", model="gemini-3.5-flash-lite")


def _install(agent) -> TestClient:
    server._state["agent"] = agent
    server._state["settings"] = _SETTINGS
    return TestClient(server.app)


def _conversa_ok() -> list:
    return [
        HumanMessage(content="temperatura média em Porto Alegre?"),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "get_weather_trend",
                    "args": {"region": "Porto Alegre", "period": "7d"},
                    "id": "call-1",
                    "type": "tool_call",
                }
            ],
        ),
        ToolMessage(
            content='{"available": true, "region_query": "Porto Alegre", "summary": []}',
            tool_call_id="call-1",
        ),
        AIMessage(content="A temperatura média foi 17,0 °C nos últimos 7 dias."),
    ]


def test_ask_repassa_resposta_tools_e_dados():
    client = _install(StubAgent(_conversa_ok()))
    r = client.post("/ask", json={"question": "temp média em porto alegre nos últimos 7 dias?"})

    assert r.status_code == 200
    body = r.json()
    assert "17,0 °C" in body["answer"]
    assert body["tool_calls"] == ["get_weather_trend"]
    assert body["model"] == "gemini-3.5-flash-lite"
    assert body["data"] == [{"available": True, "region_query": "Porto Alegre", "summary": []}]


def test_ask_data_vazio_sem_toolmessage():
    client = _install(StubAgent([AIMessage(content="Sem escopo para previsão.")]))
    r = client.post("/ask", json={"question": "previsão?"})
    assert r.status_code == 200
    assert r.json()["data"] == []


def test_ask_resposta_em_blocos_gemini():
    msgs = [AIMessage(content=[{"type": "text", "text": "Choveu 12 mm."}])]
    client = _install(StubAgent(msgs))
    r = client.post("/ask", json={"question": "choveu quanto?"})
    assert r.status_code == 200
    assert r.json()["answer"] == "Choveu 12 mm."


def test_ask_sem_agente_pronto_503():
    client = TestClient(server.app)  # sem lifespan → _state vazio
    r = client.post("/ask", json={"question": "oi"})
    assert r.status_code == 503


def test_ask_falha_do_agente_vira_502():
    client = _install(StubAgent(raises=RuntimeError("boom")))
    r = client.post("/ask", json={"question": "oi"})
    assert r.status_code == 502
    assert "boom" in r.json()["detail"]


def test_ask_resposta_vazia_502():
    client = _install(StubAgent([AIMessage(content="")]))
    r = client.post("/ask", json={"question": "oi"})
    assert r.status_code == 502


def test_ask_valida_pergunta():
    client = _install(StubAgent(_conversa_ok()))
    assert client.post("/ask", json={"question": ""}).status_code == 422
    assert client.post("/ask", json={}).status_code == 422


def test_healthz():
    client = _install(StubAgent(_conversa_ok()))
    assert client.get("/healthz").json() == {"status": "ok"}

    server._state.clear()
    assert TestClient(server.app).get("/healthz").json() == {"status": "starting"}


# --------------------------------------------------------------------------- #
# ponta a ponta real: Gemini + MCP server (rodar com: pytest -m live)


@pytest.mark.live
async def test_live_pergunta_ancora():
    from satelite_agro_agent.agent import build_agent

    settings = Settings.from_env()
    agent = await build_agent(settings)
    out = await agent.ainvoke(
        {"messages": [("user", "Qual foi a temperatura média em Porto Alegre na última semana?")]}
    )
    final = out["messages"][-1]
    assert isinstance(final, AIMessage) and final.content
    called = [c["name"] for m in out["messages"] for c in (getattr(m, "tool_calls", None) or [])]
    assert "get_weather_trend" in called
