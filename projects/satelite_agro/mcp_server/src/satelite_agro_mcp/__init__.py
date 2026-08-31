"""MCP server do Projeto 1 — Satélite + Agro/GIS.

Expõe tools de acesso a dado público: clima ao vivo (Open-Meteo) e uso/cobertura
da terra (MapBiomas Coleção 11, pré-agregado no banco local + raster do RS). O
raciocínio fica no agente; aqui só o acesso a dado, determinístico.
"""

from .land_use import (
    LandUsePoint,
    LandUseSummary,
    get_land_use_at_point,
    get_land_use_summary,
)
from .weather import WeatherTrend, get_weather_trend

__all__ = [
    "LandUsePoint",
    "LandUseSummary",
    "WeatherTrend",
    "get_land_use_at_point",
    "get_land_use_summary",
    "get_weather_trend",
]
