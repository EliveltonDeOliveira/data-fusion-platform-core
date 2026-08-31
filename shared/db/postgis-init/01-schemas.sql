-- Executado uma única vez, na criação do cluster.

CREATE EXTENSION IF NOT EXISTS postgis;

-- Um schema por projeto; infraestrutura genérica compartilhada.
CREATE SCHEMA IF NOT EXISTS satelite_agro;
CREATE SCHEMA IF NOT EXISTS radio_comunicacao;
CREATE SCHEMA IF NOT EXISTS migrations;
