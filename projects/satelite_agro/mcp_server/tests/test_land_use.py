"""Tools de uso da terra — lógica pura, sem rede e sem banco real.

O Postgres é substituído por um fake com fila de result sets; o raster por um
GeoTIFF sintético pequeno (rasterio + numpy) gravado em tmp_path.
"""

from __future__ import annotations

import numpy as np
import psycopg
import pytest
import rasterio
from affine import Affine

from satelite_agro_mcp.land_use import (
    _norm,
    _strip_region_wording,
    get_land_use_at_point,
    get_land_use_change,
    get_land_use_raster_overlay,
    get_land_use_summary,
    get_land_use_timeseries,
)

# --------------------------------------------------------------------------- #
# fake do Postgres


class _FakeCursor:
    def __init__(self, conn: FakeConn) -> None:
        self._conn = conn

    async def __aenter__(self) -> _FakeCursor:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def execute(self, sql: str, params: object = None) -> None:
        self._conn.executed.append((sql, params))
        if self._conn.raises is not None:
            raise self._conn.raises
        self._conn.current = self._conn.results.pop(0) if self._conn.results else []

    async def fetchall(self) -> list:
        return list(self._conn.current)

    async def fetchone(self):
        return self._conn.current[0] if self._conn.current else None


class FakeConn:
    def __init__(self, *results: list, raises: Exception | None = None) -> None:
        self.results = list(results)
        self.raises = raises
        self.executed: list = []
        self.current: list = []

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self)


SANTA_MARIA_ROW = {
    "geocode": "4316907",
    "name": "Santa Maria",
    "state": "Rio Grande do Sul",
    "state_abbrev": "RS",
}
AGG_ROWS = [
    {"label": "Agricultura", "code": "3.2", "area_ha": 63934.0},
    {"label": "Formação Campestre", "code": "2.1", "area_ha": 52185.0},
    {"label": "Formação Florestal", "code": "1.1", "area_ha": 29166.0},
]
LEGEND_PASTAGEM = {
    "class_id": 15,
    "name_pt": "Pastagem",
    "label": "Pastagem",
    "code": "3.1",
    "level_1_pt": "Agropecuária",
    "level_2_pt": "Pastagem",
    "level_3_pt": None,
    "level_4_pt": None,
}


# --------------------------------------------------------------------------- #
# raster sintético


@pytest.fixture
def raster(tmp_path):
    """4x4 uint8, cobre lon [-54,-53] x lat [-30,-29], pixel 0.25°. arr[1,2] = 15."""
    arr = np.zeros((4, 4), dtype="uint8")
    arr[1, 2] = 15  # Pastagem
    path = tmp_path / "rs_coverage_2025.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=4,
        width=4,
        count=1,
        dtype="uint8",
        crs="EPSG:4326",
        transform=Affine(0.25, 0.0, -54.0, 0.0, -0.25, -29.0),
        nodata=0,
    ) as dst:
        dst.write(arr, 1)
    return path


# --------------------------------------------------------------------------- #
# _strip_region_wording


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("região de Santa Maria", "santa maria"),
        ("Região Metropolitana de Porto Alegre", "porto alegre"),
        ("Pelotas/RS", "pelotas"),
        ("Santa Maria, Rio Grande do Sul", "santa maria"),
        ("  Porto  Alegre  ", "porto alegre"),
    ],
)
def test_strip_region_wording(raw, expected):
    assert _strip_region_wording(_norm(raw)) == expected


# --------------------------------------------------------------------------- #
# get_land_use_summary


async def test_summary_municipio():
    conn = FakeConn([SANTA_MARIA_ROW], AGG_ROWS)
    out = await get_land_use_summary("região de Santa Maria", 2025, 2, conn=conn)

    assert out.available
    assert out.location is not None
    assert out.location.kind == "municipality"
    assert out.location.geocode == "4316907"
    assert out.year == 2025
    assert out.level == 2
    assert out.classes[0].label == "Agricultura"
    assert out.total_area_ha == pytest.approx(145285.0, abs=0.1)
    assert out.classes[0].area_pct == pytest.approx(63934.0 / 145285.0 * 100, abs=0.01)
    assert sum(c.area_pct for c in out.classes) == pytest.approx(100.0, abs=0.05)


async def test_summary_estado_nao_resolve_municipio():
    conn = FakeConn(AGG_ROWS)  # só a query de agregação; sem lookup de município
    out = await get_land_use_summary("RS", 2024, 1, conn=conn)

    assert out.available
    assert out.location is not None
    assert out.location.kind == "state"
    # a primeira (e única) query foi a de agregação, não um SELECT em ibge_municipio
    assert "ibge_municipio" not in conn.executed[0][0]
    assert "lu.geocode" not in conn.executed[0][0]


