"""Tools de uso e cobertura da terra — MapBiomas Coleção 11 (Rio Grande do Sul).

Duas entradas, ambas informativas (dado + contexto, nunca recomendação):

- `get_land_use_summary(region, year, level)` - composicao de classes de uma
  regiao, lida do Postgres local (pre-agregado por municipio, classe e ano,
  1985-2025). "Regiao de X" resolve para o municipio X e, opcionalmente, o
  estado inteiro - sem buffer de vizinhos, sem calculo zonal ao vivo.
- `get_land_use_at_point(lat, lon, year, level)` - classe de um ponto, por
  leitura de 1 pixel do raster do RS ja recortado. So o ano da demo (2025) tem
  raster; fora disso, ou fora do RS, responde `available=false`.

`level` (1 a 4, padrao 2) e sempre explicito: a hierarquia canonica vem da tabela
`mapbiomas_legend`, e a consulta faz "carry down" (do nível pedido para o mais
profundo disponível na classe). Nunca agrega ou desagrega em silêncio.
"""

from __future__ import annotations

import asyncio
import os
import unicodedata
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import psycopg
from pydantic import BaseModel

from . import db

# Faixa de anos do dado tabular no Postgres (planilha de Estatísticas MapBiomas).
MIN_YEAR = 1985
MAX_YEAR = 2025
# Único ano com raster do RS recortado e montado no serviço.
RASTER_YEAR = 2025

SOURCE = "MapBiomas Coleção 11"

_DB_UNAVAILABLE = (
    RuntimeError,
    OSError,
    psycopg.OperationalError,
    psycopg.errors.InsufficientPrivilege,
    psycopg.errors.UndefinedTable,
)

_STATE_ALIASES = {
    "rs",
    "rio grande do sul",
    "estado do rio grande do sul",
    "rio grande do sul (estado)",
}
_REGION_PREFIXES = (
    "regiao metropolitana de ",
    "regiao metropolitana da ",
    "regiao metropolitana do ",
    "regiao de ",
    "regiao do ",
    "regiao da ",
    "municipio de ",
    "municipio da ",
    "municipio do ",
    "cidade de ",
    "area de ",
    "entorno de ",
    "arredores de ",
)
_STATE_SUFFIXES = (
    ", rio grande do sul",
    " rio grande do sul",
    ", rs",
    " rs",
    "/rs",
    " (rs)",
    ", brasil",
    " brasil",
)


class LandUseClass(BaseModel):
    code: str | None
    label: str
    area_ha: float
    area_pct: float


class LandUseLocation(BaseModel):
    query: str
    kind: Literal["municipality", "state"]
    name: str
    geocode: str | None = None
    state: str = "Rio Grande do Sul"
    state_abbrev: str = "RS"


class LandUseSummary(BaseModel):
    region_query: str
    available: bool
    location: LandUseLocation | None = None
    year: int | None = None
    level: int = 2
    total_area_ha: float | None = None
    classes: list[LandUseClass] = []
    source: str = SOURCE
    notes: list[str] = []


class LandUsePoint(BaseModel):
    available: bool
    point: dict[str, float] | None = None
    year: int | None = None
    level: int = 2
    class_id: int | None = None
    code: str | None = None
    label: str | None = None
    name_pt: str | None = None
    hierarchy: dict[str, str | None] | None = None
    source: str = SOURCE
    notes: list[str] = []


class LandUseYearPoint(BaseModel):
    year: int
    area_ha: float
    area_pct: float


class LandUseTimeseriesClass(BaseModel):
    code: str | None
    label: str
    points: list[LandUseYearPoint] = []


class LandUseTimeseries(BaseModel):
    region_query: str
    available: bool
    location: LandUseLocation | None = None
    level: int = 2
    year_from: int = MIN_YEAR
    year_to: int = MAX_YEAR
    classes: list[LandUseTimeseriesClass] = []
    source: str = SOURCE
    notes: list[str] = []


class LandUseChangeClass(BaseModel):
    code: str | None
    label: str
    area_from_ha: float
    area_to_ha: float
    delta_ha: float
    delta_pct_points: float  # variação da participação da classe, em pontos percentuais


class LandUseChange(BaseModel):
    region_query: str
    available: bool
    location: LandUseLocation | None = None
    year_from: int | None = None
    year_to: int | None = None
    level: int = 2
    total_area_from_ha: float | None = None
    total_area_to_ha: float | None = None
    classes: list[LandUseChangeClass] = []
    source: str = SOURCE
    notes: list[str] = []


# --------------------------------------------------------------------------- #
# helpers


