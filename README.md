# data-fusion-platform-core

Sistema multi-agente que funde **dados públicos institucionais brasileiros**
— sensoriamento remoto e condição climática/de solo — para monitoramento
agro/GIS na região piloto do Rio Grande do Sul. Caráter **informativo, nunca
prescritivo**: nenhuma saída constitui recomendação de ação.

Este repositório é só o núcleo — agentes, tools MCP, ingestão e schema.
Orquestração e configuração de execução ficam separadas.

## Arquitetura

```
Usuário
  │
  ▼
Interface (chat)
  │
  ▼
Gateway ── rate limit por IP · cache de resposta · circuit breaker
  │
  ▼
Supervisor (LangGraph) ── decompõe a pergunta e roteia
  │
  ├──▶ Especialista Clima         ─┐
  ├──▶ Especialista Uso-da-Terra   ├─ paralelo (fan-out); cada um decide
  └──▶ Especialista Metodologia   ─┘  suas próprias tools via MCP (ReAct)
           │
           ▼
     MCP server ── tools tipadas, contrato fixo e versionado
           │
           ▼
  Postgres/PostGIS (pré-agregado) · RAG (corpus MapBiomas) · Open-Meteo (ao vivo)
```

Padrões de AI Engineering aplicados:

- **Orchestrator-workers** — um Supervisor decompõe a pergunta e delega para
  especialistas.
- **Paralelização de especialistas independentes** — Clima e Uso-da-Terra
  rodam em fan-out quando a pergunta pede os dois (I/O-bound).
- **Tool-use (ReAct) via MCP** — o especialista decide qual tool chamar,
  observa o resultado e decide se responde ou chama outra; o MCP desacopla
  raciocínio de acesso a dado.
- **Determinístico-primeiro, LLM contido** — todo número que aparece numa
  resposta vem direto do payload cru da tool, nunca do texto livre do LLM; o
  modelo só correlaciona e explica.
- **Guardrail determinístico** — pedidos de recomendação (“devo irrigar?”,
  “vale a pena investir?”) são recusados por checagem de código, não só por
  instrução de prompt.
- **RAG clássico** sobre a metodologia oficial (ATBDs da MapBiomas) para
  perguntas de definição/classificação.
- **Honestidade sobre plausibilidade** — fora da região piloto, ou ano sem
  cobertura, o agente diz isso explicitamente em vez de preencher com um
  número plausível.

## Fontes de dados

| Fonte | Uso |
|---|---|
| [MapBiomas](https://brasil.mapbiomas.org/) | Uso e cobertura da terra, fogo e superfície d'água (séries anuais) |
| [Open-Meteo](https://open-meteo.com/) | Temperatura, precipitação, evapotranspiração, umidade e temperatura do solo |
| [IBGE — Malhas Territoriais](https://servicodados.ibge.gov.br/api/docs/malhas) | Limites territoriais para recorte e estatística zonal |

## Tools MCP

O `mcp_server` expõe o acesso a dado como tools tipadas de contrato fixo — o
raciocínio fica no agente. Contrato versionado: novas versões em vez de
quebrar assinatura.

| Tool | Fonte |
|---|---|
| `get_weather_trend(region, period, granularity, variables)` | Open-Meteo (ao vivo, cache curto) |
| `get_land_use_summary(region, year, level=2)` | MapBiomas (anual, pré-agregado) |
| `get_land_use_at_point(lat, lon, year, level=2)` | MapBiomas (raster do RS) |
| `get_land_use_change(region, year_from, year_to, level=2)` | MapBiomas (anual, pré-agregado) |
| `search_mapbiomas_methodology(query, top_k=5)` | ATBDs MapBiomas (corpus RAG, embedding + pgvector) |

- **Escopo geográfico:** Rio Grande do Sul (piloto). Fora dele, ou sem dado
  para a consulta, a tool responde `available=false` com a explicação em
  `notes` — nunca inventa número.
- **`level`** (tools de uso da terra): nível da legenda hierárquica do
  MapBiomas, `1`–`4`, padrão `2`, sempre explícito — nunca agrega ou
  desagrega em silêncio.

## Avaliação

Dataset-âncora determinístico em [`tests/eval/`](tests/eval/): perguntas reais
rodadas contra o agente e checadas por regras puras — sem LLM na checagem.
Cobre roteamento entre especialistas (inclusive perguntas que exigem dois),
honestidade quando não há dado (fora da região piloto, ano sem cobertura) e o
guardrail de não-recomendação. Dataset em
[`cases/satelite_agro.json`](tests/eval/cases/satelite_agro.json), checagens em
[`checks.py`](tests/eval/checks.py).

## Limitações

- Cobertura piloto: Rio Grande do Sul — fora disso o agente recusa e explica
  em vez de estimar.
- Uso e cobertura da terra é um produto **anual** (MapBiomas), tratado como
  tendência histórica, não leitura do dia.

## Como rodar os testes

Tudo roda em container — nada é instalado na máquina. Dependências Python com
[uv](https://docs.astral.sh/uv/) (`uv.lock` por serviço), lint/format com
[ruff](https://docs.astral.sh/ruff/) (`ruff.toml`). Cada serviço Python tem um
alvo `test` no seu `Dockerfile`, por exemplo:

```sh
cd projects/satelite_agro/mcp_server
docker build --target test -t sa-mcp-test .
docker run --rm sa-mcp-test
```

O Gateway (Go) roda testes localmente, sem container:

```sh
cd shared/gateway
go test ./...
```

## Atribuição

- **MapBiomas** e **Open-Meteo** são licenciados sob
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/deed.pt_BR) — uso
  público e aberto, mediante referência à fonte.
- **IBGE** publica sob a Política de Dados Abertos do Poder Executivo Federal
  (Decreto 8.777/2016): reuso livre, com obrigação de creditar a fonte (a
  política não define uma licença Creative Commons específica).

## Licença

[MIT](LICENSE) — cobre só o código deste repositório. Os dados usados têm
suas próprias licenças (ver "Atribuição" acima).

## Isenção de responsabilidade / Aviso legal

Este é um **projeto de portfólio**, desenvolvido para fins de estudo e
demonstração técnica. Não possui vínculo, patrocínio ou endosso da MapBiomas,
da Open-Meteo, do IBGE ou de qualquer outra instituição, e não constitui um
serviço oficial dessas fontes.

- **Natureza informativa.** Todo o conteúdo produzido pelo sistema (respostas
  dos agentes, dados agregados, textos) tem caráter **estritamente informativo
  e de monitoramento**. Nenhuma saída constitui recomendação, aconselhamento
  ou parecer — técnico, agronômico, ambiental, econômico, jurídico ou de
  qualquer outra natureza — nem deve ser usada como base única para decisão
  operacional. O sistema não substitui a avaliação de profissional habilitado.
- **Dados de terceiros.** As informações derivam de fontes públicas externas e
  são reproduzidas "no estado em que se encontram", sem garantia de exatidão,
  completude ou atualidade. As etapas de recorte, fusão e agregação podem
  introduzir imprecisões adicionais.
- **Respostas geradas por modelo de linguagem.** Parte das respostas é
  redigida por um LLM e pode conter erros, omissões ou interpretações
  equivocadas, ainda que os números apresentados venham diretamente das
  fontes de dados.
- **Sem garantias.** O software é fornecido sem qualquer garantia, expressa ou
  implícita (ver [LICENSE](LICENSE)). Não há compromisso de disponibilidade,
  continuidade ou suporte. O uso é por conta e risco de quem o realiza, e os
  autores não se responsabilizam por perdas ou danos decorrentes desse uso.
