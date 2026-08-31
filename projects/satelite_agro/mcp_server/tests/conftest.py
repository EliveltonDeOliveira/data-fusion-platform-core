from __future__ import annotations

import pytest

from .samples import GEO_URL


@pytest.fixture
def geo(httpx_mock):
    """Registra uma resposta para a chamada de geocoding."""

    def _add(payload: dict):
        httpx_mock.add_response(url=GEO_URL, json=payload)

    return _add
