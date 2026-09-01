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

from . import land_use, methodology, regions, weather
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
_methodology_cache = Cache.from_env(ttl_env_var="RAG_CACHE_TTL")

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


_LAND_USE_SUMMARY_DESC = """\
Composição de uso e cobertura da terra (MapBiomas Coleção 11) de uma região do
Rio Grande do Sul (escopo piloto), por área em hectares. Fonte: dado anual
pré-agregado (1985-2025) lido do banco local. Determinístico, sem LLM.
Informativo: entrega composição + contexto histórico, nunca recomendação.

Parâmetros:
- region: município do RS ("Santa Maria", "Porto Alegre"), "região de X" (resolve
  para o município X), ou o estado ("RS", "Rio Grande do Sul"). Fora do RS ou nome
  não reconhecido -> available=false com a explicação em notes, sem número
  inventado. Não há buffer de vizinhos nem cálculo zonal ao vivo.
- year: ano entre 1985 e 2025. Padrão 2025. Fora da faixa -> available=false.
- level: nível da legenda hierárquica, 1 a 4. Padrão 2. Sempre explícito: a
  consulta agrega no nível pedido e faz "carry down" para o nível mais profundo
  disponível em cada classe. Nunca agrega/desagrega em silêncio.

Retorno: available, location (município ou estado, com geocode), year, level,
total_area_ha, classes (code, label, area_ha, area_pct, ordenado por área) e
notes. Sempre repasse as notes ao usuário."""

_LAND_USE_POINT_DESC = """\
Classe de uso e cobertura da terra (MapBiomas Coleção 11) em um ponto do Rio
Grande do Sul, por leitura de 1 pixel (~30 m) do raster do RS. Determinístico,
sem LLM. Informativo, nunca recomendação.

Parâmetros:
- lat, lon: coordenadas em graus decimais (EPSG:4326). Ponto fora do RS -> pixel
  sem observação -> available=false com a explicação, sem chute.
- year: só 2025 tem raster recortado. Outro ano -> available=false apontando
  get_land_use_summary.
- level: nível da legenda, 1 a 4. Padrão 2. Mesmo "carry down" do summary.

Retorno: available, point, year, level, class_id, code, label (no nível pedido),
name_pt (classe da folha), hierarchy (level_1..4) e notes. Repasse as notes."""


@mcp.tool(name="get_land_use_summary", description=_LAND_USE_SUMMARY_DESC)
async def get_land_use_summary(region: str, year: int = 2025, level: int = 2) -> dict:
    """Adapta `land_use.get_land_use_summary` para a camada MCP."""
    result = await land_use.get_land_use_summary(region, year, level)
    return result.model_dump(mode="json")


@mcp.tool(name="get_land_use_at_point", description=_LAND_USE_POINT_DESC)
async def get_land_use_at_point(lat: float, lon: float, year: int = 2025, level: int = 2) -> dict:
    """Adapta `land_use.get_land_use_at_point` para a camada MCP."""
    result = await land_use.get_land_use_at_point(lat, lon, year, level)
    return result.model_dump(mode="json")


_LAND_USE_CHANGE_DESC = """\
Variação de uso e cobertura da terra (MapBiomas Coleção 11) de uma região do Rio
Grande do Sul entre dois anos, por classe, em hectares. Fonte: mesmo dado anual
pré-agregado do get_land_use_summary (1985-2025), lido nos dois anos e
diferenciado. Determinístico, sem LLM. Informativo: entrega a variação medida e o
contexto histórico — nunca a causa, nunca projeção de tendência, nunca
recomendação.

Parâmetros:
- region: município do RS ("Santa Maria"), "região de X" (resolve para o município
  X) ou o estado ("RS", "Rio Grande do Sul"). Fora do RS ou nome não reconhecido
  -> available=false com a explicação em notes.
- year_from, year_to: dois anos distintos entre 1985 e 2025. Fora da faixa ou
  iguais -> available=false.
- level: nível da legenda hierárquica, 1 a 4. Padrão 2. Mesmo "carry down" do
  summary. Sempre explícito, nunca agrega/desagrega em silêncio.

Retorno: available, location, year_from, year_to, level, total_area_from_ha,
total_area_to_ha, classes (code, label, area_from_ha, area_to_ha, delta_ha,
delta_pct_points; ordenado por |delta_ha|) e notes. Sempre repasse as notes."""


