# satelite_agro / mcp_server

MCP server do Projeto 1. Expõe tools de acesso a dado público; o raciocínio
fica no agente.

## Tools

| Tool | Estado | Fonte |
|---|---|---|
| `get_weather_trend(region, period, granularity, variables)` | implementada | Open-Meteo (ao vivo) |
| `get_land_use_summary(region, year, level=2)` | implementada | MapBiomas Coleção 11 (pré-agregado) |
| `get_land_use_at_point(lat, lon, year, level=2)` | implementada | MapBiomas Coleção 11 (raster do RS) |
| `get_land_use_change(region, year_from, year_to, level=2)` | planejada | MapBiomas Coleção 11 (pré-agregado) |

Escopo geográfico de todas: **Rio Grande do Sul** (piloto). Fora dele, ou sem
dado para a consulta, a tool responde `available=false` com a explicação em
`notes` — nunca inventa número.

### `get_weather_trend`

Série climática atual/recente. Consulta a nível de estado usa um ponto
representativo e diz isso na resposta. Variáveis: `temperature`,
`precipitation`, `evapotranspiration` (ET₀ FAO), `soil_moisture`,
`soil_temperature` (as duas de solo só em `granularity="hourly"`). `period`:
`"now"`, `"7d"`, `"30"`, ou intervalo ISO `"2026-08-01/2026-08-10"`.

### `get_land_use_summary`

Composição de uso e cobertura da terra por área (hectares), lida de dado anual
pré-agregado (1985–2025). `region`: município do RS, `"região de X"` (resolve
para o município X), ou o estado. Sem buffer de vizinhos, sem cálculo zonal ao
vivo.

### `get_land_use_at_point`

Classe de um ponto por leitura de 1 pixel (~30 m) do raster do RS. Só o ano com
raster recortado está disponível; fora disso, aponta `get_land_use_summary`.

### `get_land_use_change` (planejada)

Variação da composição entre dois anos, do mesmo dado pré-agregado que o
`summary` usa. Contrato pretendido:

```
get_land_use_change(region, year_from, year_to, level=2)
  -> { available, location, year_from, year_to, level,
       classes: [ { code, label,
                    area_from_ha, area_to_ha,
                    delta_ha, delta_pct_points } ],   # ordenado por |delta_ha|
       source, notes }
```

Sem implicar causa nem projeção: só a diferença medida entre os dois anos, por
classe. `year_from`/`year_to` fora de 1985–2025 ou `region` fora do RS →
`available=false` com nota. Ainda não implementada.

### `level` (tools de uso da terra)

Nível da legenda hierárquica do MapBiomas, `1`–`4`, padrão `2`. Sempre
explícito: a consulta agrega no nível pedido e faz *carry down* para o nível
mais profundo disponível em cada classe. Nunca agrega/desagrega em silêncio.

## Testes

```sh
docker build --target test -t sa-mcp-test . && docker run --rm sa-mcp-test
docker run --rm sa-mcp-test uv run --no-sync pytest -m live   # Open-Meteo real
```

Os testes não tocam rede nem banco: o Postgres é um fake e o raster é um GeoTIFF
sintético.