async def test_summary_municipio_desconhecido():
    conn = FakeConn([])  # lookup não acha nada
    out = await get_land_use_summary("Balneário Camboriú", 2025, 2, conn=conn)

    assert not out.available
    assert out.location is None
    assert any("não é um município reconhecido" in n for n in out.notes)


async def test_summary_nivel_invalido_nao_consulta():
    conn = FakeConn([SANTA_MARIA_ROW], AGG_ROWS)
    out = await get_land_use_summary("Santa Maria", 2025, 9, conn=conn)

    assert not out.available
    assert conn.executed == []
    assert any("nível inválido" in n for n in out.notes)


async def test_summary_ano_fora_da_faixa():
    conn = FakeConn([SANTA_MARIA_ROW], AGG_ROWS)
    out = await get_land_use_summary("Santa Maria", 1970, 2, conn=conn)

    assert not out.available
    assert conn.executed == []
    assert any("1985 a 2025" in n for n in out.notes)


async def test_summary_banco_indisponivel():
    conn = FakeConn(raises=psycopg.OperationalError("connection refused"))
    out = await get_land_use_summary("Santa Maria", 2025, 2, conn=conn)

    assert not out.available
    assert any("indisponível" in n for n in out.notes)


async def test_summary_nivel_no_sql():
    conn = FakeConn([SANTA_MARIA_ROW], AGG_ROWS)
    await get_land_use_summary("Santa Maria", 2025, 4, conn=conn)
    agg_sql = conn.executed[1][0]
    assert "level_4_pt" in agg_sql
    assert "level_4_code" in agg_sql


# --------------------------------------------------------------------------- #
# get_land_use_at_point


async def test_point_classe_encontrada(raster):
    conn = FakeConn([LEGEND_PASTAGEM])
    out = await get_land_use_at_point(-29.4, -53.4, 2025, 2, conn=conn, raster_path=raster)

    assert out.available
    assert out.class_id == 15
    assert out.label == "Pastagem"
    assert out.code == "3.1"
    assert out.name_pt == "Pastagem"
    assert out.hierarchy == {
        "level_1": "Agropecuária",
        "level_2": "Pastagem",
        "level_3": None,
        "level_4": None,
    }
    assert conn.executed[0][1] == {"cid": 15}


async def test_point_sem_observacao(raster):
    conn = FakeConn([LEGEND_PASTAGEM])
    out = await get_land_use_at_point(-29.1, -53.9, 2025, 2, conn=conn, raster_path=raster)

    assert not out.available
    assert out.class_id == 0
    assert conn.executed == []  # nem consulta a legenda
    assert any("Não Observado" in n for n in out.notes)


async def test_point_fora_da_grade(raster):
    conn = FakeConn([LEGEND_PASTAGEM])
    out = await get_land_use_at_point(10.0, 10.0, 2025, 2, conn=conn, raster_path=raster)

    assert not out.available
    assert out.class_id is None
    assert any("fora da área coberta" in n for n in out.notes)


async def test_point_ano_sem_raster(raster):
    conn = FakeConn([LEGEND_PASTAGEM])
    out = await get_land_use_at_point(-29.4, -53.4, 2020, 2, conn=conn, raster_path=raster)

    assert not out.available
    assert conn.executed == []
    assert any("get_land_use_summary" in n for n in out.notes)


async def test_point_raster_ausente(tmp_path):
    conn = FakeConn([LEGEND_PASTAGEM])
    out = await get_land_use_at_point(
        -53.4, -29.4, 2025, 2, conn=conn, raster_path=tmp_path / "nao_existe.tif"
    )

    assert not out.available
    assert any("não está montado" in n for n in out.notes)


# --------------------------------------------------------------------------- #
# get_land_use_change

CHANGE_ROWS = [
    {"label": "Agricultura", "code": "3.2", "year": 1990, "area_ha": 40000.0},
    {"label": "Agricultura", "code": "3.2", "year": 2020, "area_ha": 64000.0},
    {"label": "Formação Campestre", "code": "2.1", "year": 1990, "area_ha": 60000.0},
    {"label": "Formação Campestre", "code": "2.1", "year": 2020, "area_ha": 52000.0},
    {"label": "Formação Florestal", "code": "1.1", "year": 1990, "area_ha": 30000.0},
]


