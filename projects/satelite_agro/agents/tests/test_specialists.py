from __future__ import annotations

from langchain_core.tools import tool

from satelite_agro_agent.agent import SYSTEM_PROMPT
from satelite_agro_agent.specialists import (
    CLIMA_TOOLS,
    METODOLOGIA_TOOLS,
    USO_TERRA_TOOLS,
    build_clima_specialist,
    build_metodologia_specialist,
    build_uso_terra_specialist,
)


@tool
def get_weather_trend(region: str) -> str:
    """clima."""
    return "{}"


@tool
def get_land_use_summary(region: str) -> str:
    """uso da terra."""
    return "{}"


@tool
def get_land_use_at_point(lat: float, lon: float) -> str:
    """ponto."""
    return "{}"


@tool
def get_land_use_change(region: str, year_from: int, year_to: int) -> str:
    """mudança."""
    return "{}"


@tool
def get_land_use_timeseries(region: str) -> str:
    """série histórica."""
    return "{}"


@tool
def search_mapbiomas_methodology(query: str) -> str:
    """metodologia."""
    return "{}"


_TOOLS = {
    t.name: t
    for t in (
        get_weather_trend,
        get_land_use_summary,
        get_land_use_at_point,
        get_land_use_change,
        get_land_use_timeseries,
        search_mapbiomas_methodology,
    )
}


class _FakeModel:
    """Só precisa existir — create_agent aceita um BaseChatModel; aqui um duck."""

    def bind_tools(self, *_a, **_k):
        return self

    def with_config(self, *_a, **_k):
        return self


def test_listas_de_tools_nao_se_cruzam():
    assert set(CLIMA_TOOLS).isdisjoint(USO_TERRA_TOOLS)
    assert set(CLIMA_TOOLS).isdisjoint(METODOLOGIA_TOOLS)
    assert set(USO_TERRA_TOOLS).isdisjoint(METODOLOGIA_TOOLS)
    assert "get_land_use_change" in USO_TERRA_TOOLS


def test_prompts_herdam_guardrails_e_tem_foco():
    from satelite_agro_agent import specialists

    assert SYSTEM_PROMPT in (SYSTEM_PROMPT + specialists._CLIMA_FOCO)
    assert "SEU FOCO" in specialists._CLIMA_FOCO
    assert "SEU FOCO" in specialists._USO_TERRA_FOCO
    assert "SEU FOCO" in specialists._METODOLOGIA_FOCO
    assert "get_land_use_change" in specialists._USO_TERRA_FOCO
    assert "get_land_use_timeseries" in specialists._USO_TERRA_FOCO
    assert "source_document" in specialists._METODOLOGIA_FOCO


def test_build_especialistas_seleciona_o_subconjunto(monkeypatch):
    captured = {}

    def fake_create_agent(model, tools, system_prompt):
        captured.setdefault("calls", []).append(
            {"tools": [t.name for t in tools], "prompt": system_prompt}
        )
        return ("agent", tools)

    monkeypatch.setattr("satelite_agro_agent.specialists.create_agent", fake_create_agent)

    build_clima_specialist(_FakeModel(), _TOOLS)
    build_uso_terra_specialist(_FakeModel(), _TOOLS)
    build_metodologia_specialist(_FakeModel(), _TOOLS)

    clima_call, uso_call, metodologia_call = captured["calls"]
    assert clima_call["tools"] == ["get_weather_trend"]
    assert set(uso_call["tools"]) == set(USO_TERRA_TOOLS)
    assert metodologia_call["tools"] == ["search_mapbiomas_methodology"]
    assert "monitoramento" in clima_call["prompt"]
