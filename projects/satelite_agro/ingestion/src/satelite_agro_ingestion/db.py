"""Acesso ao Postgres. Camada fina — a lógica de transformação fica nos módulos
de cada fonte; aqui só conexão e escrita em lote."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from typing import Any

import psycopg


@contextmanager
def connect(database_url: str) -> Iterator[psycopg.Connection]:
    conn = psycopg.connect(database_url, autocommit=False)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def fetch_legend_class_ids(conn: psycopg.Connection) -> set[int]:
    with conn.cursor() as cur:
        cur.execute("SELECT class_id FROM satelite_agro.mapbiomas_legend")
        return {row[0] for row in cur.fetchall()}


def fetch_municipio_geocodes(conn: psycopg.Connection) -> set[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT geocode FROM satelite_agro.ibge_municipio")
        return {row[0] for row in cur.fetchall()}


def replace_municipios(
    conn: psycopg.Connection, rows: Sequence[tuple[str, str, str, str, str]]
) -> int:
    """rows: (geocode, name, name_norm, state, state_abbrev). Substitui tudo."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM satelite_agro.land_use_municipality")
        cur.execute("DELETE FROM satelite_agro.ibge_municipio")
        with cur.copy(
            "COPY satelite_agro.ibge_municipio "
            "(geocode, name, name_norm, state, state_abbrev) FROM STDIN"
        ) as copy:
            for row in rows:
                copy.write_row(row)
    return len(rows)


def replace_land_use(conn: psycopg.Connection, rows: Iterable[tuple[str, int, int, float]]) -> int:
    """rows: (geocode, class_id, year, area_ha). Espera ibge_municipio já populado."""
    written = 0
    with conn.cursor() as cur:
        cur.execute("TRUNCATE satelite_agro.land_use_municipality")
        with cur.copy(
            "COPY satelite_agro.land_use_municipality (geocode, class_id, year, area_ha) FROM STDIN"
        ) as copy:
            for row in rows:
                copy.write_row(row)
                written += 1
    return written


def replace_rag_chunks(conn: psycopg.Connection, rows: Iterable[tuple[str, int, str, str]]) -> int:
    """rows: (source_document, chunk_index, content, embedding_literal). Substitui tudo."""
    written = 0
    with conn.cursor() as cur:
        cur.execute("TRUNCATE satelite_agro.rag_chunk")
        with cur.copy(
            "COPY satelite_agro.rag_chunk "
            "(source_document, chunk_index, content, embedding) FROM STDIN"
        ) as copy:
            for row in rows:
                copy.write_row(row)
                written += 1
    return written


def table_count(conn: psycopg.Connection, qualified_table: str) -> int:
    allowed = {
        "satelite_agro.mapbiomas_legend",
        "satelite_agro.ibge_municipio",
        "satelite_agro.land_use_municipality",
        "satelite_agro.rag_chunk",
    }
    if qualified_table not in allowed:
        raise ValueError(f"tabela não permitida: {qualified_table}")
    with conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {qualified_table}")  # noqa: S608 - lista fixa
        result: tuple[Any, ...] = cur.fetchone()  # type: ignore[assignment]
        return int(result[0])
