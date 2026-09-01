from __future__ import annotations

import asyncio
import threading
import time

from satelite_agro_agent.status import ModelStatus, TrackedRateLimiter


class _FakeLimiter:
    """Não bloqueia de verdade; deixa o teste controlar quando `acquire` retorna."""

    def __init__(self) -> None:
        self.release = threading.Event()

    def acquire(self, *, blocking: bool = True) -> bool:
        self.release.wait(timeout=1)
        return True

    async def aacquire(self, *, blocking: bool = True) -> bool:
        while not self.release.is_set():
            await asyncio.sleep(0.01)
        return True


def test_snapshot_inicial_sem_espera():
    tracked = TrackedRateLimiter(_FakeLimiter(), max_rpm=10)
    assert tracked.snapshot() == ModelStatus(max_rpm=10, waiting=0)


def test_acquire_conta_como_esperando_enquanto_bloqueado():
    fake = _FakeLimiter()
    tracked = TrackedRateLimiter(fake, max_rpm=10)

    t = threading.Thread(target=tracked.acquire)
    t.start()
    time.sleep(0.05)  # dá tempo do acquire entrar no bloqueio simulado

    assert tracked.snapshot().waiting == 1

    fake.release.set()
    t.join(timeout=1)
    assert tracked.snapshot().waiting == 0


async def test_aacquire_conta_como_esperando_enquanto_bloqueado():
    fake = _FakeLimiter()
    tracked = TrackedRateLimiter(fake, max_rpm=10)

    task = asyncio.create_task(tracked.aacquire())
    await asyncio.sleep(0.05)

    assert tracked.snapshot().waiting == 1

    fake.release.set()
    await task
    assert tracked.snapshot().waiting == 0


def test_delega_resultado_do_acquire():
    class _DenyOnce:
        def acquire(self, *, blocking: bool = True) -> bool:
            return False

    tracked = TrackedRateLimiter(_DenyOnce(), max_rpm=10)
    assert tracked.acquire(blocking=False) is False
    assert tracked.snapshot().waiting == 0
