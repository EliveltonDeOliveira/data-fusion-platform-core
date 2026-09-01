"""`search_methodology` — lógica pura, sem rede e sem banco real.

O Postgres é substituído por um fake com fila de result sets (mesmo padrão de
`test_land_use.py`); o embedding do Gemini é mockado via monkeypatch.
"""

from __future__ import annotations

import pytest

from satelite_agro_mcp.cache import Cache
from satelite_agro_mcp.methodology import search_methodology

# --------------------------------------------------------------------------- #
# fake do Postgres (mesmo padrão de test_land_use.py)


class _FakeCursor:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, sql, params=None):
        self._conn.executed.append((sql, params))
        if self._conn.raises is not None:
            raise self._conn.raises
        self._conn.current = self._conn.results.pop(0) if self._conn.results else []

    async def fetchall(self):
        return list(self._conn.current)


class FakeConn:
    def __init__(self, *results, raises=None):
        self.results = list(results)
        self.raises = raises
        self.executed: list = []
        self.current: list = []

    def cursor(self):
        return _FakeCursor(self)


class _FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self.store[key] = value


ROWS = [
    {"source_document": "Pampa-Appendix.pdf", "content": "trecho sobre pampa", "score": 0.81},
    {"source_document": "ATBD-General.pdf", "content": "trecho geral", "score": 0.42},
]


async def _fake_embed(query, *, api_key, **kw):
    return [0.1, 0.2, 0.3]


@pytest.fixture(autouse=True)
def _stub_embed(monkeypatch):
    monkeypatch.setattr("satelite_agro_mcp.methodology.embed_query", _fake_embed)
    monkeypatch.setenv("GEMINI_API_KEY", "k")


async def test_search_methodology_retorna_chunks_ordenados():
    conn = FakeConn(ROWS)
    result = await search_methodology("como e classificado o pampa", conn=conn)
    assert result.available
    assert [c.source_document for c in result.chunks] == ["Pampa-Appendix.pdf", "ATBD-General.pdf"]
    assert result.chunks[0].score == 0.81


async def test_search_methodology_score_baixo_gera_nota():
    conn = FakeConn([{"source_document": "x.pdf", "content": "y", "score": 0.1}])
    result = await search_methodology("pergunta bem fora do corpus", conn=conn)
    assert result.available
    assert any("baixa" in n for n in result.notes)


async def test_search_methodology_corpus_vazio():
    conn = FakeConn([])
    result = await search_methodology("qualquer coisa", conn=conn)
    assert not result.available
    assert "ingest" in result.notes[0] or "populado" in result.notes[0]


async def test_search_methodology_sem_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    result = await search_methodology("classificacao de agricultura", conn=FakeConn([]))
    assert not result.available
    assert "credencial" in result.notes[0]


async def test_search_methodology_pergunta_vazia():
    result = await search_methodology("   ", conn=FakeConn([]))
    assert not result.available


async def test_search_methodology_top_k_limitado_a_10():
    conn = FakeConn(ROWS)
    await search_methodology("teste", top_k=999, conn=conn)
    _, params = conn.executed[0]
    assert params["k"] == 10


async def test_search_methodology_db_indisponivel():
    conn = FakeConn(raises=RuntimeError("sem conexao"))
    result = await search_methodology("teste", conn=conn)
    assert not result.available
    assert "indisponível" in result.notes[0]


async def test_search_methodology_cache_hit_nao_bate_no_banco():
    cache = Cache(_FakeRedis())
    conn = FakeConn(ROWS)
    first = await search_methodology("como e classificado o pampa", conn=conn, cache=cache)
    assert first.available
    assert len(conn.executed) == 1

    conn2 = FakeConn(raises=AssertionError("nao deveria consultar o banco no cache hit"))
    second = await search_methodology("como e classificado o pampa", conn=conn2, cache=cache)
    assert second.chunks == first.chunks
    assert conn2.executed == []
