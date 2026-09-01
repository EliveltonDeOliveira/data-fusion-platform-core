"""Síntese: junta as sub-respostas de 2+ especialistas numa resposta só.

Só roda quando mais de um especialista respondeu (1 só -> a sub-resposta dele
já é a resposta final). Não introduz número novo: tudo que é objetivo já está
nas sub-respostas e nos payloads determinísticos das tools. Correlação é
apresentada como dado lado a lado, nunca como relação causal.
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel

from .agent import SYSTEM_PROMPT

_SYNTHESIS_FOCO = """\

VOCÊ ESTÁ COMPONDO: recebeu as respostas de especialistas diferentes sobre a \
mesma pergunta. Junte numa resposta única, coerente e direta.
- Não invente nem altere número: use só o que veio das sub-respostas.
- Se a pergunta pede relação entre clima e uso da terra, apresente os dois \
lados e deixe a leitura com quem perguntou. NUNCA afirme que um causou o outro \
(sem análise causal).
- Mantenha o tom informativo e de monitoramento; nada de recomendação."""


def _prompt(question: str, sub_answers: dict[str, str]) -> str:
    blocos = "\n\n".join(f"[{nome}]\n{texto}" for nome, texto in sub_answers.items())
    return f"Pergunta original:\n{question}\n\nRespostas dos especialistas:\n\n{blocos}"


async def synthesize(question: str, sub_answers: dict[str, str], model: BaseChatModel) -> str:
    result = await model.ainvoke(
        [
            ("system", SYSTEM_PROMPT + _SYNTHESIS_FOCO),
            ("human", _prompt(question, sub_answers)),
        ]
    )
    content = result.content
    if isinstance(content, str):
        return content.strip()
    parts = [
        b.get("text", "") if isinstance(b, dict) else str(b)
        for b in content
        if not isinstance(b, dict) or b.get("type") == "text"
    ]
    return "".join(parts).strip()
