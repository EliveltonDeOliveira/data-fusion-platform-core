"""Cliente do embedding hospedado do Gemini (`gemini-embedding-2`) — 1 chamada
por pergunta do usuário, não ingestão em lote. Ver `projects/satelite_agro/
ingestion/src/satelite_agro_ingestion/embeddings.py` para a contraparte de
ingestão: cada serviço é um pacote isolado (sem lib compartilhada entre
projeto e serviço), então a duplicação pequena é deliberada.
"""

from __future__ import annotations

import httpx

MODEL = "gemini-embedding-2"
_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


async def embed_query(
    text: str,
    *,
    api_key: str,
    client: httpx.AsyncClient | None = None,
    timeout: float = 15.0,
) -> list[float]:
    own_client = client is None
    active = client or httpx.AsyncClient(timeout=timeout)
    try:
        resp = await active.post(
            f"{_BASE_URL}/models/{MODEL}:embedContent",
            params={"key": api_key},
            json={"content": {"parts": [{"text": text}]}},
        )
        resp.raise_for_status()
        return resp.json()["embedding"]["values"]
    finally:
        if own_client:
            await active.aclose()


def to_vector_literal(values: list[float]) -> str:
    return "[" + ",".join(str(v) for v in values) + "]"
