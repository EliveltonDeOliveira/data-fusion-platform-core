"""Reforço determinístico da regra "nunca prescritivo".

O `system_prompt` já instrui os especialistas a recusar explicitamente pedido
de recomendação/orientação/decisão — mas depender só do LLM seguir essa
instrução é probabilístico, não determinístico (ver achado do eval ao vivo:
o mesmo tipo de pergunta às vezes passa batido). Este módulo detecta, por
regex sobre a PERGUNTA original (não a resposta), se ela pede recomendação; se
pedir e a resposta do especialista/síntese não trouxer recusa explícita,
prepende um aviso fixo. Determinístico-primeiro, LLM contido — mesmo padrão já
usado pros thresholds numéricos das tools.
"""

from __future__ import annotations

import re
import unicodedata

_ADVICE_RE = re.compile(
    r"\b(devo|deveria|vale a pena|compensa|convem|"
    r"e recomendavel|aconselh\w*|recomend[ao]|melhor "
    r"(investir|plantar|comprar|irrigar|manejar))\b"
)

_REFUSAL_MARKERS = (
    "informativo",
    "monitoramento",
    "nao recomend",
    "nao posso recomendar",
    "nao faco recomend",
    "nao e recomendacao",
)

_DISCLAIMER = (
    "Este serviço é só informativo e de monitoramento — não recomenda ação, manejo nem decisão. "
)


def _norm(text: str) -> str:
    stripped = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return stripped.lower()


def wants_recommendation(question: str) -> bool:
    return bool(_ADVICE_RE.search(_norm(question)))


def already_refuses(answer: str) -> bool:
    normalized = _norm(answer)
    return any(marker in normalized for marker in _REFUSAL_MARKERS)


def ensure_recommendation_refusal(question: str, answer: str) -> str:
    """Se a pergunta pede recomendação e a resposta não recusa, prepende o aviso."""
    if not answer.strip():
        return answer
    if not wants_recommendation(question):
        return answer
    if already_refuses(answer):
        return answer
    return _DISCLAIMER + answer
