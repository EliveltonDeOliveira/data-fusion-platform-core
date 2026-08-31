-- MapBiomas Coleção 11 — legenda: código de pixel -> classe e sua posição na
-- hierarquia (Nível 1-4). Tabela de referência fixa, semeada aqui em SQL.
--
-- Fonte da hierarquia: "Códigos de Legenda" + "Descrição das Classes da Legenda"
-- da Coleção 11 (MapBiomas Brasil, publicado 2026-08-13). Essa é a hierarquia
-- CANÔNICA do projeto. As colunas class_level_* das planilhas de Estatísticas
-- usam uma sub-numeração divergente (ex.: Formação Savânica como 1.2 em vez de
-- 1.3) e NÃO são usadas — os níveis são sempre derivados desta tabela via
-- class_id.
--
-- level_N_code guarda o código hierárquico ("3.2.1"); level_N_pt o rótulo.
-- Níveis mais rasos que o da classe ficam NULL — a consulta faz o "carry down"
-- (COALESCE do nível pedido para o mais profundo disponível).

CREATE TABLE satelite_agro.mapbiomas_legend (
    class_id      smallint PRIMARY KEY,
    name_pt       text     NOT NULL,
    name_en       text     NOT NULL,
    hex_color     text     NOT NULL,
    level_1_id    smallint,
    level_1_pt    text,
    level_2_code  text,
    level_2_pt    text,
    level_3_code  text,
    level_3_pt    text,
    level_4_code  text,
    level_4_pt    text,
    is_beta       boolean  NOT NULL DEFAULT false,
    collection    smallint NOT NULL DEFAULT 11,
    CONSTRAINT mapbiomas_legend_level_1_id_range
        CHECK (level_1_id IS NULL OR level_1_id BETWEEN 1 AND 5)
);

COMMENT ON TABLE satelite_agro.mapbiomas_legend IS
    'MapBiomas Coleção 11: código de pixel -> classe de uso/cobertura + '
    'hierarquia Nível 1-4 (fonte: PDF oficial de legenda, 2026-08-13). '
    'Hierarquia canônica do projeto; as colunas class_level_* das planilhas de '
    'Estatísticas divergem e não são usadas.';

INSERT INTO satelite_agro.mapbiomas_legend
    (class_id, name_pt, name_en, hex_color,
     level_1_id, level_1_pt,
     level_2_code, level_2_pt,
     level_3_code, level_3_pt,
     level_4_code, level_4_pt,
     is_beta)
