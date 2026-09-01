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


async def test_land_use_tools_registradas_com_schema():
    tools = {t.name: t for t in await mcp.list_tools()}

    summary = tools["get_land_use_summary"]
    assert set(summary.input_schema["properties"]) == {"region", "year", "level"}
    assert summary.input_schema["properties"]["level"]["default"] == 2

    point = tools["get_land_use_at_point"]
    assert set(point.input_schema["properties"]) == {"lat", "lon", "year", "level"}
    assert point.input_schema["properties"]["year"]["default"] == 2025

    change = tools["get_land_use_change"]
    assert set(change.input_schema["properties"]) == {
        "region",
        "year_from",
        "year_to",
        "level",
    }
    assert change.input_schema["properties"]["level"]["default"] == 2

    timeseries = tools["get_land_use_timeseries"]
    assert set(timeseries.input_schema["properties"]) == {"region", "level"}
    assert timeseries.input_schema["properties"]["level"]["default"] == 2


async def test_land_use_sem_banco_nao_quebra(monkeypatch):
    # sem DATABASE_URL no ambiente -> a tool responde available=false com a
    # explicação em notes, nunca um erro de protocolo nem um número.
    monkeypatch.delenv("DATABASE_URL", raising=False)
    result = await mcp.call_tool("get_land_use_summary", {"region": "Santa Maria"})

    assert not result.is_error
    data = _payload(result)
    assert data["available"] is False
    assert data["classes"] == []
    assert data["notes"]


async def test_land_use_change_sem_banco_nao_quebra(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    result = await mcp.call_tool(
        "get_land_use_change",
        {"region": "Santa Maria", "year_from": 1990, "year_to": 2020},
    )

    assert not result.is_error
    data = _payload(result)
    assert data["available"] is False
    assert data["classes"] == []


async def test_land_use_timeseries_sem_banco_nao_quebra(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    result = await mcp.call_tool("get_land_use_timeseries", {"region": "Santa Maria"})

    assert not result.is_error
    data = _payload(result)
    assert data["available"] is False
    assert data["classes"] == []
    assert data["notes"]


async def test_land_use_raster_overlay_tool_registrada_com_schema():
    tools = {t.name: t for t in await mcp.list_tools()}
    tool = tools["get_land_use_raster_overlay"]
    assert set(tool.input_schema["properties"]) == {"year", "max_dim"}
    assert tool.input_schema["properties"]["year"]["default"] == 2025
    assert tool.input_schema["properties"]["max_dim"]["default"] == 1200


async def test_land_use_raster_overlay_sem_raster_nao_quebra(monkeypatch):
    monkeypatch.delenv("RS_COVERAGE_RASTER", raising=False)
    result = await mcp.call_tool("get_land_use_raster_overlay", {})

    assert not result.is_error
    data = _payload(result)
    assert data["available"] is False
    assert data["image_base64"] is None
    assert data["notes"]


async def test_resolve_region_point_tool_registrada_com_schema():
    tools = {t.name: t for t in await mcp.list_tools()}
    tool = tools["resolve_region_point"]
    assert set(tool.input_schema["properties"]) == {"region"}


async def test_resolve_region_point_tool_devolve_lat_lon(geo):
    geo(PORTO_ALEGRE)
    result = await mcp.call_tool("resolve_region_point", {"region": "Porto Alegre"})

    assert not result.is_error
    data = _payload(result)
    assert data["available"] is True
    assert abs(data["location"]["latitude"] + 30.03306) < 1e-6
