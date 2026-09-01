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
