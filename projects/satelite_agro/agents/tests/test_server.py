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


def test_ask_repassa_historico_pro_grafo():
    agent = StubAgent(_state_ok())
    client = _install(agent)
    r = client.post(
        "/ask",
        json={
            "question": "e em 2020?",
            "history": [
                {"role": "user", "content": "uso da terra em Santa Maria em 2019?"},
                {"role": "assistant", "content": "39% agricultura em 2019."},
            ],
        },
    )
    assert r.status_code == 200
    assert agent.last_inputs["history"] == [
        {"role": "user", "content": "uso da terra em Santa Maria em 2019?"},
        {"role": "assistant", "content": "39% agricultura em 2019."},
    ]


def test_ask_sem_historico_manda_lista_vazia():
    agent = StubAgent(_state_ok())
    client = _install(agent)
    r = client.post("/ask", json={"question": "temp em porto alegre?"})
    assert r.status_code == 200
    assert agent.last_inputs["history"] == []


def test_ask_historico_com_role_invalido_e_rejeitado():
    client = _install(StubAgent(_state_ok()))
    r = client.post(
        "/ask",
        json={"question": "oi", "history": [{"role": "sistema", "content": "x"}]},
    )
    assert r.status_code == 422


def test_ask_historico_alem_do_limite_e_rejeitado():
    client = _install(StubAgent(_state_ok()))
    historico = [{"role": "user", "content": f"pergunta {i}"} for i in range(13)]
    r = client.post("/ask", json={"question": "oi", "history": historico})
    assert r.status_code == 422


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


def test_nenhum_texto_livre_da_pergunta_ou_resposta_chega_ao_trace(monkeypatch):
    """Valida em código que o trace do MLflow nunca vê o texto literal da
    pergunta nem da resposta, só metadado estrutural (specialists/tool_calls/
    latência). Guarda contra regressão se algum dia alguém passar
    `req.question`/`result["answer"]` pra `trace.log_routing`."""
    from .test_observability import _FakeMlflowClient, _install_fake_mlflow

    pergunta_sentinela = "SENTINELA-PERGUNTA-xyz789: qual a temperatura em Bagé?"
    resposta_sentinela = "SENTINELA-RESPOSTA-abc123: 18,4 °C nos últimos 7 dias."

    client = _FakeMlflowClient(experiments={"satelite_agro": "exp-1"})
    _install_fake_mlflow(monkeypatch, client)

    state = {
        "answer": resposta_sentinela,
        "tool_calls": ["get_weather_trend"],
        "specialists": ["clima"],
        "data": [],
    }
    server._state["agent"] = StubAgent(state)
    server._state["settings"] = Settings(
        gemini_api_key="x",
        model="gemini-3.5-flash-lite",
        mlflow_tracking_uri="http://mlflow:5000",
    )

    r = TestClient(server.app).post("/ask", json={"question": pergunta_sentinela})
    assert r.status_code == 200
    assert r.json()["answer"] == resposta_sentinela  # a API continua devolvendo o texto pro usuário

    logado = repr(client.logged["tags"]) + repr(client.logged["metrics"])
    assert "SENTINELA-PERGUNTA" not in logado
    assert "SENTINELA-RESPOSTA" not in logado


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


class _FakeTool:
    """Espelha só o que `direct_tools.call_tool` usa de uma `BaseTool` do MCP:
    `ainvoke` devolvendo o payload como string JSON (mesmo formato que a tool
    real devolve através do `langchain_mcp_adapters`)."""

    def __init__(self, result: dict | None = None, *, raises: Exception | None = None):
        self._result = result
        self._raises = raises
        self.calls: list[dict] = []

    async def ainvoke(self, kwargs: dict) -> str:
        import json

        self.calls.append(kwargs)
        if self._raises is not None:
            raise self._raises
        return json.dumps(self._result)


def test_land_use_summary_repassa_o_payload_da_tool():
    tool = _FakeTool({"available": True, "region_query": "Porto Alegre", "classes": []})
    client = _install(StubAgent(_state_ok(), tools_by_name={"get_land_use_summary": tool}))
    r = client.get("/land_use/summary", params={"region": "Porto Alegre", "year": 2025, "level": 2})
    assert r.status_code == 200
    assert r.json() == {"available": True, "region_query": "Porto Alegre", "classes": []}
    assert tool.calls == [{"region": "Porto Alegre", "year": 2025, "level": 2}]


def test_land_use_at_point_repassa_o_payload_da_tool():
    tool = _FakeTool({"available": True, "label": "Soja"})
    client = _install(StubAgent(_state_ok(), tools_by_name={"get_land_use_at_point": tool}))
    r = client.get("/land_use/at_point", params={"lat": -30.03, "lon": -51.23})
    assert r.status_code == 200
    assert r.json()["label"] == "Soja"
    assert tool.calls == [{"lat": -30.03, "lon": -51.23, "year": 2025, "level": 2}]


