"""`search_mapbiomas_methodology` — busca por similaridade no corpus RAG dos
ATBDs da MapBiomas Coleção 11 (metodologia, critérios de classificação,
acurácia). RAG clássico: a busca em si é determinística (distância vetorial no
Postgres/pgvector); o LLM não entra aqui — só no especialista do agente, que lê
os trechos devolvidos e nunca afirma algo que não esteja neles.

Exceção deliberada de "chamada ao vivo com cache curto" (mesmo padrão do
`get_weather_trend`): a pergunta do usuário só pode ser embarcada na hora — o
corpus (os trechos dos PDFs) é que é pré-computado pela ingestão. Cache no
Valkey por texto normalizado da pergunta + top_k.
"""

from __future__ import annotations

import os
import unicodedata
from contextlib import asynccontextmanager

import psycopg
from pydantic import BaseModel

from . import db
from .cache import Cache, make_key
from .embeddings import embed_query, to_vector_literal

SOURCE = "ATBDs MapBiomas Coleção 11 (metodologia)"
DEFAULT_TOP_K = 5
MAX_TOP_K = 10
# abaixo disso, o melhor resultado provavelmente não responde à pergunta —
# repassado como nota, não escondido (honestidade sobre plausibilidade).
_LOW_SCORE_THRESHOLD = 0.3
_CACHE_KEY_PREFIX = "satelite_agro:methodology:"

_DB_UNAVAILABLE = (
    RuntimeError,
    OSError,
    psycopg.OperationalError,
    psycopg.errors.InsufficientPrivilege,
    psycopg.errors.UndefinedTable,
)


class MethodologyChunk(BaseModel):
    source_document: str
    content: str
    score: float  # similaridade de cosseno, 1.0 = idêntico


class MethodologySearch(BaseModel):
    query: str
    available: bool
    chunks: list[MethodologyChunk] = []
    source: str = SOURCE
    notes: list[str] = []


def _norm(text: str) -> str:
    stripped = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return " ".join(stripped.lower().split())


def _gemini_api_key() -> str | None:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    return key or None


@asynccontextmanager
async def _acquire(conn: psycopg.AsyncConnection | None):
    if conn is not None:
        yield conn
    else:
        async with db.connect() as owned:
            yield owned


async def search_methodology(
    query: str,
    top_k: int = DEFAULT_TOP_K,
    *,
    conn: psycopg.AsyncConnection | None = None,
    cache: Cache | None = None,
) -> MethodologySearch:
    q = (query or "").strip()
    if not q:
        return MethodologySearch(query=query, available=False, notes=["pergunta vazia."])

    k = max(1, min(top_k, MAX_TOP_K))

    api_key = _gemini_api_key()
    if api_key is None:
        return MethodologySearch(
            query=q,
            available=False,
            notes=["busca de metodologia indisponível: sem credencial do provedor de embedding."],
        )

    cache_key = make_key("methodology", _norm(q), k, prefix=_CACHE_KEY_PREFIX)
    if cache is not None:
        hit = await cache.get_json(cache_key)
        if hit is not None:
            return MethodologySearch.model_validate(hit)

    try:
        vector = await embed_query(q, api_key=api_key)
        qvec = to_vector_literal(vector)
        async with _acquire(conn) as active, active.cursor() as cur:
            await cur.execute(
                "SELECT source_document, content, 1 - (embedding <=> %(qvec)s::vector) AS score "
                "FROM satelite_agro.rag_chunk "
                "ORDER BY embedding <=> %(qvec)s::vector "
                "LIMIT %(k)s",
                {"qvec": qvec, "k": k},
            )
            rows = await cur.fetchall()
    except _DB_UNAVAILABLE as exc:
        return MethodologySearch(
            query=q,
            available=False,
            notes=[f"busca de metodologia indisponível no momento ({type(exc).__name__})."],
        )

    if not rows:
        result = MethodologySearch(
            query=q,
            available=False,
            notes=["corpus de metodologia ainda não populado (rode a etapa de ingestão)."],
        )
    else:
        chunks = [
            MethodologyChunk(
                source_document=r["source_document"], content=r["content"], score=r["score"]
            )
            for r in rows
        ]
        notes = []
        if chunks[0].score < _LOW_SCORE_THRESHOLD:
            notes.append(
                "similaridade baixa para todos os trechos encontrados — o corpus pode não "
                "cobrir essa pergunta; trate como possivelmente irrelevante."
            )
        result = MethodologySearch(query=q, available=True, chunks=chunks, notes=notes)

    if cache is not None:
        await cache.set_json(cache_key, result.model_dump(mode="json"))
    return result