def _norm(value: str) -> str:
    stripped = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return " ".join(stripped.lower().split())


def _strip_region_wording(name_norm: str) -> str:
    out = name_norm
    for suffix in _STATE_SUFFIXES:
        if out.endswith(suffix):
            out = out[: -len(suffix)].strip(" ,/")
    changed = True
    while changed:
        changed = False
        for prefix in _REGION_PREFIXES:
            if out.startswith(prefix):
                out = out[len(prefix) :].strip()
                changed = True
    return out


def _validate_level(level: int) -> int | None:
    return level if level in (1, 2, 3, 4) else None


def _label_sql(level: int) -> str:
    parts = [f"g.level_{i}_pt" for i in range(level, 0, -1)]
    return f"coalesce({', '.join(parts)}, g.name_pt)"


def _code_sql(level: int) -> str:
    parts = [f"g.level_{i}_code" for i in range(level, 1, -1)]
    if not parts:
        return "cast(null as text)"
    if len(parts) == 1:
        return parts[0]
    return f"coalesce({', '.join(parts)})"


@asynccontextmanager
async def _acquire(conn: psycopg.AsyncConnection | None):
    if conn is not None:
        yield conn
    else:
        async with db.connect() as owned:
            yield owned


def _raster_path() -> Path:
    return Path(os.environ.get("RS_COVERAGE_RASTER", "/data/derived/rs_coverage_2025.tif"))


# --------------------------------------------------------------------------- #
# get_land_use_summary


async def _resolve_region(
    conn: psycopg.AsyncConnection, region: str
) -> tuple[LandUseLocation | None, list[str]]:
    q_norm = _strip_region_wording(_norm(region))
    if not q_norm:
        return None, ["região não informada"]

    if q_norm in _STATE_ALIASES:
        return LandUseLocation(query=region, kind="state", name="Rio Grande do Sul"), []

    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT geocode, name, state, state_abbrev "
            "FROM satelite_agro.ibge_municipio WHERE name_norm = %(n)s ORDER BY geocode",
            {"n": q_norm},
        )
        rows = await cur.fetchall()

    if not rows:
        return None, [
            f"'{region}' não é um município reconhecido do Rio Grande do Sul "
            f"(escopo piloto). A consulta cobre os 497 municípios do RS ou o estado inteiro."
        ]
    if len(rows) > 1:
        nomes = ", ".join(f"{r['name']} ({r['geocode']})" for r in rows)
        return None, [f"'{region}' é ambíguo no RS: {nomes}. Especifique o município."]

    r = rows[0]
    loc = LandUseLocation(
        query=region,
        kind="municipality",
        name=r["name"],
        geocode=r["geocode"],
        state=r["state"],
        state_abbrev=r["state_abbrev"],
    )
    return loc, []


async def get_land_use_summary(
    region: str,
    year: int = MAX_YEAR,
    level: int = 2,
    *,
    conn: psycopg.AsyncConnection | None = None,
) -> LandUseSummary:
    lvl = _validate_level(level)
    if lvl is None:
        return LandUseSummary(
            region_query=region,
            available=False,
            level=level,
            notes=[f"nível inválido: {level}. Use 1, 2, 3 ou 4 (padrão 2)."],
        )

    if not (MIN_YEAR <= year <= MAX_YEAR):
        return LandUseSummary(
            region_query=region,
            available=False,
            year=year,
            level=lvl,
            notes=[
                f"o uso da terra do MapBiomas vai de {MIN_YEAR} a {MAX_YEAR}; "
                f"não há dado para {year}."
            ],
        )

    try:
        async with _acquire(conn) as active:
            loc, notes = await _resolve_region(active, region)
            if loc is None:
                return LandUseSummary(
                    region_query=region, available=False, year=year, level=lvl, notes=notes
                )

            where = "lu.year = %(year)s"
            params: dict[str, object] = {"year": year}
            if loc.kind == "municipality":
                where += " AND lu.geocode = %(geocode)s"
                params["geocode"] = loc.geocode

            sql = (
                f"SELECT {_label_sql(lvl)} AS label, {_code_sql(lvl)} AS code, "  # noqa: S608 - nível é int validado
                f"sum(lu.area_ha) AS area_ha "
                f"FROM satelite_agro.land_use_municipality lu "
                f"JOIN satelite_agro.mapbiomas_legend g ON g.class_id = lu.class_id "
                f"WHERE {where} "
                f"GROUP BY 1, 2 ORDER BY area_ha DESC"
            )
            async with active.cursor() as cur:
                await cur.execute(sql, params)
                rows = await cur.fetchall()
    except _DB_UNAVAILABLE as exc:
        return LandUseSummary(
            region_query=region,
            available=False,
            year=year,
            level=lvl,
            notes=[f"consulta de uso da terra indisponível no momento ({type(exc).__name__})."],
        )

    if not rows:
        notes.append(
            f"sem linhas de uso da terra para {loc.name} em {year} — verifique se a "
            f"ingestão do ano foi feita."
        )
        return LandUseSummary(
            region_query=region, available=False, location=loc, year=year, level=lvl, notes=notes
        )

    total = sum(float(r["area_ha"]) for r in rows)
    classes = [
        LandUseClass(
            code=r["code"],
            label=r["label"],
            area_ha=round(float(r["area_ha"]), 1),
            area_pct=round(float(r["area_ha"]) / total * 100, 2) if total else 0.0,
        )
        for r in rows
    ]
    notes.append(
        f"composição por área (hectares) das classes de nível {lvl} do {SOURCE}, "
        f"município{'s' if loc.kind == 'state' else ''} do RS, ano {year}."
    )
    return LandUseSummary(
        region_query=region,
        available=True,
        location=loc,
        year=year,
        level=lvl,
        total_area_ha=round(total, 1),
        classes=classes,
        notes=notes,
    )


