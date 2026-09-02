# data-fusion-platform-core

Código de um projeto de portfólio sobre **fusão de dados públicos institucionais
brasileiros**. Orquestração e configuração de execução são mantidas
separadamente; este repositório é só o núcleo.

## Objetivo

Sensoriamento remoto e condição climática/de solo aplicados à agricultura
(região piloto: Rio Grande do Sul), fundindo fontes públicas institucionais
distintas num só sistema multi-agente — sempre em caráter **informativo e de
monitoramento**, nenhuma saída constitui recomendação de ação.

## Fontes de dados

| Fonte | Uso |
|---|---|
| [MapBiomas](https://brasil.mapbiomas.org/) | Uso e cobertura da terra, fogo e superfície d'água (séries anuais) |
| [Open-Meteo](https://open-meteo.com/) | Temperatura, precipitação, evapotranspiração, umidade e temperatura do solo |
| [IBGE — Malhas Territoriais](https://servicodados.ibge.gov.br/api/docs/malhas) | Limites territoriais para recorte e estatística zonal |

## Desenvolvimento

Tudo roda em container — nada é instalado na máquina. Dependências Python com
[uv](https://docs.astral.sh/uv/) (`uv.lock` por serviço), lint/format com
[ruff](https://docs.astral.sh/ruff/) (`ruff.toml`). Cada serviço tem um alvo
`test` no seu `Dockerfile`.

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
