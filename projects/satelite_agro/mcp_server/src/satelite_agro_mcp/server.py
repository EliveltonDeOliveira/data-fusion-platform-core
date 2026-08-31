"""Entrypoint do MCP server — expõe as tools via streamable HTTP.

Endpoint de acesso a dado, determinístico e sem sessão: cada chamada é
independente e a única memória é o cache curto (ver `cache.py`). O raciocínio
fica no agente. Host/porta e cache são configuráveis por ambiente.
"""

from __future__ import annotations

import os

from mcp.server.mcpserver import MCPServer
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse

from . import weather
from .cache import Cache
from .weather import Granularity

mcp = MCPServer(
    "satelite-agro",
    instructions=(
        "Tools de dado público sobre o Rio Grande do Sul (escopo piloto). "
        "Informativo/monitoramento: entregam dado, contexto e tendência, nunca "
        "recomendação. Repasse ao usuário as mensagens do campo `notes`."
    ),
)

_cache = Cache.from_env()

_WEATHER_TREND_DESC = """\
Série climática atual/recente de uma região do Rio Grande do Sul (escopo piloto).
Fonte: Open-Meteo ao vivo — só dado atual e histórico, nunca previsão do futuro.
Determinístico, sem LLM. Informativo: entrega dado + tendência, nunca recomendação.

Parâmetros:
- region: município do RS ("Porto Alegre", "Santa Maria") ou o estado ("RS",
  "Rio Grande do Sul"). Fora do RS -> available=false com a explicação em notes,
  sem número inventado. Nível de estado usa um ponto representativo (centroide),
  não média por área.
- period: "now" (leitura horária mais recente), "7d" / "30d" (dias para trás), ou
  intervalo ISO "2026-08-01/2026-08-10". Padrão "7d".
- granularity: "daily" (padrão) ou "hourly". soil_moisture e soil_temperature só
  existem em "hourly"; "now" força horário.
- variables: subconjunto de ["temperature", "precipitation", "evapotranspiration",
  "soil_moisture", "soil_temperature"]. Omitido -> todas. Nome desconhecido é
  ignorado com aviso em notes.

Retorno: available, location (ponto usado e se é centroide do estado), period,
current (só em modo "now"), series, summary (média/mín/máx/total por variável) e
notes. Sempre repasse as notes ao usuário."""


@mcp.tool(name="get_weather_trend", description=_WEATHER_TREND_DESC)
async def get_weather_trend(
    region: str,
    period: str = "7d",
    granularity: Granularity = "daily",
    variables: list[str] | None = None,
) -> dict:
    """Adapta `weather.get_weather_trend` para a camada MCP. Ver `_WEATHER_TREND_DESC`."""
    result = await weather.get_weather_trend(
        region,
        period,
        granularity,
        variables,
        cache=_cache,
    )
    return result.model_dump(mode="json")


@mcp.custom_route("/healthz", methods=["GET"], include_in_schema=False)
async def healthz(_request: Request) -> PlainTextResponse:
    return PlainTextResponse("ok")


@mcp.custom_route("/", methods=["GET"], include_in_schema=False)
async def root(_request: Request) -> JSONResponse:
    return JSONResponse({"service": "satelite-agro-mcp", "mcp": "/mcp"})


def main() -> None:
    mcp.run(
        transport="streamable-http",
        host=os.environ.get("MCP_HOST", "0.0.0.0"),  # noqa: S104
        port=int(os.environ.get("MCP_PORT", "8000")),
        json_response=True,
        stateless_http=True,
    )


if __name__ == "__main__":
    main()