def test_land_use_change_repassa_o_payload_da_tool():
    tool = _FakeTool({"available": True, "classes": []})
    client = _install(StubAgent(_state_ok(), tools_by_name={"get_land_use_change": tool}))
    r = client.get("/land_use/change", params={"region": "RS", "year_from": 2015, "year_to": 2025})
    assert r.status_code == 200
    assert tool.calls == [{"region": "RS", "year_from": 2015, "year_to": 2025, "level": 2}]


def test_land_use_timeseries_repassa_o_payload_da_tool():
    tool = _FakeTool({"available": True, "classes": [{"label": "Agricultura", "points": []}]})
    client = _install(StubAgent(_state_ok(), tools_by_name={"get_land_use_timeseries": tool}))
    r = client.get("/land_use/timeseries", params={"region": "RS"})
    assert r.status_code == 200
    assert tool.calls == [{"region": "RS", "level": 2}]


def test_land_use_raster_overlay_repassa_o_payload_da_tool():
    tool = _FakeTool({"available": True, "width": 4, "height": 4, "image_base64": "abc="})
    client = _install(StubAgent(_state_ok(), tools_by_name={"get_land_use_raster_overlay": tool}))
    r = client.get("/land_use/raster_overlay")
    assert r.status_code == 200
    assert r.json()["image_base64"] == "abc="
    assert tool.calls == [{"year": 2025, "max_dim": 1200}]


def test_land_use_sem_agente_pronto_503():
    client = TestClient(server.app)  # sem lifespan -> _state vazio
    r = client.get("/land_use/summary", params={"region": "RS"})
    assert r.status_code == 503


def test_land_use_tool_nao_carregada_503():
    client = _install(StubAgent(_state_ok(), tools_by_name={}))
    r = client.get("/land_use/summary", params={"region": "RS"})
    assert r.status_code == 503


def test_land_use_falha_da_tool_vira_502():
    tool = _FakeTool(raises=RuntimeError("postgres fora do ar"))
    client = _install(StubAgent(_state_ok(), tools_by_name={"get_land_use_summary": tool}))
    r = client.get("/land_use/summary", params={"region": "RS"})
    assert r.status_code == 502
    assert "postgres fora do ar" in r.json()["detail"]


def test_land_use_nunca_bate_no_ask_nem_no_in_flight():
    """Chamada direta (sem LLM) não deve mexer no contador usado pelo
    rodapé de rate limit da UI — não gasta cota do Gemini."""
    tool = _FakeTool({"available": True, "classes": []})
    client = _install(StubAgent(_state_ok(), tools_by_name={"get_land_use_summary": tool}))
    client.get("/land_use/summary", params={"region": "RS"})
    assert server._state.get("in_flight", 0) == 0


def test_region_point_repassa_o_payload_da_tool():
    tool = _FakeTool({"available": True, "location": {"latitude": -30.03, "longitude": -51.23}})
    client = _install(StubAgent(_state_ok(), tools_by_name={"resolve_region_point": tool}))
    r = client.get("/region/point", params={"query": "Porto Alegre"})
    assert r.status_code == 200
    assert r.json()["location"]["latitude"] == -30.03
    assert tool.calls == [{"region": "Porto Alegre"}]


def test_region_point_sem_agente_pronto_503():
    client = TestClient(server.app)  # sem lifespan -> _state vazio
    r = client.get("/region/point", params={"query": "RS"})
    assert r.status_code == 503


def test_weather_trend_repassa_o_payload_da_tool():
    tool = _FakeTool({"available": True, "region_query": "RS", "series": []})
    client = _install(StubAgent(_state_ok(), tools_by_name={"get_weather_trend": tool}))
    r = client.get("/weather/trend", params={"region": "RS", "period": "7d"})
    assert r.status_code == 200
    assert r.json()["available"] is True
    assert tool.calls == [{"region": "RS", "period": "7d", "granularity": "daily"}]


def test_weather_trend_repassa_variables_quando_informado():
    tool = _FakeTool({"available": True, "series": []})
    client = _install(StubAgent(_state_ok(), tools_by_name={"get_weather_trend": tool}))
    client.get(
        "/weather/trend",
        params={"region": "RS", "variables": "temperature, precipitation"},
    )
    assert tool.calls == [
        {
            "region": "RS",
            "period": "7d",
            "granularity": "daily",
            "variables": ["temperature", "precipitation"],
        }
    ]


def test_weather_trend_sem_agente_pronto_503():
    client = TestClient(server.app)  # sem lifespan -> _state vazio
    r = client.get("/weather/trend", params={"region": "RS"})
    assert r.status_code == 503


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
