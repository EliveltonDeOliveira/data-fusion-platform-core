from __future__ import annotations

from typing import Any

import pytest

from satelite_agro_agent import server


class StubAgent:
    """Fica no lugar do grafo real: devolve uma lista de mensagens fixa ou levanta."""

    def __init__(self, messages: list[Any] | None = None, *, raises: Exception | None = None):
        self._messages = messages or []
        self._raises = raises

    async def ainvoke(self, _inputs: dict) -> dict:
        if self._raises is not None:
            raise self._raises
        return {"messages": self._messages}


@pytest.fixture(autouse=True)
def _clear_state():
    server._state.clear()
    yield
    server._state.clear()
