from __future__ import annotations

from satelite_agro_mcp.embeddings import embed_query, to_vector_literal


async def test_embed_query(httpx_mock):
    httpx_mock.add_response(json={"embedding": {"values": [0.1, 0.2, 0.3]}})
    vector = await embed_query("como e classificado o pampa", api_key="k")
    assert vector == [0.1, 0.2, 0.3]
    request = httpx_mock.get_requests()[0]
    assert "gemini-embedding-2:embedContent" in str(request.url)
    assert "key=k" in str(request.url)


def test_to_vector_literal():
    assert to_vector_literal([0.1, -2.0, 3]) == "[0.1,-2.0,3]"
