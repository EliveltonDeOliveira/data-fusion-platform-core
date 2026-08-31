"""Camada MCP: a tool `get_weather_trend` registrada e chamável via `MCPServer`.

Não sobe HTTP — usa `list_tools` / `call_tool` diretamente. A lógica de dado já
é coberta por `test_weather.py`; aqui só o contrato MCP (nome fixado, schema de
entrada, serialização da resposta).
"""

from __future__ import annotations

import json

from satelite_agro_mcp.server import mcp

from .samples import FORECAST_URL, PORTO_ALEGRE, SAO_PAULO, daily_forecast


def _payload(result) -> dict:
    if result.structured_content:
        return result.structured_content
    return json.loads(result.content[0].text)


async def test_tool_registrada_com_schema():
    tools = await mcp.list_tools()
    tool = next(t for t in tools if t.name == "get_weather_trend")
    props = tool.input_schema["properties"]
    assert set(props) == {"region", "period", "granularity", "variables"}
    assert props["region"]["type"] == "string"
    assert props["granularity"]["default"] == "daily"


async def test_call_tool_regiao_no_rs(geo, httpx_mock):
    geo(PORTO_ALEGRE)
    httpx_mock.add_response(url=FORECAST_URL, json=daily_forecast(7))

    result = await mcp.call_tool(
        "get_weather_trend",
        {"region": "Porto Alegre", "period": "7d", "variables": ["temperature"]},
    )

    assert not result.is_error
    data = _payload(result)
    assert data["available"] is True
    assert data["location"]["admin1"] == "Rio Grande do Sul"
    assert data["source"] == "open-meteo"
    assert any(s["measure"] == "temperature_2m_mean" for s in data["series"])


async def test_call_tool_fora_do_rs_nao_inventa(geo):
    geo(SAO_PAULO)
    result = await mcp.call_tool("get_weather_trend", {"region": "São Paulo"})

    assert not result.is_error
    data = _payload(result)
    assert data["available"] is False
    assert data["series"] == []
    assert any("fora do escopo" in n.lower() for n in data["notes"])