# --------------------------------------------------------------------------- #
# get_land_use_at_point


def _read_pixel(path: Path, lat: float, lon: float) -> int | None:
    """Leitura de 1 pixel. `None` = ponto fora da grade do raster."""
    import rasterio
    from rasterio.windows import Window

    with rasterio.open(path) as src:
        row, col = src.index(lon, lat)
        row, col = int(row), int(col)
        if not (0 <= row < src.height and 0 <= col < src.width):
            return None
        arr = src.read(1, window=Window(col, row, 1, 1))
    if arr.size == 0:
        return None
    return int(arr[0, 0])


async def get_land_use_at_point(
    lat: float,
    lon: float,
    year: int = RASTER_YEAR,
    level: int = 2,
    *,
    conn: psycopg.AsyncConnection | None = None,
    raster_path: Path | None = None,
) -> LandUsePoint:
    lvl = _validate_level(level)
    if lvl is None:
        return LandUsePoint(
            available=False, level=level, notes=[f"nível inválido: {level}. Use 1, 2, 3 ou 4."]
        )

    point = {"lat": lat, "lon": lon}
    if year != RASTER_YEAR:
        return LandUsePoint(
            available=False,
            point=point,
            year=year,
            level=lvl,
            notes=[
                f"a consulta por ponto usa o raster do MapBiomas de {RASTER_YEAR} "
                f"(único ano recortado para o RS). Para {year}, use get_land_use_summary "
                f"por município."
            ],
        )

    path = raster_path or _raster_path()
    if not path.exists():
        return LandUsePoint(
            available=False,
            point=point,
            year=year,
            level=lvl,
            notes=["o raster de uso da terra do RS não está montado neste serviço."],
        )

    try:
        class_id = await asyncio.to_thread(_read_pixel, path, lat, lon)
    except OSError as exc:
        return LandUsePoint(
            available=False,
            point=point,
            year=year,
            level=lvl,
            notes=[f"não foi possível ler o raster ({type(exc).__name__})."],
        )

    if class_id is None:
        return LandUsePoint(
            available=False,
            point=point,
            year=year,
            level=lvl,
            notes=["ponto fora da área coberta pelo raster (Rio Grande do Sul, escopo piloto)."],
        )
    if class_id == 0:
        return LandUsePoint(
            available=False,
            point=point,
            year=year,
            level=lvl,
            class_id=0,
            notes=[
                "ponto sem observação no raster (código 0 = 'Não Observado') — "
                "provavelmente fora do Rio Grande do Sul."
            ],
        )

    sql = (
        f"SELECT class_id, name_pt, {_label_sql(lvl)} AS label, {_code_sql(lvl)} AS code, "  # noqa: S608 - nível é int validado
        f"level_1_pt, level_2_pt, level_3_pt, level_4_pt "
        f"FROM satelite_agro.mapbiomas_legend g WHERE class_id = %(cid)s"
    )
    try:
        async with _acquire(conn) as active, active.cursor() as cur:
            await cur.execute(sql, {"cid": class_id})
            row = await cur.fetchone()
    except _DB_UNAVAILABLE as exc:
        return LandUsePoint(
            available=False,
            point=point,
            year=year,
            level=lvl,
            class_id=class_id,
            notes=[f"legenda indisponível no momento ({type(exc).__name__})."],
        )

    if row is None:
        return LandUsePoint(
            available=False,
            point=point,
            year=year,
            level=lvl,
            class_id=class_id,
            notes=[f"código de pixel {class_id} não está na legenda da Coleção 11."],
        )

    return LandUsePoint(
        available=True,
        point=point,
        year=year,
        level=lvl,
        class_id=int(row["class_id"]),
        code=row["code"],
        label=row["label"],
        name_pt=row["name_pt"],
        hierarchy={
            "level_1": row["level_1_pt"],
            "level_2": row["level_2_pt"],
            "level_3": row["level_3_pt"],
            "level_4": row["level_4_pt"],
        },
        notes=[
            f"classe de nível {lvl} do {SOURCE} no ponto ({lat}, {lon}), ano {year}. "
            f"1 pixel (~30 m); a classe da folha é '{row['name_pt']}'."
        ],
    )


