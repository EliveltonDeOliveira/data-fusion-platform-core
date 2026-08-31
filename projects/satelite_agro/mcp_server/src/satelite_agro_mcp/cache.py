"""Cache curto (Redis/Valkey) para as chamadas ao vivo.

Só um par get/set com TTL de minutos, chave prefixada por projeto. Sem
persistência: se o cache estiver fora, ele não age — a ferramenta ainda responde.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Protocol

KEY_PREFIX = "satelite_agro:weather:"
DEFAULT_TTL_SECONDS = 600  # 10 min


class AsyncRedisLike(Protocol):
    async def get(self, key: str) -> Any: ...
    async def set(self, key: str, value: str, ex: int | None = None) -> Any: ...


def make_key(*parts: Any) -> str:
    raw = "|".join(json.dumps(p, sort_keys=True, default=str) for p in parts)
    digest = hashlib.sha1(raw.encode()).hexdigest()  # noqa: S324 - não é uso de segurança
    return f"{KEY_PREFIX}{digest}"


class Cache:
    def __init__(
        self,
        redis: AsyncRedisLike | None,
        *,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> None:
        self._redis = redis
        self._ttl = ttl_seconds

    @classmethod
    def from_env(cls) -> Cache:
        url = os.environ.get("VALKEY_URL")
        ttl = int(os.environ.get("WEATHER_CACHE_TTL", DEFAULT_TTL_SECONDS))
        if not url:
            return cls(None, ttl_seconds=ttl)
        from redis.asyncio import from_url

        return cls(from_url(url, decode_responses=True), ttl_seconds=ttl)

    async def get_json(self, key: str) -> dict[str, Any] | None:
        if self._redis is None:
            return None
        try:
            raw = await self._redis.get(key)
        except Exception:  # noqa: BLE001 - cache indisponível nunca quebra a resposta
            return None
        return json.loads(raw) if raw else None

    async def set_json(self, key: str, value: dict[str, Any]) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.set(key, json.dumps(value, default=str), ex=self._ttl)
        except Exception:  # noqa: BLE001
            return
