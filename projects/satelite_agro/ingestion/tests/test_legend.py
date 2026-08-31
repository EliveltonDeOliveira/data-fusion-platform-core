from __future__ import annotations

from pathlib import Path

from satelite_agro_ingestion.legend import read_legend_csv, validate_legend

CSV = (
    "class_id,class_name_pt_br,class_name_en,hex_code\n"
    "3,Formação Florestal,Forest Formation,#1f8d49\n"
    "15,Pastagem,Pasture,#edde8e\n"
    "39,Soja,Soybean,#f5b3c8\n"
)


def _write(tmp_path: Path) -> Path:
    p = tmp_path / "legend.csv"
    p.write_text(CSV, encoding="utf-8")
    return p


def test_read_legend_csv(tmp_path: Path):
    legend = read_legend_csv(_write(tmp_path))
    assert legend[39] == ("Soja", "#f5b3c8")
    assert set(legend) == {3, 15, 39}


def test_validate_ok_with_extra_seed_rows(tmp_path: Path):
    db_legend = {
        0: ("Não Observado", "#ffffff"),  # nó extra no seed — não é erro
        3: ("Formação Florestal", "#1f8d49"),
        15: ("Pastagem", "#edde8e"),
        39: ("Soja", "#f5b3c8"),
    }
    report = validate_legend(_write(tmp_path), db_legend)
    assert report.ok
    assert report.csv_classes == 3


def test_validate_flags_missing_and_hex(tmp_path: Path):
    db_legend = {
        3: ("Formação Florestal", "#1f8d49"),
        15: ("Pastagem", "#000000"),  # hex errado
        # 39 ausente
    }
    report = validate_legend(_write(tmp_path), db_legend)
    assert not report.ok
    assert report.missing_in_db == [39]
    assert any("15:" in m for m in report.hex_mismatch)


def test_validate_name_mismatch_is_warning_only(tmp_path: Path):
    db_legend = {
        3: ("Formacao Florestal (typo)", "#1f8d49"),
        15: ("Pastagem", "#edde8e"),
        39: ("Soja", "#f5b3c8"),
    }
    report = validate_legend(_write(tmp_path), db_legend)
    assert report.ok  # nome não derruba
    assert report.name_mismatch
