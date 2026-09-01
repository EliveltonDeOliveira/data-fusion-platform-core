from __future__ import annotations

import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from satelite_agro_agent.config import Settings
from satelite_agro_agent.graph import build_graph
from satelite_agro_agent.supervisor import Plan

_SETTINGS = Settings(gemini_api_key="k")


class _FakeSpecialist:
    """Devolve messages fixas e registra a sub-pergunta recebida."""

    def __init__(self, tool_name: str, payload: dict, answer: str):
        self._tool_name = tool_name
        self._payload = payload
        self._answer = answer
        self.seen: list[str] = []

    async def ainvoke(self, inputs: dict) -> dict:
        q = inputs["messages"][0][1]
        self.seen.append(q)
        return {
            "messages": [
                HumanMessage(content=q),
                AIMessage(
                    content="",
                    tool_calls=[
                        {"name": self._tool_name, "args": {}, "id": "c1", "type": "tool_call"}
                    ],
                ),
                ToolMessage(content=json.dumps(self._payload), tool_call_id="c1"),
                AIMessage(content=self._answer),
            ]
        }


def _clima() -> _FakeSpecialist:
    return _FakeSpecialist(
        "get_weather_trend", {"available": True, "region_query": "x"}, "17 graus"
    )


def _uso() -> _FakeSpecialist:
    return _FakeSpecialist("get_land_use_summary", {"available": True, "classes": []}, "40% agri")


def _metodologia() -> _FakeSpecialist:
    return _FakeSpecialist(
        "search_mapbiomas_methodology",
        {"available": True, "chunks": []},
        "pastagem é definida por...",
    )


async def _graph(plan_obj: Plan, *, clima=None, uso=None, metodologia=None, synth=None):
    clima = clima or _clima()
    uso = uso or _uso()
    metodologia = metodologia or _metodologia()
    calls: list = []

    async def synthesizer(question, sub_answers):
        calls.append((question, sub_answers))
        return synth or "sintese: 17 graus e 40% agri"

    async def planner(_q, _h=None):
        return plan_obj

    graph = await build_graph(
        _SETTINGS,
        planner=planner,
        clima_agent=clima,
        uso_terra_agent=uso,
        metodologia_agent=metodologia,
        synthesizer=synthesizer,
    )
    return graph, clima, uso, metodologia, calls


async def test_um_especialista_nao_chama_sintese():
    graph, clima, uso, metodologia, calls = await _graph(Plan(clima=True, clima_q="chuva no RS?"))
    out = await graph.ainvoke({"question": "Quanto choveu no RS?"})

    assert out["specialists"] == ["clima"]
    assert out["answer"] == "17 graus"  # sub-resposta direta
    assert calls == []  # síntese não rodou
    assert clima.seen == ["chuva no RS?"]  # sub-pergunta do plano
    assert uso.seen == []
    assert metodologia.seen == []
    assert out["tool_calls"] == ["get_weather_trend"]
    assert out["data"] == [{"available": True, "region_query": "x"}]


async def test_dois_especialistas_rodam_e_sintese_compoe():
    graph, *_, calls = await _graph(Plan(clima=True, uso_terra=True))
    out = await graph.ainvoke({"question": "clima e uso da terra em Santa Maria?"})

    assert set(out["specialists"]) == {"clima", "uso_terra"}
    assert len(calls) == 1
    _, sub_answers = calls[0]
    assert set(sub_answers) == {"clima", "uso_terra"}
    assert out["answer"].startswith("sintese:")
    assert set(out["tool_calls"]) == {"get_weather_trend", "get_land_use_summary"}
    assert len(out["data"]) == 2


async def test_tres_especialistas_rodam_e_sintese_compoe():
    graph, *_, calls = await _graph(Plan(clima=True, uso_terra=True, metodologia=True))
    out = await graph.ainvoke({"question": "clima, uso da terra e metodologia?"})

    assert set(out["specialists"]) == {"clima", "uso_terra", "metodologia"}
    assert len(calls) == 1
    _, sub_answers = calls[0]
    assert set(sub_answers) == {"clima", "uso_terra", "metodologia"}


async def test_nenhum_especialista_responde_direto():
    graph, clima, uso, metodologia, calls = await _graph(Plan())
    out = await graph.ainvoke({"question": "bom dia"})

    assert out["specialists"] == []
    assert "monitoramento" in out["answer"]
    assert calls == []
    assert clima.seen == [] and uso.seen == [] and metodologia.seen == []


async def test_uso_terra_sozinho_usa_subpergunta():
    graph, _clima, uso, _metodologia, _calls = await _graph(
        Plan(uso_terra=True, uso_terra_q="uso da terra em Santa Maria em 2020?")
    )
    out = await graph.ainvoke({"question": "algo mais amplo"})

    assert out["specialists"] == ["uso_terra"]
    assert uso.seen == ["uso da terra em Santa Maria em 2020?"]
    assert out["answer"] == "40% agri"


async def test_metodologia_sozinho_usa_subpergunta():
    graph, *_ = await _graph(
        Plan(metodologia=True, metodologia_q="como e definida a classe pastagem?")
    )
    out = await graph.ainvoke({"question": "algo mais amplo"})

    assert out["specialists"] == ["metodologia"]
    assert out["tool_calls"] == ["search_mapbiomas_methodology"]


