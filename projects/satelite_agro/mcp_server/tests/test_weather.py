from __future__ import annotations

from datetime import date

import pytest

from satelite_agro_mcp.weather import _parse_period, get_weather_trend

from .samples import FORECAST_URL, PORTO_ALEGRE, SANTA_MARIA, SAO_PAULO, daily_forecast, hourly_now

TODAY = date(2026, 8, 31)


# --------------------------------------------------------------------------- #
# parsing de período (sem rede)


@pytest.mark.parametrize(
    "period,mode,start",
    [
        ("7d", "range", date(2026, 8, 25)),
        ("7", "range", date(2026, 8, 25)),
        ("30 dias", "range", date(2026, 8, 2)),
        ("now", "now", date(2026, 8, 29)),
        ("agora", "now", date(2026, 8, 29)),
    ],
)
def test_parse_period_relativo(period, mode, start):
    rng = _parse_period(period, TODAY)
    assert rng.mode == mode
    assert rng.start == start
    assert rng.end == TODAY


def test_parse_period_iso_range():
    rng = _parse_period("2026-08-01/2026-08-10", TODAY)
    assert rng.mode == "range"
    assert rng.start == date(2026, 8, 1)
    assert rng.end == date(2026, 8, 10)


def test_parse_period_range_futuro_clipado():
    rng = _parse_period("2026-08-20/2027-01-01", TODAY)
    assert rng.start == date(2026, 8, 20)
    assert rng.end == TODAY


# --------------------------------------------------------------------------- #
# get_weather_trend


async def test_tendencia_diaria(geo, httpx_mock):
    geo(PORTO_ALEGRE)
    httpx_mock.add_response(url=FORECAST_URL, json=daily_forecast(7))

    wt = await get_weather_trend(
        "Porto Alegre",
        "7d",
        "daily",
        variables=["temperature", "precipitation", "evapotranspiration", "soil_moisture"],
        today=TODAY,
    )

    assert wt.available
    assert wt.period is not None and wt.period.endpoint == "forecast"
    measures = {s.measure for s in wt.series}
    assert "temperature_2m_mean" in measures
    assert "precipitation_sum" in measures
    assert not any(s.variable == "soil_moisture" for s in wt.series)
    assert any("horária" in n for n in wt.notes)

    chuva = next(s for s in wt.summary if s.measure == "precipitation_sum")
    assert chuva.total == pytest.approx(21.6, abs=0.01)
    temp = next(s for s in wt.summary if s.measure == "temperature_2m_mean")
    assert temp.mean is not None and temp.total is None


async def test_agora_horario_com_solo(geo, httpx_mock):
    geo(SANTA_MARIA)
    httpx_mock.add_response(url=FORECAST_URL, json=hourly_now())

    wt = await get_weather_trend("Santa Maria", "now", today=TODAY)

    assert wt.available
    assert wt.granularity == "hourly"
    assert wt.period is not None and wt.period.mode == "now"
    assert wt.current is not None
    assert wt.current["temperature_2m"] == pytest.approx(21.4)
    assert wt.current["soil_moisture_3_to_9cm"] == pytest.approx(0.35)


async def test_regiao_fora_do_rs(geo):
    geo(SAO_PAULO)
    wt = await get_weather_trend("São Paulo", "7d", today=TODAY)
    assert not wt.available
    assert wt.series == []
    assert any("fora do escopo" in n.lower() for n in wt.notes)


async def test_variavel_desconhecida_ignorada(geo, httpx_mock):
    geo(PORTO_ALEGRE)
    httpx_mock.add_response(url=FORECAST_URL, json=daily_forecast(7))
    wt = await get_weather_trend(
        "Porto Alegre", "7d", "daily", variables=["temperature", "banana"], today=TODAY
    )
    assert wt.available
    assert any("banana" in n for n in wt.notes)


# --------------------------------------------------------------------------- #
# integração real (rodar com: pytest -m live)


@pytest.mark.live
async def test_live_porto_alegre():
    wt = await get_weather_trend(
        "Porto Alegre", "7d", "daily", variables=["temperature", "precipitation"]
    )
    assert wt.available
    assert wt.location and wt.location.admin1 == "Rio Grande do Sul"
    assert any(s.points for s in wt.series)


@pytest.mark.live
async def test_live_umidade_solo_agora():
    wt = await get_weather_trend("Santa Maria", "now", variables=["soil_moisture"])
    assert wt.available and wt.current
