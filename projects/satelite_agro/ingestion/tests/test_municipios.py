from __future__ import annotations

from satelite_agro_ingestion.municipios import _to_rows

PAYLOAD = [
    {"id": 4314902, "nome": "Porto Alegre"},
    {"id": 4300034, "nome": "Aceguá"},
    {"id": 4316907, "nome": "Santa Maria"},
]


def test_to_rows_normaliza_e_ordena():
    rows = _to_rows(PAYLOAD)
    assert [r[0] for r in rows] == ["4300034", "4314902", "4316907"]
    acegua = rows[0]
    assert acegua == ("4300034", "Aceguá", "acegua", "Rio Grande do Sul", "RS")


def test_to_rows_geocode_sempre_string():
    rows = _to_rows([{"id": 4314902, "nome": "Porto Alegre"}])
    assert isinstance(rows[0][0], str)
