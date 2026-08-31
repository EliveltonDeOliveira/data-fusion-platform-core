from __future__ import annotations

import pytest

from satelite_agro_agent.agent import SYSTEM_PROMPT, build_rate_limiter
from satelite_agro_agent.config import (
    DEFAULT_MAX_RPM,
    DEFAULT_MCP_URL,
    DEFAULT_MODEL,
    Settings,
)


@pytest.mark.parametrize(
    "trecho",
    [
        "NUNCA recomende",
        "TODO número vem de tool",
        "available: false",
        "previsão do futuro",
        "Rio Grande do Sul",
        "notes",
        "análise causal",
        "monitoramento",
        "MapBiomas",
        "nível 1 a 4",
    ],
)
def test_system_prompt_carrega_as_regras(trecho):
    assert trecho in SYSTEM_PROMPT


def test_settings_exige_chave(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        Settings.from_env()


def test_settings_do_ambiente(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "  abc123  ")
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.delenv("MCP_URL", raising=False)

    s = Settings.from_env()

    assert s.gemini_api_key == "abc123"
    assert s.model == DEFAULT_MODEL
    assert s.mcp_url == DEFAULT_MCP_URL
    assert s.temperature == 0.0


def test_settings_override_modelo(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
    monkeypatch.setenv("MCP_URL", "http://outro:9000/mcp")

    s = Settings.from_env()

    assert s.model == "gemini-3.1-flash-lite"
    assert s.mcp_url == "http://outro:9000/mcp"


def test_default_nunca_e_pro():
    assert "flash-lite" in DEFAULT_MODEL
    assert "pro" not in DEFAULT_MODEL.lower()


def test_rate_limiter_respeita_o_teto():
    s = Settings(gemini_api_key="k", max_rpm=12)
    rl = build_rate_limiter(s)
    assert rl.requests_per_second == pytest.approx(12 / 60.0)
    # sem rajada: teto rigido
    assert rl.max_bucket_size == 1


def test_max_rpm_do_ambiente(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("GEMINI_MAX_RPM", "8")
    assert Settings.from_env().max_rpm == 8


@pytest.mark.parametrize("bad", ["", "0", "-3", "abc"])
def test_max_rpm_invalido_cai_no_default(monkeypatch, bad):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("GEMINI_MAX_RPM", bad)
    assert Settings.from_env().max_rpm == DEFAULT_MAX_RPM
