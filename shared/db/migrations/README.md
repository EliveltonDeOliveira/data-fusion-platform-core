# Migrations

Schema versionado do Postgres+PostGIS, aplicado com
[golang-migrate](https://github.com/golang-migrate/migrate). Fonte única de
verdade do schema — inclusive a criação de extensão e dos schemas por projeto
(`000001`). Não há script de init separado.

## Convenção de arquivo

```
{versão}_{título}.up.sql     # aplica
{versão}_{título}.down.sql    # reverte
```

Versão em 6 dígitos, sequencial. Ex.: `000002_add_mapbiomas_legend.up.sql`.

golang-migrate mantém o controle de versão na tabela `schema_migrations`
(schema `public`).