@mcp.tool(name="get_land_use_change", description=_LAND_USE_CHANGE_DESC)
async def get_land_use_change(region: str, year_from: int, year_to: int, level: int = 2) -> dict:
    """Adapta `land_use.get_land_use_change` para a camada MCP."""
    result = await land_use.get_land_use_change(region, year_from, year_to, level)
    return result.model_dump(mode="json")


_LAND_USE_TIMESERIES_DESC = """\
Série histórica completa (1985-2025) de uso e cobertura da terra (MapBiomas
Coleção 11) de uma região do Rio Grande do Sul, por classe, em hectares e
percentual — toda a profundidade que o dado tabular tem, não só dois anos.
Determinístico, sem LLM. Informativo: mostra a tendência de longo prazo —
nunca a causa, nunca projeção do futuro, nunca recomendação.

Parâmetros:
- region: município do RS ("Santa Maria"), "região de X" (resolve para o
  município X) ou o estado ("RS", "Rio Grande do Sul"). Fora do RS ou nome
  não reconhecido -> available=false com a explicação em notes.
- level: nível da legenda hierárquica, 1 a 4. Padrão 2. Mesmo "carry down"
  dos outros dois. Sempre explícito, nunca agrega/desagrega em silêncio.

Retorno: available, location, level, year_from (1985), year_to (2025),
classes (code, label, points: lista de {year, area_ha, area_pct} pra cada
ano do intervalo) e notes. Sempre repasse as notes."""


@mcp.tool(name="get_land_use_timeseries", description=_LAND_USE_TIMESERIES_DESC)
async def get_land_use_timeseries(region: str, level: int = 2) -> dict:
    """Adapta `land_use.get_land_use_timeseries` para a camada MCP."""
    result = await land_use.get_land_use_timeseries(region, level)
    return result.model_dump(mode="json")


_METHODOLOGY_SEARCH_DESC = """\
Busca por trecho relevante nos ATBDs (documentos de metodologia) da MapBiomas
Coleção 11 — como a classificação é feita, critérios de cada classe de uso da
terra, avaliação de acurácia. Fonte: corpus pré-computado (embedding) a partir
de um subconjunto dos PDFs oficiais. Busca vetorial determinística; não gera
texto novo. Informativo, nunca recomendação.

Parâmetros:
- query: a pergunta ou termo de busca, em português ou inglês.
- top_k: quantos trechos retornar (1 a 10, padrão 5).

Retorno: available, chunks (source_document, content, score de similaridade
0-1, ordenado do mais relevante), source, notes. Se o melhor score for baixo, a
nota avisa que o corpus pode não cobrir a pergunta — repasse isso ao usuário.
Sem corpus populado ou sem credencial de embedding -> available=false."""


@mcp.tool(name="search_mapbiomas_methodology", description=_METHODOLOGY_SEARCH_DESC)
async def search_mapbiomas_methodology(query: str, top_k: int = 5) -> dict:
    """Adapta `methodology.search_methodology` para a camada MCP."""
    result = await methodology.search_methodology(query, top_k, cache=_methodology_cache)
    return result.model_dump(mode="json")


_REGION_POINT_DESC = """\
Resolve uma região do Rio Grande do Sul (município ou o estado) para um ponto
representativo (lat/lon) — mesmo geocoding usado por get_weather_trend, sem
nenhum dado novo. Determinístico, sem LLM. Uso interno de apoio (ex.: dar
zoom/centralizar um mapa) — não traz clima nem uso da terra; para isso use
get_weather_trend ou get_land_use_summary/at_point.

Parâmetros:
- region: município do RS ou o estado ("RS", "Rio Grande do Sul"). Fora do RS
  ou não encontrado -> available=false com a explicação em notes.

Retorno: available, location (nome, lat/lon, se é ponto representativo do
estado) e notes."""


@mcp.tool(name="resolve_region_point", description=_REGION_POINT_DESC)
async def resolve_region_point(region: str) -> dict:
    """Adapta `regions.resolve_region_point` para a camada MCP."""
    result = await regions.resolve_region_point(region, cache=_cache)
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
