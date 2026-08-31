"""Municípios do RS via API de Localidades do IBGE (sem chave).

Fonte da lista canônica de geocodes — o `land_use_municipality` referencia esta
tabela por FK, então qualquer geocode da planilha do MapBiomas que não bater com
o IBGE é reportado em vez de ingerido em silêncio.
"""

from __future__ import annotations

import httpx

from .config import UF_ABBREV, UF_CODE, UF_NAME
from .text import norm

MunicipioRow = tuple[str, str, str, str, str]  # geocode, name, name_norm, state, abbrev


def fetch_municipios(api_base: str, *, timeout: float = 30.0) -> list[MunicipioRow]:
    url = f"{api_base}/api/v1/localidades/estados/{UF_CODE}/municipios"
    resp = httpx.get(url, timeout=timeout)
    resp.raise_for_status()
    return _to_rows(resp.json())


def _to_rows(payload: list[dict]) -> list[MunicipioRow]:
    rows: list[MunicipioRow] = []
    for item in payload:
        geocode = str(item["id"]).strip()
        name = str(item["nome"]).strip()
        rows.append((geocode, name, norm(name), UF_NAME, UF_ABBREV))
    rows.sort(key=lambda r: r[0])
    return rows
