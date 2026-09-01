"""Cliente do embedding hospedado do Gemini (`gemini-embedding-2`).

Chamada de ingestão, uma vez por trecho do corpus: não é geração de texto — o
mesmo trecho sempre produz o mesmo vetor (determinístico o suficiente pra não
quebrar a filosofia de ingestão sem raciocínio de LLM). Modelo de 3072
dimensões; limites de requisição checados antes de virar dependência.
`_MIN_INTERVAL_SECONDS` espaça as chamadas com folga sob o teto por minuto.
"""

from __future__ import annotations

import time
from collections.abc import Iterable

import httpx

MODEL = "gemini-embedding-2"
_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
_MIN_INTERVAL_SECONDS = 0.7


def embed_texts(
    texts: Iterable[str],
    *,
    api_key: str,
    client: httpx.Client | None = None,
) -> list[list[float]]:
    own_client = client is None
    active = client or httpx.Client(timeout=30.0)
    try:
        vectors: list[list[float]] = []
        for i, text in enumerate(texts):
            if i:
                time.sleep(_MIN_INTERVAL_SECONDS)
            vectors.append(_embed_one(active, text, api_key))
        return vectors
    finally:
        if own_client:
            active.close()


def _embed_one(client: httpx.Client, text: str, api_key: str) -> list[float]:
    resp = client.post(
        f"{_BASE_URL}/models/{MODEL}:embedContent",
        params={"key": api_key},
        json={"content": {"parts": [{"text": text}]}},
    )
    resp.raise_for_status()
    return resp.json()["embedding"]["values"]


def to_vector_literal(values: list[float]) -> str:
    """Formato de texto que o pgvector aceita direto na entrada COPY: `[v1,v2,...]`."""
    return "[" + ",".join(str(v) for v in values) + "]"
