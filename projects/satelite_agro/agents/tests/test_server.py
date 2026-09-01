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


def test_status_sem_agente_pronto():
    client = TestClient(server.app)  # sem lifespan -> _state vazio
    r = client.get("/status")
    assert r.status_code == 200
    assert r.json() == {"ready": False, "in_flight": 0, "models": {}}


def test_status_sem_model_pool_no_agente():
    client = _install(StubAgent(_state_ok()))  # StubAgent sem model_pool
    r = client.get("/status")
    assert r.json() == {"ready": False, "in_flight": 0, "models": {}}


def test_status_repassa_stats_do_pool():
    class _FakePool:
        def stats(self):
            from satelite_agro_agent.status import ModelStatus

            return {
                "gemini-3.5-flash-lite": ModelStatus(max_rpm=10, waiting=0),
                "gemini-3.1-flash-lite": ModelStatus(max_rpm=10, waiting=2),
            }

    client = _install(StubAgent(_state_ok(), model_pool=_FakePool()))
    r = client.get("/status")
    assert r.status_code == 200
    body = r.json()
    assert body["ready"] is True
    assert body["in_flight"] == 0
    assert body["models"]["gemini-3.1-flash-lite"] == {"max_rpm": 10, "waiting": 2}
    assert body["models"]["gemini-3.5-flash-lite"] == {"max_rpm": 10, "waiting": 0}


async def test_in_flight_conta_enquanto_o_agente_processa_e_zera_no_final():
    """Reproduz o achado do dono: o widget só devia mudar DURANTE o
    processamento, não só depois que a resposta chega. `in_flight` cobre o
    início ao fim de `agent.ainvoke`, não só o tempo bloqueado no rate
    limiter (que é o que `models[*].waiting` mede)."""
    import asyncio

    import httpx

    ready = asyncio.Event()
    release = asyncio.Event()

    class _SlowAgent(StubAgent):
        async def ainvoke(self, inputs):
            ready.set()
            await release.wait()
            return await super().ainvoke(inputs)

    server._state["agent"] = _SlowAgent(_state_ok())
    server._state["settings"] = _SETTINGS

    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        task = asyncio.create_task(client.post("/ask", json={"question": "oi"}))
        await asyncio.wait_for(ready.wait(), timeout=1)

        mid = await client.get("/status")
        assert mid.json()["in_flight"] == 1

        release.set()
        resp = await task
        assert resp.status_code == 200

        after = await client.get("/status")
        assert after.json()["in_flight"] == 0


async def test_in_flight_zera_mesmo_quando_o_agente_falha():
    client = _install(StubAgent(raises=RuntimeError("boom")))
    r = client.post("/ask", json={"question": "oi"})
    assert r.status_code == 502
    assert client.get("/status").json()["in_flight"] == 0


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
