"""Cliente HTTP para as APIs abertas do Open-Meteo.

Três endpoints, todos sem chave e sem cadastro:
- geocoding: nome de lugar -> coordenadas
- forecast:  dado recente/atual + até 92 dias para trás
- archive:   série histórica (desde 1940)
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# `past_days` do endpoint forecast vai no máximo até 92.
MAX_FORECAST_PAST_DAYS = 92


class OpenMeteoError(RuntimeError):
    """Falha de rede ou resposta de erro do Open-Meteo."""


class OpenMeteoClient:
    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        timeout: float = 10.0,
        retries: int = 2,
    ) -> None:
        self._client = client
        self._owns_client = client is None
        self._timeout = timeout
        self._retries = retries

    async def __aenter__(self) -> OpenMeteoClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _get(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        if self._client is None:  # uso fora do context manager
            self._client = httpx.AsyncClient(timeout=self._timeout)

        last_exc: Exception | None = None
        for attempt in range(self._retries + 1):
            try:
                resp = await self._client.get(url, params=params)
                break
            except httpx.TransportError as exc:  # connect/read/timeout — transitório
                last_exc = exc
                if attempt < self._retries:
                    await asyncio.sleep(0.5 * (attempt + 1))
            except httpx.HTTPError as exc:
                raise OpenMeteoError(f"falha ao chamar {url}: {exc!r}") from exc
        else:
            raise OpenMeteoError(
                f"Open-Meteo indisponível após {self._retries + 1} tentativas ({url}): {last_exc!r}"
            ) from last_exc

        if resp.status_code >= 400:
            raise OpenMeteoError(f"{url} respondeu {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        if isinstance(data, dict) and data.get("error"):
            raise OpenMeteoError(str(data.get("reason", "erro do Open-Meteo")))
        return data

    async def geocode(self, name: str, *, count: int = 10) -> list[dict[str, Any]]:
        data = await self._get(
            GEOCODING_URL,
            {"name": name, "count": count, "language": "pt", "format": "json"},
        )
        return list(data.get("results") or [])

    async def forecast(
        self,
        *,
        latitude: float,
        longitude: float,
        past_days: int,
        daily: list[str] | None = None,
        hourly: list[str] | None = None,
        current: list[str] | None = None,
        timezone: str = "America/Sao_Paulo",
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "latitude": latitude,
            "longitude": longitude,
            "past_days": min(past_days, MAX_FORECAST_PAST_DAYS),
            "forecast_days": 1,
            "timezone": timezone,
        }
        if daily:
            params["daily"] = ",".join(daily)
        if hourly:
            params["hourly"] = ",".join(hourly)
        if current:
            params["current"] = ",".join(current)
        return await self._get(FORECAST_URL, params)

    async def archive(
        self,
        *,
        latitude: float,
        longitude: float,
        start_date: str,
        end_date: str,
        daily: list[str] | None = None,
        hourly: list[str] | None = None,
        timezone: str = "America/Sao_Paulo",
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "latitude": latitude,
            "longitude": longitude,
            "start_date": start_date,
            "end_date": end_date,
            "timezone": timezone,
        }
        if daily:
            params["daily"] = ",".join(daily)
        if hourly:
            params["hourly"] = ",".join(hourly)
        return await self._get(ARCHIVE_URL, params)
