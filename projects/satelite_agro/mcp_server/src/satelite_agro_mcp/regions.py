"""Resolução de região para o escopo piloto: Rio Grande do Sul.

Usa a API de geocoding do próprio Open-Meteo (nome -> coordenadas). A Fase 1
trabalha em cima de um ponto representativo — agregação zonal por área
(recorte com malha do IBGE) é da Fase 2. Por isso a resposta sempre diz qual
ponto foi usado e se ele é o centroide do estado.
"""

from __future__ import annotations

import unicodedata

from pydantic import BaseModel

from .openmeteo import OpenMeteoClient

ADMIN1_RS = "Rio Grande do Sul"
_STATE_ALIASES = {
    "rs",
    "rio grande do sul",
    "estado do rio grande do sul",
    "rio grande do sul (estado)",
}
# A API de geocoding do Open-Meteo indexa só cidades, não unidades federativas.
# Para a consulta a nível de estado usamos o centroide aproximado do RS
# (~região de Júlio de Castilhos). A resposta deixa explícito que é um ponto.
_RS_CENTROID = (-29.75, -53.30)


class ResolvedLocation(BaseModel):
    query: str
    name: str
    admin1: str | None = None
    admin2: str | None = None
    country: str | None = None
    latitude: float
    longitude: float
    is_state_level: bool = False


class RegionResolution(BaseModel):
    """Resultado da resolução. `location` é None quando fora do escopo."""

    available: bool
    location: ResolvedLocation | None = None
    notes: list[str] = []


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return " ".join(text.lower().split())


def _score(result: dict, query_norm: str) -> tuple:
    """Ordena candidatos: nome exato > é RS > populoso."""
    name_exact = _norm(result.get("name", "")) == query_norm
    in_rs = result.get("admin1") == ADMIN1_RS
    population = result.get("population") or 0
    return (name_exact, in_rs, population)


async def resolve_region(query: str, client: OpenMeteoClient) -> RegionResolution:
    q = query.strip()
    if not q:
        return RegionResolution(available=False, notes=["região não informada"])

    q_norm = _norm(q)
    for suffix in (", brasil", ", br", " brasil"):
        if q_norm.endswith(suffix):
            q_norm = q_norm[: -len(suffix)].strip()

    if q_norm in _STATE_ALIASES:
        lat, lon = _RS_CENTROID
        return RegionResolution(
            available=True,
            location=ResolvedLocation(
                query=query,
                name="Rio Grande do Sul",
                admin1=ADMIN1_RS,
                country="Brasil",
                latitude=lat,
                longitude=lon,
                is_state_level=True,
            ),
            notes=[
                "consulta a nível de estado: os valores são de um ponto "
                "representativo do RS (centroide aproximado), não uma média "
                "por área. Recorte por município/estado vem em fase posterior."
            ],
        )

    results = await client.geocode(query)
    br = [r for r in results if r.get("country_code") == "BR"]

    if not br:
        return RegionResolution(
            available=False,
            notes=[
                f"não encontrei '{query}' no Brasil. O escopo desta ferramenta "
                f"é o Rio Grande do Sul."
            ],
        )

    in_rs = [r for r in br if r.get("admin1") == ADMIN1_RS]
    if not in_rs:
        best = max(br, key=lambda r: _score(r, q_norm))
        return RegionResolution(
            available=False,
            notes=[
                f"'{query}' foi localizado em {best.get('admin1') or 'outro estado'} "
                f"({best.get('country')}), fora do escopo piloto (Rio Grande do Sul)."
            ],
        )

    chosen = max(in_rs, key=lambda r: _score(r, q_norm))
    loc = ResolvedLocation(
        query=query,
        name=chosen.get("name", q),
        admin1=chosen.get("admin1"),
        admin2=chosen.get("admin2"),
        country=chosen.get("country"),
        latitude=chosen["latitude"],
        longitude=chosen["longitude"],
    )
    return RegionResolution(available=True, location=loc)
