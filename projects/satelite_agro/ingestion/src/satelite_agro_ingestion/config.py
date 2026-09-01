"""Configuração da ingestão, lida do ambiente.

Nada de segredo embutido. `DATABASE_URL` e os caminhos vêm do ambiente de
execução; os defaults assumem um layout de container (`/data/raw` para os
arquivos baixados manualmente, `/data/derived` para a saída).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Região piloto. RS = código 43 do IBGE.
UF_CODE = "43"
UF_NAME = "Rio Grande do Sul"
UF_ABBREV = "RS"

# Coleção do MapBiomas em uso (ver migration 000002).
MAPBIOMAS_COLLECTION = 11


@dataclass(frozen=True)
class Settings:
    database_url: str
    raw_dir: Path
    derived_dir: Path
    target_year: int
    ibge_api_base: str
    malha_quality: str
    coverage_raster: str
    stats_xlsx: str
    legend_csv: str
    gemini_api_key: str

    @classmethod
    def from_env(cls) -> Settings:
        url = os.environ.get("DATABASE_URL", "").strip()
        if not url:
            raise RuntimeError("DATABASE_URL é obrigatório para a ingestão.")
        return cls(
            database_url=url,
            raw_dir=Path(os.environ.get("RAW_DIR", "/data/raw")),
            derived_dir=Path(os.environ.get("DERIVED_DIR", "/data/derived")),
            target_year=int(os.environ.get("TARGET_YEAR", "2025")),
            ibge_api_base=os.environ.get(
                "IBGE_API_BASE", "https://servicodados.ibge.gov.br"
            ).rstrip("/"),
            malha_quality=os.environ.get("MALHA_QUALITY", "intermediaria"),
            coverage_raster=os.environ.get("COVERAGE_RASTER", "brazil_coverage-col11_2025.tif"),
            stats_xlsx=os.environ.get(
                "STATS_XLSX", "MAPBIOMAS_BRAZIL-COL.11-BIOME_STATE_MUNICIPALITY.xlsx"
            ),
            legend_csv=os.environ.get(
                "LEGEND_CSV", "legend_code_mapbiomas_brazil_collection_11.csv"
            ),
            gemini_api_key=os.environ.get("GEMINI_API_KEY", "").strip(),
        )

    def raw(self, name: str) -> Path:
        return self.raw_dir / name

    @property
    def clipped_raster_path(self) -> Path:
        return self.derived_dir / f"rs_coverage_{self.target_year}.tif"
