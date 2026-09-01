from __future__ import annotations

import pytest

from satelite_agro_mcp.cache import Cache
from satelite_agro_mcp.openmeteo import OpenMeteoClient
from satelite_agro_mcp.regions import resolve_region, resolve_region_point

from .samples import NO_RESULTS, PORTO_ALEGRE, SAO_PAULO


async def _resolve(query: str):
    async with OpenMeteoClient() as client:
        return await resolve_region(query, client)


async def test_municipio_no_rs(geo):
    geo(PORTO_ALEGRE)
    r = await _resolve("Porto Alegre")
    assert r.available
    assert r.location is not None
    assert r.location.admin1 == "Rio Grande do Sul"
    assert not r.location.is_state_level
    assert abs(r.location.latitude + 30.03306) < 1e-6


@pytest.mark.parametrize("q", ["Rio Grande do Sul", "RS", "rio grande do sul, Brasil"])
async def test_estado_inteiro_sem_geocoding(q):
    # não passa pelo geocoding (Open-Meteo não indexa UF) — usa o centroide fixo
    r = await _resolve(q)
    assert r.available
    assert r.location is not None
    assert r.location.is_state_level
    assert (r.location.latitude, r.location.longitude) == (-29.75, -53.30)
    assert any("ponto representativo" in n for n in r.notes)


async def test_fora_do_rs(geo):
    geo(SAO_PAULO)
    r = await _resolve("São Paulo")
    assert not r.available
    assert r.location is None
    assert any("fora do escopo" in n.lower() for n in r.notes)


async def test_lugar_inexistente(geo):
    geo(NO_RESULTS)
    r = await _resolve("Xyzzyville")
    assert not r.available
    assert any("brasil" in n.lower() for n in r.notes)


async def test_vazio():
    r = await _resolve("   ")
    assert not r.available


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.store[key] = value


async def test_resolve_region_point_municipio(geo):
    geo(PORTO_ALEGRE)
    r = await resolve_region_point("Porto Alegre")
    assert r.available
    assert r.location is not None
    assert abs(r.location.latitude + 30.03306) < 1e-6


async def test_resolve_region_point_usa_o_cache(geo):
    geo(PORTO_ALEGRE)
    redis = _FakeRedis()
    cache = Cache(redis, ttl_seconds=600)

    r1 = await resolve_region_point("Porto Alegre", cache=cache)
    # 2ª chamada não bate no geocoding de novo (httpx_mock só registrou 1
    # resposta) -- se o cache não tivesse funcionado, isso estouraria.
    r2 = await resolve_region_point("Porto Alegre", cache=cache)

    assert r1 == r2
    assert len(redis.store) == 1
