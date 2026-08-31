from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from satelite_agro_ingestion.raster import clip_raster, fetch_uf_boundary


def _make_raster(path: Path, crs: str = "EPSG:4326") -> None:
    # grade 10x10 começando em (lon=-54, lat=-29), pixel de 0.1 grau
    data = np.arange(100, dtype="uint8").reshape(10, 10)
    transform = from_origin(-54.0, -29.0, 0.1, 0.1)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=10,
        width=10,
        count=1,
        dtype="uint8",
        crs=crs,
        transform=transform,
        nodata=0,
    ) as dst:
        dst.write(data, 1)


def _square(lon0: float, lat0: float, lon1: float, lat1: float) -> dict:
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [lon0, lat0],
                [lon1, lat0],
                [lon1, lat1],
                [lon0, lat1],
                [lon0, lat0],
            ]
        ],
    }


def test_clip_recorta_e_mantem_crs(tmp_path: Path):
    national = tmp_path / "nat.tif"
    _make_raster(national)
    # recorta a metade superior-esquerda (~5x5 pixels)
    geom = _square(-54.0, -29.5, -53.5, -29.0)
    result = clip_raster(national, [geom], tmp_path / "out" / "rs.tif")

    assert result.crs == "EPSG:4326"
    assert result.width < 10 and result.height < 10
    assert result.out_path.exists()
    assert national.exists()  # nacional preservado
    with rasterio.open(result.out_path) as ds:
        assert ds.profile["compress"] == "lzw"
        assert ds.nodata == 0


def test_clip_rejeita_crs_diferente(tmp_path: Path):
    national = tmp_path / "nat3857.tif"
    _make_raster(national, crs="EPSG:3857")
    with pytest.raises(ValueError, match="EPSG:4326"):
        clip_raster(national, [_square(-54, -29.5, -53.5, -29)], tmp_path / "o.tif")


def test_fetch_uf_boundary(httpx_mock):
    httpx_mock.add_response(
        json={
            "type": "FeatureCollection",
            "features": [
                {
                    "geometry": {"type": "Polygon", "coordinates": [[[0, 0]]]},
                    "properties": {"codarea": "43"},
                },
            ],
        },
    )
    geoms = fetch_uf_boundary("https://example.test", "intermediaria")
    assert geoms == [{"type": "Polygon", "coordinates": [[[0, 0]]]}]


def test_fetch_uf_boundary_vazio(httpx_mock):
    httpx_mock.add_response(json={"type": "FeatureCollection", "features": []})
    with pytest.raises(ValueError, match="nenhuma geometria"):
        fetch_uf_boundary("https://example.test", "intermediaria")
