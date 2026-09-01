"""Especialistas: cada um é um agente ReAct (`create_agent`) com só o
subconjunto de tools do seu domínio e um foco por cima das regras comuns
(`SYSTEM_PROMPT`). Os guardrails (informativo, nunca prescritivo, todo número
vem de tool, honestidade sobre `available: false`) valem para todos.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from langchain.agents import create_agent
from langchain_core.tools import BaseTool

from .agent import SYSTEM_PROMPT

CLIMA_TOOLS = ("get_weather_trend",)
USO_TERRA_TOOLS = ("get_land_use_summary", "get_land_use_at_point", "get_land_use_change")

_RECUSA_FOCO = """\
Se a pergunta também pedir recomendação, orientação ou decisão (irrigar, \
plantar, comprar terra, manejar), NÃO ignore essa parte: comece a resposta \
recusando-a explicitamente (ex.: "este serviço é só informativo, não recomendo \
X") antes de apresentar o dado."""

_CLIMA_FOCO = f"""\

SEU FOCO: clima e solo (Open-Meteo). Responda só a parte de clima/solo da \
pergunta. Não comente uso da terra — outro especialista cuida disso. \
{_RECUSA_FOCO}"""

_USO_TERRA_FOCO = f"""\

SEU FOCO: uso e cobertura da terra (MapBiomas Coleção 11). Responda só a parte \
de uso da terra. Para variação entre dois anos use get_land_use_change. Não \
comente clima — outro especialista cuida disso. \
{_RECUSA_FOCO}"""


def _pick(tools: Mapping[str, BaseTool], names: tuple[str, ...]) -> list[BaseTool]:
    return [tools[n] for n in names if n in tools]


def build_clima_specialist(model: Any, tools: Mapping[str, BaseTool]) -> Any:
    return create_agent(model, _pick(tools, CLIMA_TOOLS), system_prompt=SYSTEM_PROMPT + _CLIMA_FOCO)


def build_uso_terra_specialist(model: Any, tools: Mapping[str, BaseTool]) -> Any:
    return create_agent(
        model, _pick(tools, USO_TERRA_TOOLS), system_prompt=SYSTEM_PROMPT + _USO_TERRA_FOCO
    )