# --------------------------------------------------------------------------- #
# get_land_use_change


def _out_of_range(*years: int) -> int | None:
    for y in years:
        if not (MIN_YEAR <= y <= MAX_YEAR):
            return y
    return None


async def get_land_use_change(
    region: str,
    year_from: int,
    year_to: int,
    level: int = 2,
    *,
    conn: psycopg.AsyncConnection | None = None,
) -> LandUseChange:
    """Variação de área por classe entre dois anos. Só a diferença medida — nunca
    causa nem projeção. Mesmo dado pré-agregado do summary (`land_use_municipality`)."""
    lvl = _validate_level(level)
    if lvl is None:
        return LandUseChange(
            region_query=region,
            available=False,
            level=level,
            notes=[f"nível inválido: {level}. Use 1, 2, 3 ou 4 (padrão 2)."],
        )

    bad = _out_of_range(year_from, year_to)
    if bad is not None:
        return LandUseChange(
            region_query=region,
            available=False,
            year_from=year_from,
            year_to=year_to,
            level=lvl,
            notes=[
                f"o uso da terra do MapBiomas vai de {MIN_YEAR} a {MAX_YEAR}; "
                f"não há dado para {bad}."
            ],
        )
    if year_from == year_to:
        return LandUseChange(
            region_query=region,
            available=False,
            year_from=year_from,
            year_to=year_to,
            level=lvl,
            notes=["informe dois anos diferentes para comparar a variação."],
        )

    try:
        async with _acquire(conn) as active:
            loc, notes = await _resolve_region(active, region)
            if loc is None:
                return LandUseChange(
                    region_query=region,
                    available=False,
                    year_from=year_from,
                    year_to=year_to,
                    level=lvl,
                    notes=notes,
                )

            where = "lu.year IN (%(yf)s, %(yt)s)"
            params: dict[str, object] = {"yf": year_from, "yt": year_to}
            if loc.kind == "municipality":
                where += " AND lu.geocode = %(geocode)s"
                params["geocode"] = loc.geocode

            sql = (
                f"SELECT {_label_sql(lvl)} AS label, {_code_sql(lvl)} AS code, "  # noqa: S608 - nível é int validado
                f"lu.year AS year, sum(lu.area_ha) AS area_ha "
                f"FROM satelite_agro.land_use_municipality lu "
                f"JOIN satelite_agro.mapbiomas_legend g ON g.class_id = lu.class_id "
                f"WHERE {where} "
                f"GROUP BY 1, 2, 3"
            )
            async with active.cursor() as cur:
                await cur.execute(sql, params)
                rows = await cur.fetchall()
    except _DB_UNAVAILABLE as exc:
        return LandUseChange(
            region_query=region,
            available=False,
            year_from=year_from,
            year_to=year_to,
            level=lvl,
            notes=[f"consulta de uso da terra indisponível no momento ({type(exc).__name__})."],
        )

    if not rows:
        notes.append(
            f"sem linhas de uso da terra para {loc.name} em {year_from} ou {year_to} — "
            f"verifique se a ingestão dos anos foi feita."
        )
        return LandUseChange(
            region_query=region,
            available=False,
            location=loc,
            year_from=year_from,
            year_to=year_to,
            level=lvl,
            notes=notes,
        )

    by_class: dict[tuple[str | None, str], dict[int, float]] = {}
    for r in rows:
        key = (r["code"], r["label"])
        slot = by_class.setdefault(key, {year_from: 0.0, year_to: 0.0})
        slot[int(r["year"])] += float(r["area_ha"])

    total_from = sum(v[year_from] for v in by_class.values())
    total_to = sum(v[year_to] for v in by_class.values())

    classes = [
        LandUseChangeClass(
            code=code,
            label=label,
            area_from_ha=round(v[year_from], 1),
            area_to_ha=round(v[year_to], 1),
            delta_ha=round(v[year_to] - v[year_from], 1),
            delta_pct_points=round(
                (v[year_to] / total_to * 100 if total_to else 0.0)
                - (v[year_from] / total_from * 100 if total_from else 0.0),
                2,
            ),
        )
        for (code, label), v in by_class.items()
    ]
    classes.sort(key=lambda c: abs(c.delta_ha), reverse=True)

    notes.append(
        f"variação de área (hectares) por classe de nível {lvl} do {SOURCE} entre "
        f"{year_from} e {year_to}, {'estado' if loc.kind == 'state' else 'município'} do RS. "
        f"Apenas a variação medida — não indica causa nem projeta tendência."
    )
    return LandUseChange(
        region_query=region,
        available=True,
        location=loc,
        year_from=year_from,
        year_to=year_to,
        level=lvl,
        total_area_from_ha=round(total_from, 1),
        total_area_to_ha=round(total_to, 1),
        classes=classes,
        notes=notes,
    )


