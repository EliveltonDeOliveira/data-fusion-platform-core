from __future__ import annotations

import pytest

from satelite_agro_agent.agent import SYSTEM_PROMPT
from satelite_agro_agent.config import DEFAULT_MCP_URL, DEFAULT_MODEL, Settings


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
