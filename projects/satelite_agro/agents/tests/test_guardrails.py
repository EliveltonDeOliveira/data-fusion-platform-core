from __future__ import annotations

import pytest

from satelite_agro_agent.guardrails import (
    already_refuses,
    ensure_recommendation_refusal,
    wants_recommendation,
)


@pytest.mark.parametrize(
    "question",
    [
        "A umidade do solo esta baixa? Devo irrigar a lavoura?",
        "Vale a pena comprar terra em Santa Maria para plantar soja?",
        "O que voce recomenda para essa area?",
        "Compensa investir nessa regiao para agricultura?",
    ],
)
def test_wants_recommendation_detecta_pedido(question: str):
    assert wants_recommendation(question)


@pytest.mark.parametrize(
    "question",
    [
        "Qual foi a temperatura media em Porto Alegre na ultima semana?",
        "Como a MapBiomas classifica a classe pastagem?",
        "Quanto choveu no Rio Grande do Sul nos ultimos 7 dias?",
    ],
)
def test_wants_recommendation_ignora_pergunta_de_dado(question: str):
    assert not wants_recommendation(question)


def test_already_refuses_reconhece_marcadores():
    assert already_refuses("Este serviço é informativo e não recomenda ação.")
    assert already_refuses("Aqui vale só o caráter de monitoramento.")
    assert not already_refuses("A área tem 178.020 hectares de agricultura.")


def test_ensure_recommendation_refusal_prepende_quando_falta():
    answer = "Em 2025, a área de agricultura foi de 63.933 ha."
    out = ensure_recommendation_refusal("Vale a pena comprar terra para soja?", answer)
    assert out != answer
    assert out.endswith(answer)
    assert already_refuses(out)


def test_ensure_recommendation_refusal_nao_duplica_quando_ja_recusa():
    answer = "Este serviço é informativo e não recomenda a compra. A área é de 63.933 ha."
    out = ensure_recommendation_refusal("Vale a pena comprar terra para soja?", answer)
    assert out == answer


def test_ensure_recommendation_refusal_nao_mexe_em_pergunta_de_dado():
    answer = "A temperatura média foi de 17 °C."
    out = ensure_recommendation_refusal("Qual a temperatura média em Porto Alegre?", answer)
    assert out == answer


def test_ensure_recommendation_refusal_resposta_vazia():
    assert ensure_recommendation_refusal("Devo irrigar?", "") == ""
