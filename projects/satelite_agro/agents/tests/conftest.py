from __future__ import annotations

from typing import Any

import pytest

from satelite_agro_agent import server


class StubAgent:
    """Fica no lugar do grafo compilado: devolve um state final fixo ou levanta."""

    def __init__(self, result: dict[str, Any] | None = None, *, raises: Exception | None = None):
        self._result = result or {}
        self._raises = raises
        self.role_models = {"supervisor": "m-a", "clima": "m-b", "uso_terra": "m-a"}

    async def ainvoke(self, _inputs: dict) -> dict:
        if self._raises is not None:
            raise self._raises
        return self._result


@pytest.fixture(autouse=True)
def _clear_state():
    server._state.clear()
    yield
    server._state.clear()
