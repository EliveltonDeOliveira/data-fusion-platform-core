from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import Workbook
from satelite_agro_ingestion.land_use import LandUseStats, stream_land_use

HEADER = [
    "ID",
    "country",
    "biome",
    "region",
    "state",
    "geocode",
    "municipality",
    "municipality-state",
    "class",
    "class_level_0",
    "class_level_1",
    "class_level_2",
    "class_level_3",
    "class_level_4",
    "y2023",
    "y2024",
    "y2025",
]

KNOWN = {"4314902", "4316907", "4200051"}


def _row(state, geocode, klass, y2023, y2024, y2025, biome="Pampa"):
    return [
        0,
        "Brasil",
        biome,
        "Sul",
        state,
        geocode,
        "Muni",
        f"Muni - {state}",
        klass,
        "Anthropic",
        "x",
        "x",
        "x",
        "x",
        y2023,
        y2024,
        y2025,
    ]


def _xlsx(tmp_path: Path, rows) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "COVERAGE_11"
    ws.append(HEADER)
    for r in rows:
        ws.append(r)
    p = tmp_path / "stats.xlsx"
    wb.save(p)
    return p


def _run(path, class_ids, stats, *, known=KNOWN):
    return list(
        stream_land_use(
            path,
            state_name="Rio Grande do Sul",
            legend_class_ids=class_ids,
            known_geocodes=known,
            stats=stats,
        )
    )


def test_filtra_estado_e_derrete_anos(tmp_path: Path):
    path = _xlsx(
        tmp_path,
        [
            _row("Rio Grande do Sul", "4314902", 15, 100.0, 110.0, 120.0),
            _row("Santa Catarina", "4200051", 15, 999.0, 999.0, 999.0),
        ],
    )
    stats = LandUseStats()
    rows = _run(path, {15}, stats)
    assert rows == [
        ("4314902", 15, 2023, 100.0),
        ("4314902", 15, 2024, 110.0),
        ("4314902", 15, 2025, 120.0),
    ]
    assert stats.skipped_other_state == 1
    assert stats.municipios == {"4314902"}
    assert stats.years == {2023, 2024, 2025}


def test_soma_area_entre_biomas_do_mesmo_municipio(tmp_path: Path):
    path = _xlsx(
        tmp_path,
        [
            _row("Rio Grande do Sul", "4316907", 15, 100.0, 0.0, 0.0, biome="Pampa"),
            _row("Rio Grande do Sul", "4316907", 15, 30.0, 0.0, 0.0, biome="Mata Atlântica"),
        ],
    )
    stats = LandUseStats()
    rows = _run(path, {15}, stats)
    assert rows == [("4316907", 15, 2023, 130.0)]
    assert stats.biomes == {"Pampa", "Mata Atlântica"}
    assert stats.cells_summed == 2
    assert stats.rows_emitted == 1


def test_omite_celulas_nulas_e_nao_positivas(tmp_path: Path):
    path = _xlsx(tmp_path, [_row("Rio Grande do Sul", "4314902", 39, 0.0, None, 42.5)])
    stats = LandUseStats()
    assert _run(path, {39}, stats) == [("4314902", 39, 2025, 42.5)]


def test_class_id_desconhecido_vira_report(tmp_path: Path):
    path = _xlsx(tmp_path, [_row("Rio Grande do Sul", "4314902", 999, 1.0, 1.0, 1.0)])
    stats = LandUseStats()
    assert _run(path, {15}, stats) == []
    assert stats.unknown_class_ids == {999}
    assert not stats.ok


def test_geocode_fora_da_malha_e_pulado(tmp_path: Path):
    path = _xlsx(
        tmp_path,
        [
            _row("Rio Grande do Sul", "4300001", 33, 5000.0, 0.0, 0.0),  # Lagoa dos Patos
            _row("Rio Grande do Sul", "4314902", 33, 10.0, 0.0, 0.0),
        ],
    )
    stats = LandUseStats()
    rows = _run(path, {33}, stats)
    assert rows == [("4314902", 33, 2023, 10.0)]
    assert stats.unknown_geocodes == {"4300001"}


def test_sem_coluna_de_ano_falha(tmp_path: Path):
    wb = Workbook()
    ws = wb.active
    ws.title = "COVERAGE_11"
    ws.append(["state", "geocode", "class"])
    ws.append(["Rio Grande do Sul", "4314902", 15])
    p = tmp_path / "bad.xlsx"
    wb.save(p)
    with pytest.raises(ValueError, match="coluna de ano"):
        _run(p, {15}, LandUseStats())
