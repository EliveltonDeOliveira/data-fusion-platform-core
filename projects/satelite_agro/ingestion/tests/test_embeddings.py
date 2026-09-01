from __future__ import annotations

from satelite_agro_ingestion.embeddings import embed_texts, to_vector_literal


def test_embed_texts_uma_chamada_por_trecho(httpx_mock, monkeypatch):
    monkeypatch.setattr("satelite_agro_ingestion.embeddings._MIN_INTERVAL_SECONDS", 0)
    httpx_mock.add_response(json={"embedding": {"values": [0.1, 0.2, 0.3]}})
    httpx_mock.add_response(json={"embedding": {"values": [0.4, 0.5, 0.6]}})

    vectors = embed_texts(["primeiro", "segundo"], api_key="k")

    assert vectors == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    requests = httpx_mock.get_requests()
    assert len(requests) == 2
    assert all("gemini-embedding-2:embedContent" in str(r.url) for r in requests)
    assert all("key=k" in str(r.url) for r in requests)


def test_to_vector_literal_formato_pgvector():
    assert to_vector_literal([0.1, -2.0, 3]) == "[0.1,-2.0,3]"
