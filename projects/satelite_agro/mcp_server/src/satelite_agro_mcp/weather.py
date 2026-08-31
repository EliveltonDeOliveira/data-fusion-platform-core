"""`get_weather_trend` — série climática atual/recente para uma região do RS.

Fonte: Open-Meteo ao vivo (sem chave), com cache curto. Determinístico, sem LLM.
Variáveis agro-relevantes — temperatura, precipitação, evapotranspiração
(ET₀ FAO), umidade e temperatura do solo por profundidade.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from pydantic import BaseModel

from .cache import Cache, make_key
from .openmeteo import MAX_FORECAST_PAST_DAYS, OpenMeteoClient
from .regions import ResolvedLocation, resolve_region

Granularity = Literal["daily", "hourly"]

DEFAULT_VARIABLES = (
    "temperature",
    "precipitation",
    "evapotranspiration",
    "soil_moisture",
    "soil_temperature",
)


@dataclass(frozen=True)
class VarSpec:
    unit: str
    daily: tuple[str, ...]
    hourly: tuple[str, ...]
    aggregate: Literal["mean", "sum"] = "mean"
    hourly_only: bool = False


VARIABLES: dict[str, VarSpec] = {
    "temperature": VarSpec(
        unit="°C",
        daily=("temperature_2m_mean", "temperature_2m_min", "temperature_2m_max"),
        hourly=("temperature_2m",),
    ),
    "precipitation": VarSpec(
        unit="mm",
        daily=("precipitation_sum",),
        hourly=("precipitation",),
        aggregate="sum",
    ),
    "evapotranspiration": VarSpec(
        unit="mm",
        daily=("et0_fao_evapotranspiration",),
        hourly=("et0_fao_evapotranspiration",),
        aggregate="sum",
    ),
    "soil_moisture": VarSpec(
        unit="m³/m³",
        daily=(),
        hourly=(
            "soil_moisture_0_to_1cm",
            "soil_moisture_1_to_3cm",
            "soil_moisture_3_to_9cm",
            "soil_moisture_9_to_27cm",
            "soil_moisture_27_to_81cm",
        ),
        hourly_only=True,
    ),
    "soil_temperature": VarSpec(
        unit="°C",
        daily=(),
        hourly=(
            "soil_temperature_0cm",
            "soil_temperature_6cm",
            "soil_temperature_18cm",
            "soil_temperature_54cm",
        ),
        hourly_only=True,
    ),
}

_CURRENT_CAPABLE = {"temperature_2m", "precipitation", "et0_fao_evapotranspiration"}


class DataPoint(BaseModel):
    t: str
    value: float | None


class Series(BaseModel):
    variable: str
    measure: str
    unit: str
    points: list[DataPoint]


class SeriesSummary(BaseModel):
    variable: str
    measure: str
    unit: str
    mean: float | None = None
    min: float | None = None
    max: float | None = None
    total: float | None = None


class PeriodInfo(BaseModel):
    mode: Literal["now", "range"]
    start: date
    end: date
    endpoint: Literal["forecast", "archive"]
    label: str


class WeatherTrend(BaseModel):
    region_query: str
    available: bool
    location: ResolvedLocation | None = None
    granularity: Granularity = "daily"
    period: PeriodInfo | None = None
    current: dict[str, float] | None = None
    series: list[Series] = []
    summary: list[SeriesSummary] = []
    source: str = "open-meteo"
    notes: list[str] = []


# --------------------------------------------------------------------------- #
# parsing de período


@dataclass
class _Range:
    start: date
    end: date
    mode: Literal["now", "range"]


_REL_RE = re.compile(r"^\s*(\d{1,4})\s*(d|dias?|days?)?\s*$", re.IGNORECASE)
_ISO_RANGE_RE = re.compile(
    r"^\s*(\d{4}-\d{2}-\d{2})\s*(?:/|\.\.|\sa\s|\sto\s)\s*(\d{4}-\d{2}-\d{2})\s*$",
    re.IGNORECASE,
)


def _parse_period(period: str, today: date) -> _Range:
    p = period.strip().lower()
    if p in {"now", "agora", "atual", "current"}:
        return _Range(today - timedelta(days=2), today, "now")

    m = _ISO_RANGE_RE.match(period)
    if m:
        start = date.fromisoformat(m.group(1))
        end = min(date.fromisoformat(m.group(2)), today)
        if end < start:
            start, end = end, start
        return _Range(start, end, "range")

    m = _REL_RE.match(p)
    days = int(m.group(1)) if m else 7
    days = max(1, min(days, 3650))
    return _Range(today - timedelta(days=days - 1), today, "range")


def _label(rng: _Range) -> str:
    if rng.mode == "now":
        return "agora"
    return f"{rng.start.isoformat()} a {rng.end.isoformat()}"


# --------------------------------------------------------------------------- #
# extração das séries


def _rows(block: dict, key: str) -> tuple[list[str], list[float | None]]:
    times = block.get("time") or []
    values = block.get(key) or []
    return times, values


def _clip(times: list[str], values: list[float | None], start: date, end: date) -> list[DataPoint]:
    out: list[DataPoint] = []
    for t, v in zip(times, values, strict=False):
        d = date.fromisoformat(t[:10])
        if start <= d <= end:
            out.append(DataPoint(t=t, value=v))
    return out


def _summ(
    variable: str, measure: str, unit: str, spec: VarSpec, pts: list[DataPoint]
) -> SeriesSummary:
    nums = [p.value for p in pts if p.value is not None]
    s = SeriesSummary(variable=variable, measure=measure, unit=unit)
    if nums:
        s.mean = round(sum(nums) / len(nums), 3)
        s.min = round(min(nums), 3)
        s.max = round(max(nums), 3)
        if spec.aggregate == "sum":
            s.total = round(sum(nums), 3)
    return s


# --------------------------------------------------------------------------- #
# entrada principal


async def get_weather_trend(
    region: str,
    period: str = "7d",
    granularity: Granularity = "daily",
    variables: list[str] | None = None,
    *,
    client: OpenMeteoClient | None = None,
    cache: Cache | None = None,
    today: date | None = None,
) -> WeatherTrend:
    today = today or datetime.now(UTC).date()
    wanted = list(variables) if variables else list(DEFAULT_VARIABLES)
    unknown = [v for v in wanted if v not in VARIABLES]
    wanted = [v for v in wanted if v in VARIABLES]

    rng = _parse_period(period, today)
    effective_gran: Granularity = "hourly" if rng.mode == "now" else granularity

    cache_key = make_key("weather_trend", region, period, effective_gran, sorted(wanted))
    if cache is not None:
        hit = await cache.get_json(cache_key)
        if hit is not None:
            return WeatherTrend.model_validate(hit)

    own_client = client is None
    client = client or OpenMeteoClient()
    try:
        resolution = await resolve_region(region, client)
        notes: list[str] = list(resolution.notes)
        for u in unknown:
            notes.append(f"variável desconhecida ignorada: '{u}'")

        if not resolution.available or resolution.location is None:
            result = WeatherTrend(
                region_query=region,
                available=False,
                granularity=effective_gran,
                notes=notes or [f"não foi possível resolver a região '{region}'"],
            )
            if cache is not None:
                await cache.set_json(cache_key, result.model_dump(mode="json"))
            return result

        loc = resolution.location

        # monta a lista de measures do Open-Meteo
        daily_params: list[str] = []
        hourly_params: list[str] = []
        measure_map: list[tuple[str, str]] = []  # (variável amigável, measure)
        for v in wanted:
            spec = VARIABLES[v]
            if effective_gran == "daily":
                if spec.hourly_only or not spec.daily:
                    notes.append(
                        f"'{v}' só existe em granularidade horária no Open-Meteo; "
                        f"use granularity='hourly'."
                    )
                    continue
                for m in spec.daily:
                    daily_params.append(m)
                    measure_map.append((v, m))
            else:
                for m in spec.hourly:
                    hourly_params.append(m)
                    measure_map.append((v, m))

        endpoint: Literal["forecast", "archive"]
        past_days = (today - rng.start).days
        if past_days <= MAX_FORECAST_PAST_DAYS:
            endpoint = "forecast"
            current_params = (
                [p for p in hourly_params if p in _CURRENT_CAPABLE] if rng.mode == "now" else None
            )
            data = await client.forecast(
                latitude=loc.latitude,
                longitude=loc.longitude,
                past_days=max(past_days, 1),
                daily=daily_params or None,
                hourly=hourly_params or None,
                current=current_params or None,
            )
        else:
            endpoint = "archive"
            data = await client.archive(
                latitude=loc.latitude,
                longitude=loc.longitude,
                start_date=rng.start.isoformat(),
                end_date=rng.end.isoformat(),
                daily=daily_params or None,
                hourly=hourly_params or None,
            )

        block = data.get("daily" if effective_gran == "daily" else "hourly") or {}
        series: list[Series] = []
        summary: list[SeriesSummary] = []
        for variable, measure in measure_map:
            spec = VARIABLES[variable]
            times, values = _rows(block, measure)
            pts = _clip(times, values, rng.start, rng.end)
            unit = spec.unit
            series.append(Series(variable=variable, measure=measure, unit=unit, points=pts))
            summary.append(_summ(variable, measure, unit, spec, pts))

        current: dict[str, float] | None = None
        if rng.mode == "now":
            current = {}
            cur_block = data.get("current") or {}
            for _variable, measure in measure_map:
                if measure in cur_block and isinstance(cur_block[measure], (int, float)):
                    current[measure] = float(cur_block[measure])
            # para as variáveis sem `current` (solo), pega o último horário válido
            for s in series:
                if s.measure not in current:
                    last = next((p.value for p in reversed(s.points) if p.value is not None), None)
                    if last is not None:
                        current[s.measure] = float(last)
            notes.append("valores de 'agora' são a leitura horária mais recente disponível.")

        if not any(s.points for s in series) and not current:
            notes.append(
                "o Open-Meteo não retornou dados para essa combinação de região/período/variáveis."
            )

        result = WeatherTrend(
            region_query=region,
            available=True,
            location=loc,
            granularity=effective_gran,
            period=PeriodInfo(
                mode=rng.mode,
                start=rng.start,
                end=rng.end,
                endpoint=endpoint,
                label=_label(rng),
            ),
            current=current,
            series=series,
            summary=summary,
            notes=notes,
        )
        if cache is not None:
            await cache.set_json(cache_key, result.model_dump(mode="json"))
        return result
    finally:
        if own_client:
            await client.__aexit__()
