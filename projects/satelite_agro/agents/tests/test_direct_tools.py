from __future__ import annotations

import json

import pytest

from satelite_agro_agent.direct_tools import ToolNotAvailableError, call_tool


class _FakeTool:
    def __init__(self, content):
        self._content = content
        self.calls: list[dict] = []

    async def ainvoke(self, kwargs: dict):
        self.calls.append(kwargs)
        return self._content


async def test_call_tool_devolve_o_payload_parseado():
    tool = _FakeTool(json.dumps({"available": True, "classes": []}))
    out = await call_tool({"get_land_use_summary": tool}, "get_land_use_summary", region="RS")
    assert out == {"available": True, "classes": []}
    assert tool.calls == [{"region": "RS"}]


async def test_call_tool_aceita_blocos_de_conteudo_mcp():
    """Formato alternativo que o MCP às vezes devolve — lista de blocos com type=text."""
    tool = _FakeTool([{"type": "text", "text": json.dumps({"available": True})}])
    out = await call_tool({"t": tool}, "t")
    assert out == {"available": True}


async def test_call_tool_levanta_erro_pra_tool_desconhecida():
    with pytest.raises(ToolNotAvailableError):
        await call_tool({}, "get_land_use_summary", region="RS")


async def test_call_tool_levanta_erro_pra_resposta_que_nao_e_json_de_objeto():
    tool = _FakeTool("não é json")
    with pytest.raises(ValueError, match="resposta inesperada"):
        await call_tool({"t": tool}, "t")
