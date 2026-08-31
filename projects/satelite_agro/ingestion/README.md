# satelite_agro / ingestion

Pipeline determinístico (sem LLM) que lê dado público institucional e grava
pré-agregado no Postgres. Toda agregação espacial pesada acontece aqui, nunca
numa consulta ao vivo.

## Etapas

| Etapa | Entrada | Saída |
|---|---|---|
| `legend` | CSV oficial de legenda do MapBiomas (Coleção 11) | confere o seed da migration `000002` (falha se divergir) |
| `municipios` | API de Localidades do IBGE | tabela de municípios do RS |
| `land-use` | planilha de Estatísticas do MapBiomas (aba `COVERAGE_11`) | área por classe × município × ano (1985–2025); só RS, somada entre biomas, células ≤ 0 omitidas |
| `raster` | GeoTIFF nacional de cobertura + malha do RS (IBGE) | raster recortado do RS (o nacional não é copiado) |

Geocodes que o IBGE atribui a corpos d'água (Lagoa dos Patos, Lagoa Mirim) não
são municípios e são pulados, com contagem reportada.

## Uso

```sh
python -m satelite_agro_ingestion                 # todas as etapas
python -m satelite_agro_ingestion --only land-use
python -m satelite_agro_ingestion --skip raster
```

Configuração (conexão, diretórios de dado, ano-alvo) vem do ambiente conforme
o ambiente de execução.

## Testes

```sh
docker build --target test -t sa-ingest-test . && docker run --rm sa-ingest-test
```

Sem rede e sem Postgres — as transformações são funções puras testadas com
fixtures.
