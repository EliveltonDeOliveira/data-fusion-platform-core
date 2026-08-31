from __future__ import annotations

import argparse

import pytest
from satelite_agro_ingestion.__main__ import STEPS, _selected_steps, main


def _ns(only=(), skip=()):
    return argparse.Namespace(only=list(only), skip=list(skip))


def test_default_roda_tudo_em_ordem():
    assert _selected_steps(_ns()) == list(STEPS)


def test_only_preserva_ordem_canonica():
    assert _selected_steps(_ns(only=["raster", "legend"])) == ["legend", "raster"]


def test_skip():
    assert _selected_steps(_ns(skip=["raster"])) == ["legend", "municipios", "land-use"]


def test_main_exige_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        main([])
