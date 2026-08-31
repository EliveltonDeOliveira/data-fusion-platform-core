"""MCP server do Projeto 1 — Satélite + Agro/GIS.

Expõe tools de acesso a dado público (Open-Meteo ao vivo nesta fase). O
raciocínio fica no agente; aqui só o acesso a dado, determinístico.
"""

from .weather import WeatherTrend, get_weather_trend

__all__ = ["WeatherTrend", "get_weather_trend"]
