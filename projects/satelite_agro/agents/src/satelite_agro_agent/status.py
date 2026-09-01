"""Instrumentação do rate limiter para expor fila/cota via `GET /status`.

`InMemoryRateLimiter` (LangChain) não expõe quantas chamadas estão esperando
um token — só o estado interno do bucket. `TrackedRateLimiter` embrulha um
limiter real e conta quantas chamadas estão dentro de `acquire`/`aacquire`
neste instante, sem alterar o comportamento de bloqueio (delega tudo pro
limiter interno). Existe só para alimentar um indicador informativo na UI —
não decide nada, não limita nada por conta própria.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from langchain_core.rate_limiters import BaseRateLimiter


@dataclass(frozen=True)
class ModelStatus:
    max_rpm: int
    waiting: int


class TrackedRateLimiter(BaseRateLimiter):
    def __init__(self, inner: BaseRateLimiter, *, max_rpm: int) -> None:
        self._inner = inner
        self._max_rpm = max_rpm
        self._waiting = 0
        self._lock = threading.Lock()

    def acquire(self, *, blocking: bool = True) -> bool:
        with self._lock:
            self._waiting += 1
        try:
            return self._inner.acquire(blocking=blocking)
        finally:
            with self._lock:
                self._waiting -= 1

    async def aacquire(self, *, blocking: bool = True) -> bool:
        with self._lock:
            self._waiting += 1
        try:
            return await self._inner.aacquire(blocking=blocking)
        finally:
            with self._lock:
                self._waiting -= 1

    def snapshot(self) -> ModelStatus:
        with self._lock:
            waiting = self._waiting
        return ModelStatus(max_rpm=self._max_rpm, waiting=waiting)
