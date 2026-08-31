"""Recorte do GeoTIFF nacional do MapBiomas para o Rio Grande do Sul.

Baixa a fronteira do RS da API de Malhas do IBGE (GeoJSON, EPSG:4326 — mesmo CRS
do raster do MapBiomas, sem reprojeção), recorta e grava só o RS. O raster
nacional NÃO é copiado para lugar nenhum — fica em `data/raw/` e é o dono quem
decide apagar.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import httpx
import rasterio
from rasterio.mask import mask

from .config import UF_CODE

# 0 = "Não Observado" no MapBiomas — serve de nodata para as bordas do recorte.
CLIP_NODATA = 0


@dataclass
class ClipResult:
    out_path: Path
    width: int
    height: int
    crs: str


def fetch_uf_boundary(api_base: str, quality: str, *, timeout: float = 60.0) -> list[dict]:
    """Geometrias (GeoJSON) da fronteira do RS."""
    url = f"{api_base}/api/v3/malhas/estados/{UF_CODE}"
    params = {"formato": "application/vnd.geo+json", "qualidade": quality}
    resp = httpx.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    payload = resp.json()
    geoms = [feat["geometry"] for feat in payload.get("features", [])]
    if not geoms:
        raise ValueError("malha do IBGE não retornou nenhuma geometria")
    return geoms


def clip_raster(national_tif: Path, geometries: list[dict], out_path: Path) -> ClipResult:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(national_tif) as src:
        if src.crs is None or src.crs.to_epsg() != 4326:
            raise ValueError(f"esperava EPSG:4326 no raster, veio {src.crs}")
        image, transform = mask(src, geometries, crop=True, nodata=CLIP_NODATA)
        profile = src.profile.copy()

    profile.update(
        height=image.shape[1],
        width=image.shape[2],
        transform=transform,
        nodata=CLIP_NODATA,
        compress="lzw",
        tiled=True,
        blockxsize=512,
        blockysize=512,
    )
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(image)

    return ClipResult(
        out_path=out_path,
        width=image.shape[2],
        height=image.shape[1],
        crs="EPSG:4326",
    )
