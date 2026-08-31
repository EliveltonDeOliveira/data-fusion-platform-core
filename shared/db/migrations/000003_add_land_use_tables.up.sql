-- Uso/cobertura da terra do MapBiomas, pré-agregado por município e ano.
-- Populado pelo job de ingestão (projects/satelite_agro/ingestion), a partir da
-- planilha de Estatísticas da Coleção 11. Recorte: só o Rio Grande do Sul.
-- Nenhuma agregação espacial ao vivo — a consulta por região soma linhas.

CREATE TABLE satelite_agro.ibge_municipio (
    geocode       text PRIMARY KEY,          -- código IBGE de 7 dígitos
    name          text NOT NULL,
    name_norm     text NOT NULL,             -- sem acento, minúsculo, para casar nome de região
    state         text NOT NULL,
    state_abbrev  text NOT NULL
);

CREATE INDEX ibge_municipio_name_norm_idx
    ON satelite_agro.ibge_municipio (name_norm);
CREATE INDEX ibge_municipio_state_abbrev_idx
    ON satelite_agro.ibge_municipio (state_abbrev);

COMMENT ON TABLE satelite_agro.ibge_municipio IS
    'Municípios do RS (API de Malhas/Localidades do IBGE). Usado para resolver '
    '"região de X" -> geocode. Sem geometria nesta fase.';

CREATE TABLE satelite_agro.land_use_municipality (
    geocode   text     NOT NULL REFERENCES satelite_agro.ibge_municipio (geocode),
    class_id  smallint NOT NULL REFERENCES satelite_agro.mapbiomas_legend (class_id),
    year      smallint NOT NULL,
    area_ha   double precision NOT NULL,
    PRIMARY KEY (geocode, class_id, year),
    CONSTRAINT land_use_municipality_year_min CHECK (year >= 1985),
    CONSTRAINT land_use_municipality_area_nonneg CHECK (area_ha >= 0)
);

CREATE INDEX land_use_municipality_year_idx
    ON satelite_agro.land_use_municipality (year);

COMMENT ON TABLE satelite_agro.land_use_municipality IS
    'Área (hectares) por classe MapBiomas Coleção 11, por município do RS e por '
    'ano (1985-2025). Origem: planilha BIOME_STATE_MUNICIPALITY. Pré-agregado.';
