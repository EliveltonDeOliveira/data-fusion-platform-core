from __future__ import annotations

import pytest

from satelite_agro_agent.supervisor import Plan, plan


class _FakeStructured:
    def __init__(self, result):
        self._result = result

    async def ainvoke(self, _messages):
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class _FakeModel:
    def __init__(self, result):
        self._result = result

    def with_structured_output(self, schema):
        assert schema is Plan
        return _FakeStructured(self._result)


def test_plan_specialists_property():
    p = Plan(clima=True, uso_terra=False)
    assert p.specialists == ["clima"]
    p2 = Plan(clima=True, uso_terra=True)
    assert p2.specialists == ["clima", "uso_terra"]


def test_plan_question_for_usa_subpergunta_ou_fallback():
    p = Plan(clima=True, clima_q="e a chuva?")
    assert p.question_for("clima", "orig") == "e a chuva?"
    assert p.question_for("uso_terra", "orig") == "orig"


async def test_plan_roteia_um_especialista():
    model = _FakeModel(Plan(clima=True, uso_terra=False, clima_q="chuva no RS?"))
    out = await plan("Quanto choveu no RS?", model)
    assert out.specialists == ["clima"]
    assert out.clima_q == "chuva no RS?"


async def test_plan_roteia_dois_especialistas():
    model = _FakeModel(Plan(clima=True, uso_terra=True))
    out = await plan("clima e uso da terra em Santa Maria?", model)
    assert out.specialists == ["clima", "uso_terra"]


async def test_plan_roteia_metodologia():
    model = _FakeModel(Plan(metodologia=True, metodologia_q="como e definida a pastagem?"))
    out = await plan("como a MapBiomas define a classe pastagem?", model)
    assert out.specialists == ["metodologia"]
    assert out.metodologia_q == "como e definida a pastagem?"


async def test_plan_nenhum_especialista():
    model = _FakeModel(Plan())
    out = await plan("bom dia", model)
    assert out.specialists == []


@pytest.mark.parametrize("bad", [RuntimeError("api down"), "não é um Plan", None])
async def test_plan_fallback_quando_parse_falha(bad):
    model = _FakeModel(bad)
    out = await plan("pergunta qualquer", model)
    # fallback seguro: todos os especialistas, com a pergunta original
    assert out.specialists == ["clima", "uso_terra", "metodologia"]
    assert out.clima_q == "pergunta qualquer"
    assert out.uso_terra_q == "pergunta qualquer"
    assert out.metodologia_q == "pergunta qualquer"


class _RecordingStructured:
    def __init__(self, result, sink: list):
        self._result = result
        self._sink = sink

    async def ainvoke(self, messages):
        self._sink.append(messages)
        return self._result


class _RecordingModel:
    def __init__(self, result):
        self.sink: list = []
        self._result = result

    def with_structured_output(self, schema):
        assert schema is Plan
        return _RecordingStructured(self._result, self.sink)


async def test_plan_sem_historico_nao_manda_bloco_extra():
    model = _RecordingModel(Plan(clima=True))
    await plan("chove amanhã?", model)
    assert len(model.sink[0]) == 2  # só system (regras) + human (pergunta)


async def test_plan_com_historico_manda_bloco_de_contexto():
    plan_esperado = Plan(uso_terra=True, uso_terra_q="uso da terra em Santa Maria em 2020?")
    model = _RecordingModel(plan_esperado)
    historico = [
        {"role": "user", "content": "uso da terra em Santa Maria em 2019?"},
        {"role": "assistant", "content": "39% agricultura em 2019."},
    ]
    await plan("e em 2020?", model, history=historico)

    messages = model.sink[0]
    assert len(messages) == 3
    assert messages[-1] == ("human", "e em 2020?")
    bloco_historico = messages[1][1]
    assert "Santa Maria em 2019" in bloco_historico
    assert "39% agricultura" in bloco_historico


async def test_plan_historico_so_usa_os_ultimos_turnos():
    model = _RecordingModel(Plan(clima=True))
    historico = [{"role": "user", "content": f"pergunta {i}"} for i in range(10)]
    await plan("agora?", model, history=historico)

    bloco_historico = model.sink[0][1][1]
    assert "pergunta 0" not in bloco_historico  # fora da janela dos últimos 6
    assert "pergunta 9" in bloco_historico
