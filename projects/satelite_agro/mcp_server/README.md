# satelite_agro / mcp_server

MCP server do Projeto 1. Expõe tools de acesso a dado público; o raciocínio
fica no agente.

## Tools

| Tool | Estado | Fonte |
|---|---|---|
| `get_weather_trend(region, period, granularity, variables)` | implementada | Open-Meteo |

`get_weather_trend` — série climática atual/recente para uma região do **Rio
Grande do Sul** (escopo piloto). Região fora do RS → responde `available=false`
com a explicação, sem inventar número. Consulta a nível de estado usa um ponto
representativo (agregação por área é da Fase 2) e diz isso na resposta.

Variáveis: `temperature`, `precipitation`, `evapotranspiration` (ET₀ FAO),
`soil_moisture`, `soil_temperature` (as duas de solo só em `granularity="hourly"`).

`period`: `"now"`, `"7d"`, `"30"`, ou intervalo ISO `"2026-08-01/2026-08-10"`.

## Testes

```sh
docker build --target test -t sa-mcp-test . && docker run --rm sa-mcp-test
docker run --rm sa-mcp-test uv run --no-sync pytest -m live   # Open-Meteo real
```