async def test_change_variacao_medida():
    conn = FakeConn([SANTA_MARIA_ROW], CHANGE_ROWS)
    out = await get_land_use_change("Santa Maria", 1990, 2020, 2, conn=conn)

    assert out.available
    assert out.year_from == 1990
    assert out.year_to == 2020
    assert out.location is not None and out.location.kind == "municipality"
    # ordenado por |delta_ha|: Agricultura +24000, Campestre -8000, Florestal -30000
    assert out.classes[0].label == "Formação Florestal"
    assert out.classes[0].delta_ha == pytest.approx(-30000.0, abs=0.1)
    agricultura = next(c for c in out.classes if c.label == "Agricultura")
    assert agricultura.area_from_ha == pytest.approx(40000.0, abs=0.1)
    assert agricultura.area_to_ha == pytest.approx(64000.0, abs=0.1)
    assert agricultura.delta_ha == pytest.approx(24000.0, abs=0.1)
    assert out.total_area_from_ha == pytest.approx(130000.0, abs=0.1)
    assert out.total_area_to_ha == pytest.approx(116000.0, abs=0.1)


async def test_change_estado_nao_resolve_municipio():
    conn = FakeConn(CHANGE_ROWS)
    out = await get_land_use_change("Rio Grande do Sul", 1990, 2020, 2, conn=conn)

    assert out.available
    assert out.location is not None and out.location.kind == "state"
    assert "ibge_municipio" not in conn.executed[0][0]
    assert conn.executed[0][1] == {"yf": 1990, "yt": 2020}


async def test_change_ano_fora_da_faixa():
    conn = FakeConn([SANTA_MARIA_ROW], CHANGE_ROWS)
    out = await get_land_use_change("Santa Maria", 1970, 2020, 2, conn=conn)

    assert not out.available
    assert conn.executed == []
    assert any("1985 a 2025" in n for n in out.notes)


async def test_change_anos_iguais():
    conn = FakeConn([SANTA_MARIA_ROW], CHANGE_ROWS)
    out = await get_land_use_change("Santa Maria", 2020, 2020, 2, conn=conn)

    assert not out.available
    assert conn.executed == []
    assert any("anos diferentes" in n for n in out.notes)


async def test_change_nivel_invalido_nao_consulta():
    conn = FakeConn([SANTA_MARIA_ROW], CHANGE_ROWS)
    out = await get_land_use_change("Santa Maria", 1990, 2020, 9, conn=conn)

    assert not out.available
    assert conn.executed == []
    assert any("nível inválido" in n for n in out.notes)


async def test_change_municipio_desconhecido():
    conn = FakeConn([])
    out = await get_land_use_change("Londrina", 1990, 2020, 2, conn=conn)

    assert not out.available
    assert out.location is None
    assert any("não é um município reconhecido" in n for n in out.notes)


async def test_change_banco_indisponivel():
    conn = FakeConn(raises=psycopg.OperationalError("connection refused"))
    out = await get_land_use_change("Santa Maria", 1990, 2020, 2, conn=conn)

    assert not out.available
    assert any("indisponível" in n for n in out.notes)


async def test_change_nivel_no_sql():
    conn = FakeConn([SANTA_MARIA_ROW], CHANGE_ROWS)
    await get_land_use_change("Santa Maria", 1990, 2020, 3, conn=conn)
    agg_sql = conn.executed[1][0]
    assert "level_3_pt" in agg_sql
    assert "lu.year IN" in agg_sql


TIMESERIES_ROWS = [
    {"label": "Agricultura", "code": "3.2", "year": 1985, "area_ha": 30000.0},
    {"label": "Formação Campestre", "code": "2.1", "year": 1985, "area_ha": 70000.0},
    {"label": "Agricultura", "code": "3.2", "year": 2025, "area_ha": 64000.0},
    {"label": "Formação Campestre", "code": "2.1", "year": 2025, "area_ha": 52000.0},
]


async def test_timeseries_serie_completa_por_classe():
    conn = FakeConn([SANTA_MARIA_ROW], TIMESERIES_ROWS)
    out = await get_land_use_timeseries("Santa Maria", 2, conn=conn)

    assert out.available
    assert out.year_from == 1985
    assert out.year_to == 2025
    assert out.location is not None and out.location.kind == "municipality"
    agricultura = next(c for c in out.classes if c.label == "Agricultura")
    assert [p.year for p in agricultura.points] == [1985, 2025]
    assert agricultura.points[0].area_ha == pytest.approx(30000.0, abs=0.1)
    assert agricultura.points[0].area_pct == pytest.approx(30.0, abs=0.1)  # 30000/100000
    assert agricultura.points[1].area_pct == pytest.approx(55.17, abs=0.1)  # 64000/116000


