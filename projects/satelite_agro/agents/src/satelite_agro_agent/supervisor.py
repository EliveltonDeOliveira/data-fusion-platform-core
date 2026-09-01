"""Supervisor: decide quais especialistas a pergunta precisa e reescreve a
sub-pergunta de cada um. Uma chamada de LLM com saída estruturada.

Não responde à pergunta nem toca em número — só roteia. Se o parse falhar,
cai no padrão seguro: manda para os dois especialistas com a pergunta original.
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field

SPECIALISTS = ("clima", "uso_terra", "metodologia")

_PLANNER_PROMPT = """\
Você roteia uma pergunta para especialistas de dado público do Rio Grande do Sul.
NÃO responda à pergunta. Só decida quem precisa agir.

Especialistas:
- clima: tempo, temperatura, chuva, umidade e temperatura do solo, \
evapotranspiração. Dado atual e histórico (Open-Meteo). Nunca previsão.
- uso_terra: composição e mudança de uso e cobertura da terra por área \
(MapBiomas, anual 1985-2025) — agricultura, pastagem, floresta, campo, área \
urbana, água etc., inclusive variação entre dois anos.
- metodologia: como a MapBiomas classifica cada classe, critério usado, \
avaliação de acurácia/confiabilidade do dado — pergunta sobre o MÉTODO, não \
sobre um número de uma região. Ex.: "como é definida a classe pastagem?", \
"quão confiável é esse mapeamento?".

Regras:
- Marque `clima` e/ou `uso_terra` e/ou `metodologia` conforme a pergunta.
- Se a pergunta relaciona duas ou mais dimensões (ex.: "como o clima recente se \
compara ao uso da terra"), marque todas as que se aplicam.
- Se não toca nenhuma (saudação, pergunta sobre o próprio serviço, tema fora de \
clima, uso da terra e metodologia), não marque nenhuma.
- Para cada especialista marcado, escreva em `*_q` a sub-pergunta focada na \
parte de dado que é dele, mantendo região e período da pergunta original.
- Se a pergunta original também pedir recomendação, orientação ou decisão \
(irrigar, plantar, comprar terra, manejar), mantenha esse pedido na \
sub-pergunta tal como foi feito — NÃO remova e NÃO responda a ele aqui; o \
especialista vai recusá-lo explicitamente.
- Pode vir um histórico recente da conversa, só de contexto. Se a pergunta \
atual depender dele (ex.: "e em 2020?", "e a chuva na mesma semana?", "e em \
Santa Maria?"), use o histórico só para completar região/período/tema que \
ficaram implícitos — escreva cada `*_q` já completa e autocontida, sem \
"isso"/"aquilo"/"lá". Nunca responda ao histórico, só à pergunta atual.
"""

_MAX_HISTORY_TURNS = 6


class Plan(BaseModel):
    clima: bool = Field(default=False, description="a pergunta precisa do especialista de clima")
    uso_terra: bool = Field(
        default=False, description="a pergunta precisa do especialista de uso da terra"
    )
    metodologia: bool = Field(
        default=False, description="a pergunta precisa do especialista de metodologia MapBiomas"
    )
    clima_q: str | None = Field(default=None, description="sub-pergunta focada só no clima")
    uso_terra_q: str | None = Field(
        default=None, description="sub-pergunta focada só no uso da terra"
    )
    metodologia_q: str | None = Field(
        default=None, description="sub-pergunta focada só na metodologia"
    )
    rationale: str = Field(default="", description="uma frase sobre a decisão de roteamento")

    @property
    def specialists(self) -> list[str]:
        return [name for name in SPECIALISTS if getattr(self, name)]

    def question_for(self, specialist: str, fallback: str) -> str:
        return getattr(self, f"{specialist}_q", None) or fallback


def _fallback_plan(question: str) -> Plan:
    return Plan(
        clima=True,
        uso_terra=True,
        metodologia=True,
        clima_q=question,
        uso_terra_q=question,
        metodologia_q=question,
        rationale="fallback",
    )


def _format_history(history: list[dict[str, str]] | None) -> str:
    if not history:
        return ""
    linhas = []
    for turno in history[-_MAX_HISTORY_TURNS:]:
        papel = "Usuário" if turno.get("role") == "user" else "Assistente"
        conteudo = (turno.get("content") or "").strip()
        if conteudo:
            linhas.append(f"{papel}: {conteudo}")
    return "\n".join(linhas)


async def plan(
    question: str, model: BaseChatModel, *, history: list[dict[str, str]] | None = None
) -> Plan:
    """Roteia `question`. Erro/saída vazia -> fallback para os dois especialistas.

    `history` é só contexto pra resolver referência da pergunta atual (ver
    regra no prompt) — nunca persistido aqui, vem do cliente a cada chamada.
    """
    try:
        structured = model.with_structured_output(Plan)
        messages: list[tuple[str, str]] = [("system", _PLANNER_PROMPT)]
        historico = _format_history(history)
        if historico:
            messages.append(("system", "Histórico recente da conversa:\n" + historico))
        messages.append(("human", question))
        result = await structured.ainvoke(messages)
    except Exception:  # noqa: BLE001 - qualquer falha de LLM/parse cai no fallback seguro
        return _fallback_plan(question)
    if not isinstance(result, Plan):
        return _fallback_plan(question)
    return result