async def test_recusa_de_recomendacao_e_reforcada_mesmo_se_o_especialista_esquecer():
    esquecido = _FakeSpecialist(
        "get_land_use_summary", {"available": True, "classes": []}, "40% agricultura, sem mais."
    )
    graph, *_ = await _graph(
        Plan(uso_terra=True, uso_terra_q="vale a pena comprar terra para soja?"), uso=esquecido
    )
    out = await graph.ainvoke({"question": "Vale a pena comprar terra em Santa Maria para soja?"})
    assert "informativo" in out["answer"].lower() or "monitoramento" in out["answer"].lower()
    assert out["answer"].endswith("40% agricultura, sem mais.")


async def test_role_models_exposto_no_grafo():
    graph, *_ = await _graph(Plan(clima=True))
    assert set(graph.role_models) == {
        "supervisor",
        "clima",
        "uso_terra",
        "metodologia",
        "synthesis",
    }


async def test_tools_by_name_vazio_quando_agentes_sao_injetados():
    """Nos testes acima, os 3 especialistas são injetados — o grafo nunca
    carrega tools do MCP, então `tools_by_name` fica vazio (não None)."""
    graph, *_ = await _graph(Plan(clima=True))
    assert graph.tools_by_name == {}


async def test_historico_da_conversa_chega_ao_planner():
    """O histórico mandado pelo cliente vai pro Supervisor (que decide o
    roteamento), pra resolver referência tipo "e em 2020?"."""
    recebido: list = []

    async def planner(question, history=None):
        recebido.append((question, history))
        return Plan(uso_terra=True)

    graph = await build_graph(
        _SETTINGS,
        planner=planner,
        clima_agent=_clima(),
        uso_terra_agent=_uso(),
        metodologia_agent=_metodologia(),
        synthesizer=lambda *_a: "sintese",
    )
    historico = [
        {"role": "user", "content": "uso da terra em Santa Maria em 2019?"},
        {"role": "assistant", "content": "39% agricultura em 2019."},
    ]
    await graph.ainvoke({"question": "e em 2020?", "history": historico})

    assert recebido == [("e em 2020?", historico)]


async def test_sem_historico_planner_recebe_none():
    async def planner(question, history=None):
        assert history is None
        return Plan(clima=True)

    graph = await build_graph(
        _SETTINGS,
        planner=planner,
        clima_agent=_clima(),
        uso_terra_agent=_uso(),
        metodologia_agent=_metodologia(),
        synthesizer=lambda *_a: "sintese",
    )
    out = await graph.ainvoke({"question": "chove amanhã?"})
    assert out["specialists"] == ["clima"]


async def test_guardrail_pega_pedido_de_recomendacao_de_turno_anterior():
    """Pedido de recomendação feito num turno ANTERIOR ("vale a pena X?") não
    pode passar batido só porque a pergunta atual, sozinha, parece neutra."""
    esquecido = _FakeSpecialist(
        "get_land_use_summary", {"available": True, "classes": []}, "39% agricultura em 2019."
    )
    graph, *_ = await _graph(
        Plan(uso_terra=True, uso_terra_q="uso da terra em Santa Maria em 2020?"), uso=esquecido
    )
    historico = [
        {"role": "user", "content": "vale a pena comprar terra em Santa Maria para soja?"},
        {"role": "assistant", "content": "Este serviço é só informativo."},
    ]
    out = await graph.ainvoke({"question": "e em 2020?", "history": historico})
    assert "informativo" in out["answer"].lower() or "monitoramento" in out["answer"].lower()


async def test_tools_by_name_exposto_quando_tools_sao_passadas():
    """Usado pelos endpoints REST diretos (`/land_use/*`, ver direct_tools.py)
    pra chamar uma tool sem passar pelo LLM."""

    class _FakeTool:
        def __init__(self, name: str):
            self.name = name

    fake_tools = [_FakeTool("get_land_use_summary"), _FakeTool("get_weather_trend")]

    async def synthesizer(question, sub_answers):
        return "sintese"

    async def planner(_q, _h=None):
        return Plan(clima=True)

    graph = await build_graph(
        _SETTINGS,
        planner=planner,
        clima_agent=_clima(),
        uso_terra_agent=_uso(),
        metodologia_agent=_metodologia(),
        synthesizer=synthesizer,
        tools=fake_tools,
    )
    assert set(graph.tools_by_name) == {"get_land_use_summary", "get_weather_trend"}


@pytest.mark.parametrize(
    "plan_obj,expected",
    [
        (Plan(clima=True), ["clima"]),
        (Plan(uso_terra=True), ["uso_terra"]),
        (Plan(metodologia=True), ["metodologia"]),
        (Plan(clima=True, uso_terra=True), ["clima", "uso_terra"]),
        (Plan(), []),
    ],
)
async def test_roteamento_bate_com_o_plano(plan_obj, expected):
    graph, *_ = await _graph(plan_obj)
    out = await graph.ainvoke({"question": "q"})
    assert sorted(out["specialists"]) == sorted(expected)