async def test_timeseries_estado_nao_resolve_municipio():
    conn = FakeConn(TIMESERIES_ROWS)
    out = await get_land_use_timeseries("Rio Grande do Sul", 2, conn=conn)

    assert out.available
    assert out.location is not None and out.location.kind == "state"
    assert "ibge_municipio" not in conn.executed[0][0]
    assert conn.executed[0][1] == {}


async def test_timeseries_nivel_invalido_nao_consulta():
    conn = FakeConn([SANTA_MARIA_ROW], TIMESERIES_ROWS)
    out = await get_land_use_timeseries("Santa Maria", 9, conn=conn)

    assert not out.available
    assert conn.executed == []
    assert any("nível inválido" in n for n in out.notes)


async def test_timeseries_municipio_desconhecido():
    conn = FakeConn([])
    out = await get_land_use_timeseries("Londrina", 2, conn=conn)

    assert not out.available
    assert out.location is None
    assert any("não é um município reconhecido" in n for n in out.notes)


async def test_timeseries_banco_indisponivel():
    conn = FakeConn(raises=psycopg.OperationalError("connection refused"))
    out = await get_land_use_timeseries("Santa Maria", 2, conn=conn)

    assert not out.available
    assert any("indisponível" in n for n in out.notes)


async def test_timeseries_nivel_no_sql():
    conn = FakeConn([SANTA_MARIA_ROW], TIMESERIES_ROWS)
    await get_land_use_timeseries("Santa Maria", 3, conn=conn)
    agg_sql = conn.executed[1][0]
    assert "level_3_pt" in agg_sql
    assert "ORDER BY 3" in agg_sql


# --------------------------------------------------------------------------- #
# get_land_use_raster_overlay

LEGEND_COLORS_ROWS = [
    {"class_id": 0, "hex_color": "#ffffff"},  # Não Observado -- vira transparente
    {"class_id": 15, "hex_color": "#ffd966"},  # Pastagem -- é a classe do pixel [1,2] do fixture
]


async def test_overlay_ano_invalido_nao_toca_no_banco_nem_no_raster(raster):
    conn = FakeConn([])
    out = await get_land_use_raster_overlay(2020, conn=conn, raster_path=raster)

    assert not out.available
    assert conn.executed == []
    assert any("2025" in n for n in out.notes)


async def test_overlay_raster_ausente(tmp_path):
    conn = FakeConn([])
    out = await get_land_use_raster_overlay(conn=conn, raster_path=tmp_path / "nao-existe.tif")

    assert not out.available
    assert conn.executed == []
    assert any("não está montado" in n for n in out.notes)


async def test_overlay_legenda_banco_indisponivel(raster):
    conn = FakeConn(raises=psycopg.OperationalError("connection refused"))
    out = await get_land_use_raster_overlay(conn=conn, raster_path=raster)

    assert not out.available
    assert any("indisponível" in n for n in out.notes)


async def test_overlay_gera_imagem_com_bounds_e_dimensoes_corretas(raster):
    import base64
    from io import BytesIO

    from PIL import Image

    conn = FakeConn(LEGEND_COLORS_ROWS)
    out = await get_land_use_raster_overlay(max_dim=4, conn=conn, raster_path=raster)

    assert out.available
    assert out.width == 4
    assert out.height == 4
    # fixture: left=-54, top=-29, pixel 0.25°, 4x4 -> right=-53, bottom=-30
    assert out.bounds == pytest.approx([-54.0, -30.0, -53.0, -29.0])

    png = Image.open(BytesIO(base64.b64decode(out.image_base64)))
    assert png.size == (4, 4)
    assert png.mode == "RGBA"
    # pixel [1,2] (linha 1, coluna 2) = Pastagem, cor oficial + alpha 200
    assert png.getpixel((2, 1)) == (0xFF, 0xD9, 0x66, 200)
    # pixel [0,0] = "Não Observado" (class_id=0) -- transparente, não branco opaco
    assert png.getpixel((0, 0))[3] == 0


async def test_overlay_max_dim_reduz_resolucao_preservando_proporcao(raster):
    conn = FakeConn(LEGEND_COLORS_ROWS)
    out = await get_land_use_raster_overlay(max_dim=2, conn=conn, raster_path=raster)

    assert out.available
    assert out.width == 2
    assert out.height == 2
    # bounds geográficos não mudam com a decimação -- só a resolução da imagem
    assert out.bounds == pytest.approx([-54.0, -30.0, -53.0, -29.0])
