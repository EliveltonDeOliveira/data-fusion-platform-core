"""Acesso ao Postgres local — só leitura, para as tools de uso da terra.

O dado já vem pré-agregado por um pipeline de lote (sem LLM). Aqui é uma query
de leitura por chamada; a carga é baixa e cada request é curta, então não há
pool. Se `DATABASE_URL` não estiver no ambiente, as tools de uso da terra
respondem `available=false` explicando — nunca inventam número.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import psycopg
from psycopg.rows import dict_row


def database_url() -> str | None:
    url = os.environ.get("DATABASE_URL", "").strip()
    return url or None


@asynccontextmanager
async def connect() -> AsyncIterator[psycopg.AsyncConnection]:
    url = database_url()
    if not url:
        raise RuntimeError("DATABASE_URL não configurado")
    conn = await psycopg.AsyncConnection.connect(url, autocommit=True, row_factory=dict_row)
    try:
        yield conn
    finally:
        await conn.close()
