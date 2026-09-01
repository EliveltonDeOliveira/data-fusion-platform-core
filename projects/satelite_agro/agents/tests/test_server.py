from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from satelite_agro_agent import server
from satelite_agro_agent.config import Settings

from .conftest import StubAgent

_SETTINGS = Settings(gemini_api_key="x", model="gemini-3.5-flash-lite")


def _install(agent) -> TestClient:
    server._state["agent"] = agent
    server._state["settings"] = _SETTINGS
    return TestClient(server.app)


def _state_ok() -> dict:
    return {
        "answer": "A temperatura média foi 17,0 °C nos últimos 7 dias.",
        "tool_calls": ["get_weather_trend"],
        "specialists": ["clima"],
        "data": [{"available": True, "region_query": "Porto Alegre", "summary": []}],
    }


def test_ask_repassa_resposta_tools_e_dados():
    client = _install(StubAgent(_state_ok()))
    r = client.post("/ask", json={"question": "temp média em porto alegre nos últimos 7 dias?"})

    assert r.status_code == 200
    body = r.json()
    assert "17,0 °C" in body["answer"]
    assert body["tool_calls"] == ["get_weather_trend"]
    assert body["specialists"] == ["clima"]
    assert body["model"] == "gemini-3.5-flash-lite"
    assert body["data"] == [{"available": True, "region_query": "Porto Alegre", "summary": []}]


def test_ask_correlacao_dois_especialistas():
    state = {
        "answer": "Clima: 17 °C. Uso da terra: 40% agricultura.",
        "tool_calls": ["get_weather_trend", "get_land_use_summary"],
        "specialists": ["clima", "uso_terra"],
        "data": [{"available": True}, {"available": True}],
    }
    client = _install(StubAgent(state))
    r = client.post("/ask", json={"question": "clima e uso da terra em santa maria?"})
    assert r.status_code == 200
    assert r.json()["specialists"] == ["clima", "uso_terra"]
    assert len(r.json()["data"]) == 2


def test_ask_data_vazio():
    client = _install(StubAgent({"answer": "Reformule a pergunta.", "specialists": []}))
    r = client.post("/ask", json={"question": "oi"})
    assert r.status_code == 200
    assert r.json()["data"] == []
    assert r.json()["specialists"] == []


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
    client = _install(StubAgent({"answer": "", "specialists": ["clima"]}))
    r = client.post("/ask", json={"question": "oi"})
    assert r.status_code == 502


def test_ask_valida_pergunta():
    client = _install(StubAgent(_state_ok()))
    assert client.post("/ask", json={"question": ""}).status_code == 422
    assert client.post("/ask", json={}).status_code == 422


def test_healthz():
    client = _install(StubAgent(_state_ok()))
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
        {"question": "Qual foi a temperatura média em Porto Alegre na última semana?"}
    )
    assert isinstance(out.get("answer"), str) and out["answer"]
    assert "get_weather_trend" in (out.get("tool_calls") or [])
    assert out.get("specialists") == ["clima"]


@pytest.mark.live
async def test_live_correlacao_dois_especialistas():
    from satelite_agro_agent.agent import build_agent

    settings = Settings.from_env()
    agent = await build_agent(settings)
    out = await agent.ainvoke(
        {
            "question": (
                "Como o clima recente e a composição de uso da terra se "
                "relacionam no município de Santa Maria?"
            )
        }
    )
    assert set(out.get("specialists") or []) == {"clima", "uso_terra"}
    assert isinstance(out.get("answer"), str) and out["answer"]