# --------------------------------------------------------------------------- #
# get_land_use_timeseries


async def get_land_use_timeseries(
    region: str,
    level: int = 2,
    *,
    conn: psycopg.AsyncConnection | None = None,
) -> LandUseTimeseries:
    """Série completa 1985-2025, por classe — toda a profundidade histórica
    que o dado tabular tem, numa só consulta (mesma tabela pré-agregada do
    summary/change). Serve pra mostrar tendência de longo prazo, não só
    comparar dois anos."""
    lvl = _validate_level(level)
    if lvl is None:
        return LandUseTimeseries(
            region_query=region,
            available=False,
            level=level,
            notes=[f"nível inválido: {level}. Use 1, 2, 3 ou 4 (padrão 2)."],
        )

    try:
        async with _acquire(conn) as active:
            loc, notes = await _resolve_region(active, region)
            if loc is None:
                return LandUseTimeseries(
                    region_query=region, available=False, level=lvl, notes=notes
                )

            where = "1 = 1"
            params: dict[str, object] = {}
            if loc.kind == "municipality":
                where = "lu.geocode = %(geocode)s"
                params["geocode"] = loc.geocode

            sql = (
                f"SELECT {_label_sql(lvl)} AS label, {_code_sql(lvl)} AS code, "  # noqa: S608 - nível é int validado
                f"lu.year AS year, sum(lu.area_ha) AS area_ha "
                f"FROM satelite_agro.land_use_municipality lu "
                f"JOIN satelite_agro.mapbiomas_legend g ON g.class_id = lu.class_id "
                f"WHERE {where} "
                f"GROUP BY 1, 2, 3 ORDER BY 3"
            )
            async with active.cursor() as cur:
                await cur.execute(sql, params)
                rows = await cur.fetchall()
    except _DB_UNAVAILABLE as exc:
        return LandUseTimeseries(
            region_query=region,
            available=False,
            level=lvl,
            notes=[f"consulta de uso da terra indisponível no momento ({type(exc).__name__})."],
        )

    if not rows:
        notes.append(f"sem série histórica de uso da terra para {loc.name} — verifique a ingestão.")
        return LandUseTimeseries(
            region_query=region, available=False, location=loc, level=lvl, notes=notes
        )

    total_by_year: dict[int, float] = {}
    for r in rows:
        total_by_year[int(r["year"])] = total_by_year.get(int(r["year"]), 0.0) + float(r["area_ha"])

    by_class: dict[tuple[str | None, str], list[LandUseYearPoint]] = {}
    for r in rows:
        year = int(r["year"])
        area = float(r["area_ha"])
        total = total_by_year.get(year, 0.0)
        key = (r["code"], r["label"])
        by_class.setdefault(key, []).append(
            LandUseYearPoint(
                year=year,
                area_ha=round(area, 1),
                area_pct=round(area / total * 100, 2) if total else 0.0,
            )
        )

    classes = [
        LandUseTimeseriesClass(code=code, label=label, points=points)
        for (code, label), points in by_class.items()
    ]
    notes.append(
        f"série de área (hectares) por classe de nível {lvl} do {SOURCE}, "
        f"{'estado' if loc.kind == 'state' else 'município'} do RS, {MIN_YEAR}-{MAX_YEAR}. "
        f"Histórico/tendência — não é leitura do dia."
    )
    return LandUseTimeseries(
        region_query=region,
        available=True,
        location=loc,
        level=lvl,
        year_from=MIN_YEAR,
        year_to=MAX_YEAR,
        classes=classes,
        notes=notes,
    )
