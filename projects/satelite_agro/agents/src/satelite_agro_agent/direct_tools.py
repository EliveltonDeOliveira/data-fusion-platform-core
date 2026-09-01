"""Chamada direta de tools MCP determinísticas, sem passar pelo LLM/grafo.

Usado pelos endpoints REST de dado estruturado (`/land_use/*`): a UI precisa
de filtro interativo (região/ano/nível) com resposta instantânea, e cada tool
já é uma consulta determinística no Postgres — rotear isso pelo Supervisor
custaria cota do Gemini e alguns segundos de latência à toa. Reusa as tools
já carregadas no startup do grafo (`graph.tools_by_name`); não abre conexão
nova nem duplica o client MCP.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .messages import parse_tool_content

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool


class ToolNotAvailableError(Exception):
    """A tool esperada não foi carregada do MCP server (agente ainda subindo, ou nome errado)."""


async def call_tool(tools_by_name: dict[str, BaseTool], name: str, **kwargs: Any) -> dict[str, Any]:
    tool = tools_by_name.get(name)
    if tool is None:
        raise ToolNotAvailableError(name)
    raw = await tool.ainvoke(kwargs)
    parsed = parse_tool_content(raw)
    if parsed is None:
        raise ValueError(f"resposta inesperada da tool {name}: {raw!r}")
    return parsed