VALUES
    -- Sem dado
    (0,  'Não Observado', 'Not Observed', '#ffffff',
         NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, false),

    -- Nível 1 (nós de agregação; podem aparecer como valor de pixel em coleções antigas)
    (1,  'Floresta', 'Forest', '#1f8d49',
         1, 'Floresta', NULL, NULL, NULL, NULL, NULL, NULL, false),
    (10, 'Vegetação Herbácea e Arbustiva', 'Herbaceous or Shrubby Vegetation', '#d6bc74',
         2, 'Vegetação Herbácea e Arbustiva', NULL, NULL, NULL, NULL, NULL, NULL, false),
    (14, 'Agropecuária', 'Farming', '#ffefc3',
         3, 'Agropecuária', NULL, NULL, NULL, NULL, NULL, NULL, false),
    (22, 'Área não Vegetada', 'Non Vegetated Area', '#d4271e',
         4, 'Área não Vegetada', NULL, NULL, NULL, NULL, NULL, NULL, false),
    (26, 'Corpo D''água', 'Water', '#2532e4',
         5, 'Corpo D''água', NULL, NULL, NULL, NULL, NULL, NULL, false),

    -- 1. Floresta
    (3,  'Formação Florestal', 'Forest Formation', '#1f8d49',
         1, 'Floresta', '1.1', 'Formação Florestal', NULL, NULL, NULL, NULL, false),
    (6,  'Floresta Alagável', 'Floodable Forest', '#007785',
         1, 'Floresta', '1.2', 'Floresta Alagável', NULL, NULL, NULL, NULL, false),
    (4,  'Formação Savânica', 'Savanna Formation', '#7dc975',
         1, 'Floresta', '1.3', 'Formação Savânica', NULL, NULL, NULL, NULL, false),
    (7,  'Savana Alagada (beta)', 'Flooded Savanna (beta)', '#228c70',
         1, 'Floresta', '1.4', 'Savana Alagada (beta)', NULL, NULL, NULL, NULL, true),
    (5,  'Mangue', 'Mangrove', '#04381d',
         1, 'Floresta', '1.5', 'Mangue', NULL, NULL, NULL, NULL, false),
    (49, 'Restinga Arbórea', 'Wooded Sandbank Vegetation', '#02d659',
         1, 'Floresta', '1.6', 'Restinga Arbórea', NULL, NULL, NULL, NULL, false),

    -- 2. Vegetação Herbácea e Arbustiva
    (12, 'Formação Campestre', 'Grassland Formation', '#d6bc74',
         2, 'Vegetação Herbácea e Arbustiva', '2.1', 'Formação Campestre', NULL, NULL, NULL, NULL, false),
    (77, 'Formação Herbáceo Arbustiva', 'Herbaceous and Shrub Formation', '#86b074',
         2, 'Vegetação Herbácea e Arbustiva', '2.2', 'Formação Herbáceo Arbustiva', NULL, NULL, NULL, NULL, false),
    (11, 'Campo Alagado e Área Pantanosa', 'Wetland', '#519799',
         2, 'Vegetação Herbácea e Arbustiva', '2.3', 'Campo Alagado e Área Pantanosa', NULL, NULL, NULL, NULL, false),
    (84, 'Marismas (beta)', 'Salt Marsh (beta)', '#81dbbf',
         2, 'Vegetação Herbácea e Arbustiva', '2.4', 'Marismas (beta)', NULL, NULL, NULL, NULL, true),
    (50, 'Restinga Herbácea ou Arbustiva', 'Herbaceous Sandbank Vegetation', '#ffaa5f',
         2, 'Vegetação Herbácea e Arbustiva', '2.5', 'Restinga Herbácea ou Arbustiva', NULL, NULL, NULL, NULL, false),
    (32, 'Apicum', 'Hypersaline Tidal Flat', '#fc8114',
         2, 'Vegetação Herbácea e Arbustiva', '2.6', 'Apicum', NULL, NULL, NULL, NULL, false),
    (29, 'Afloramento Rochoso', 'Rocky Outcrop', '#ad5100',
         2, 'Vegetação Herbácea e Arbustiva', '2.7', 'Afloramento Rochoso', NULL, NULL, NULL, NULL, false),

    -- 3. Agropecuária
    (15, 'Pastagem', 'Pasture', '#edde8e',
         3, 'Agropecuária', '3.1', 'Pastagem', NULL, NULL, NULL, NULL, false),
    (18, 'Agricultura', 'Agriculture', '#e974ed',
         3, 'Agropecuária', '3.2', 'Agricultura', NULL, NULL, NULL, NULL, false),
    (19, 'Lavoura Temporária', 'Temporary Crop', '#c27ba0',
         3, 'Agropecuária', '3.2', 'Agricultura', '3.2.1', 'Lavoura Temporária', NULL, NULL, false),
    (39, 'Soja', 'Soybean', '#f5b3c8',
         3, 'Agropecuária', '3.2', 'Agricultura', '3.2.1', 'Lavoura Temporária', '3.2.1.1', 'Soja', false),
    (20, 'Cana', 'Sugar Cane', '#db7093',
         3, 'Agropecuária', '3.2', 'Agricultura', '3.2.1', 'Lavoura Temporária', '3.2.1.2', 'Cana', false),
    (40, 'Arroz', 'Rice', '#c71585',
         3, 'Agropecuária', '3.2', 'Agricultura', '3.2.1', 'Lavoura Temporária', '3.2.1.3', 'Arroz', false),
    (62, 'Algodão (beta)', 'Cotton (beta)', '#ff69b4',
         3, 'Agropecuária', '3.2', 'Agricultura', '3.2.1', 'Lavoura Temporária', '3.2.1.4', 'Algodão (beta)', true),
    (41, 'Outras Lavouras Temporárias', 'Other Temporary Crops', '#f54ca9',
         3, 'Agropecuária', '3.2', 'Agricultura', '3.2.1', 'Lavoura Temporária', '3.2.1.5', 'Outras Lavouras Temporárias', false),
    (36, 'Lavoura Perene', 'Perennial Crop', '#d082de',
         3, 'Agropecuária', '3.2', 'Agricultura', '3.2.2', 'Lavoura Perene', NULL, NULL, false),
    (46, 'Café', 'Coffee', '#d68fe2',
         3, 'Agropecuária', '3.2', 'Agricultura', '3.2.2', 'Lavoura Perene', '3.2.2.1', 'Café', false),
    (47, 'Citrus', 'Citrus', '#9932cc',
         3, 'Agropecuária', '3.2', 'Agricultura', '3.2.2', 'Lavoura Perene', '3.2.2.2', 'Citrus', false),
    (35, 'Dendê', 'Palm Oil', '#9065d0',
         3, 'Agropecuária', '3.2', 'Agricultura', '3.2.2', 'Lavoura Perene', '3.2.2.3', 'Dendê', false),
    (48, 'Outras Lavouras Perenes', 'Other Perennial Crops', '#e6ccff',
         3, 'Agropecuária', '3.2', 'Agricultura', '3.2.2', 'Lavoura Perene', '3.2.2.4', 'Outras Lavouras Perenes', false),
    (9,  'Silvicultura', 'Forest Plantation', '#7a5900',
         3, 'Agropecuária', '3.3', 'Silvicultura', NULL, NULL, NULL, NULL, false),
    (21, 'Mosaico de Usos', 'Mosaic of Uses', '#ffefc3',
         3, 'Agropecuária', '3.4', 'Mosaico de Usos', NULL, NULL, NULL, NULL, false),

    -- 4. Área não Vegetada
    (23, 'Praia, Duna e Areal', 'Beach, Dune and Sand Spot', '#ffa07a',
         4, 'Área não Vegetada', '4.1', 'Praia, Duna e Areal', NULL, NULL, NULL, NULL, false),
    (24, 'Área Urbanizada', 'Urban Area', '#d4271e',
         4, 'Área não Vegetada', '4.2', 'Área Urbanizada', NULL, NULL, NULL, NULL, false),
    (30, 'Mineração', 'Mining', '#9c0027',
         4, 'Área não Vegetada', '4.3', 'Mineração', NULL, NULL, NULL, NULL, false),
    (75, 'Usina Fotovoltaica', 'Photovoltaic Power Plant', '#757272',
         4, 'Área não Vegetada', '4.4', 'Usina Fotovoltaica', NULL, NULL, NULL, NULL, false),
    (91, 'Parque eólico (beta)', 'Wind farm (beta)', '#403d3e',
         4, 'Área não Vegetada', '4.5', 'Parque eólico (beta)', NULL, NULL, NULL, NULL, true),
    -- 25: "Outras Área não Vegetadas" — concordância no singular vem assim do CSV
    -- oficial do MapBiomas (Coleção 11); mantido literal para o seed casar.
    (25, 'Outras Área não Vegetadas', 'Other non Vegetated Areas', '#db4d4f',
         4, 'Área não Vegetada', '4.6', 'Outras Área não Vegetadas', NULL, NULL, NULL, NULL, false),

    -- 5. Corpo D'água
    (33, 'Rio, Lago e Oceano', 'River, Lake and Ocean', '#2532e4',
         5, 'Corpo D''água', '5.1', 'Rio, Lago e Oceano', NULL, NULL, NULL, NULL, false),
    (31, 'Aquicultura', 'Aquaculture', '#091077',
         5, 'Corpo D''água', '5.2', 'Aquicultura', NULL, NULL, NULL, NULL, false);
