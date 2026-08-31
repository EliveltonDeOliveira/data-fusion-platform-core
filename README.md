# data-fusion-platform-core

Código de um projeto de portfólio sobre **fusão de dados públicos institucionais
brasileiros**. Orquestração e configuração de execução são mantidas
separadamente; este repositório é só o núcleo.

## Objetivo

Dois recortes, sempre em caráter **informativo e de monitoramento** — nenhuma
saída constitui recomendação de ação:

1. **Satélite + Agro/GIS** — sensoriamento remoto e condição climática/de solo
   aplicados à agricultura (região piloto: Rio Grande do Sul).
2. **Rádio/Comunicação** — consciência de infraestrutura de telecom a partir de
   dados de outorga pública.

## Estrutura

```
shared/
  gateway/        # ponto de entrada em Go: controle de vazão, fila, cache, roteamento de LLM
  llm_router/     # roteamento e fallback entre provedores de LLM
  db/             # schema versionado (postgis-init + migrations)
projects/
  satelite_agro/      { ingestion · agents · mcp_server · rag_corpus }
  radio_comunicacao/  { ingestion · agents · mcp_server · rag_corpus }
tests/eval/       # dataset dourado por projeto
```

## Fontes de dados

| Fonte | Uso |
|---|---|
| [MapBiomas](https://brasil.mapbiomas.org/) | Uso e cobertura da terra, fogo e superfície d'água (séries anuais) |
| [Open-Meteo](https://open-meteo.com/) | Temperatura, precipitação, evapotranspiração, umidade e temperatura do solo |
| [Copernicus / Sentinel Hub (CDSE)](https://dataspace.copernicus.eu/) | Imagens Sentinel para índices de vegetação _(planejado)_ |
| [IBGE — Malhas Territoriais](https://servicodados.ibge.gov.br/api/docs/malhas) | Limites territoriais para recorte e estatística zonal |
| [Anatel — Dados Abertos](https://www.gov.br/anatel/pt-br/dados/dados-abertos) | Estações licenciadas (ERB, VSAT, radiodifusão) e atos normativos |

## Atribuição

Dados publicados sob a Política de Dados Abertos do Poder Executivo Federal
(Decreto 8.777/2016) são de reuso livre, com obrigação de creditar a fonte.
MapBiomas segue seus próprios termos (dados abertos e gratuitos).

## Licença

A definir.
