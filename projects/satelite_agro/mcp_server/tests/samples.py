"""Payloads de exemplo e padrões de URL para os testes."""

from __future__ import annotations

import re

GEO_URL = re.compile(r"https://geocoding-api\.open-meteo\.com/.*")
FORECAST_URL = re.compile(r"https://api\.open-meteo\.com/v1/forecast.*")
ARCHIVE_URL = re.compile(r"https://archive-api\.open-meteo\.com/.*")

PORTO_ALEGRE = {
    "results": [
        {
            "name": "Porto Alegre",
            "latitude": -30.03306,
            "longitude": -51.23,
            "country_code": "BR",
            "country": "Brasil",
            "admin1": "Rio Grande do Sul",
            "admin2": "Porto Alegre",
            "population": 1409351,
            "feature_code": "PPLA",
        }
    ]
}

SANTA_MARIA = {
    "results": [
        {
            "name": "Santa Maria",
            "latitude": -29.68417,
            "longitude": -53.80694,
            "country_code": "BR",
            "country": "Brasil",
            "admin1": "Rio Grande do Sul",
            "admin2": "Santa Maria",
            "population": 260000,
            "feature_code": "PPLA2",
        }
    ]
}

RIO_GRANDE_DO_SUL = {
    "results": [
        {
            "name": "Rio Grande do Sul",
            "latitude": -30.0,
            "longitude": -53.5,
            "country_code": "BR",
            "country": "Brasil",
            "admin1": "Rio Grande do Sul",
            "population": 11000000,
            "feature_code": "ADM1",
        }
    ]
}

SAO_PAULO = {
    "results": [
        {
            "name": "São Paulo",
            "latitude": -23.5475,
            "longitude": -46.63611,
            "country_code": "BR",
            "country": "Brasil",
            "admin1": "São Paulo",
            "population": 10021295,
            "feature_code": "PPLA",
        }
    ]
}

NO_RESULTS: dict = {"generationtime_ms": 0.3}


def daily_forecast(days: int = 7) -> dict:
    times = [f"2026-08-{25 + i:02d}" for i in range(days)]
    return {
        "daily": {
            "time": times,
            "temperature_2m_mean": [18.0 + i * 0.5 for i in range(days)],
            "temperature_2m_min": [12.0 + i * 0.3 for i in range(days)],
            "temperature_2m_max": [25.0 + i * 0.4 for i in range(days)],
            "precipitation_sum": [0.0, 5.2, 12.1, 0.0, 3.3, 0.0, 1.0][:days],
            "et0_fao_evapotranspiration": [3.1, 2.8, 1.9, 3.4, 2.2, 3.0, 2.7][:days],
        }
    }


def hourly_now() -> dict:
    times = [f"2026-08-31T{h:02d}:00" for h in range(0, 24, 3)]
    n = len(times)
    return {
        "current": {
            "time": "2026-08-31T15:00",
            "temperature_2m": 21.4,
            "precipitation": 0.0,
        },
        "hourly": {
            "time": times,
            "temperature_2m": [16 + i for i in range(n)],
            "precipitation": [0.0] * n,
            "et0_fao_evapotranspiration": [0.1 * i for i in range(n)],
            "soil_moisture_0_to_1cm": [0.31] * n,
            "soil_moisture_1_to_3cm": [0.33] * n,
            "soil_moisture_3_to_9cm": [0.35] * n,
            "soil_moisture_9_to_27cm": [0.37] * n,
            "soil_moisture_27_to_81cm": [0.40] * n,
            "soil_temperature_0cm": [14 + i for i in range(n)],
            "soil_temperature_6cm": [15] * n,
            "soil_temperature_18cm": [16] * n,
            "soil_temperature_54cm": [17] * n,
        },
    }
