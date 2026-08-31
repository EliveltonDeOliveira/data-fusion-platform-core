-- PostGIS: a imagem postgis/postgis já cria a extensão no banco padrão;
-- repetido aqui de forma idempotente para não depender da imagem.
CREATE EXTENSION IF NOT EXISTS postgis;

-- Um schema por projeto (ver docs — "O que é compartilhado vs. isolado").
CREATE SCHEMA IF NOT EXISTS satelite_agro;
CREATE SCHEMA IF NOT EXISTS radio_comunicacao;
