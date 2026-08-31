"""Confere o seed da legenda (migration 000002) contra o CSV oficial em
`data/raw/`. A legenda vive em SQL (é referência fixa); esta etapa só garante
que o seed não divergiu do arquivo publicado pelo MapBiomas.

O CSV traz as 33 classes-folha; o seed tem essas + nós de agregação (Nível 1 e
intermediários). Portanto a checagem é unidirecional: CSV ⊆ seed.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class LegendReport:
    csv_classes: int = 0
    missing_in_db: list[int] = field(default_factory=list)
    hex_mismatch: list[str] = field(default_factory=list)
    name_mismatch: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.missing_in_db and not self.hex_mismatch


def _norm_name(value: str) -> str:
    return " ".join(value.strip().lower().split())


def read_legend_csv(path: Path) -> dict[int, tuple[str, str]]:
    """class_id -> (name_pt, hex_color_lower)."""
    out: dict[int, tuple[str, str]] = {}
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            cid = int(row["class_id"])
            out[cid] = (row["class_name_pt_br"].strip(), row["hex_code"].strip().lower())
    return out


def validate_legend(csv_path: Path, db_legend: dict[int, tuple[str, str]]) -> LegendReport:
    """db_legend: class_id -> (name_pt, hex_color) já lido do Postgres."""
    csv_legend = read_legend_csv(csv_path)
    report = LegendReport(csv_classes=len(csv_legend))

    for cid, (csv_name, csv_hex) in sorted(csv_legend.items()):
        if cid not in db_legend:
            report.missing_in_db.append(cid)
            continue
        db_name, db_hex = db_legend[cid]
        if (db_hex or "").lower() != csv_hex:
            report.hex_mismatch.append(f"{cid}: seed={db_hex!r} csv={csv_hex!r}")
        if _norm_name(db_name) != _norm_name(csv_name):
            report.name_mismatch.append(f"{cid}: seed={db_name!r} csv={csv_name!r}")

    return report
