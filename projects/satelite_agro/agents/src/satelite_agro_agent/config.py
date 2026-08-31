"""Configuração via ambiente. Nada de segredo em código."""

from __future__ import annotations

import os
from dataclasses import dataclass

# Fase 1: um agente, modelo direto. Flash-Lite — nunca Pro.
DEFAULT_MODEL = "gemini-3.5-flash-lite"
# host/porta reais vêm de MCP_URL no ambiente
DEFAULT_MCP_URL = "http://mcp:8000/mcp"


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str
    model: str = DEFAULT_MODEL
    mcp_url: str = DEFAULT_MCP_URL
    temperature: float = 0.0
    request_timeout: float = 60.0

    @classmethod
    def from_env(cls) -> Settings:
        key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not key:
            raise RuntimeError("GEMINI_API_KEY não definido.")
        return cls(
            gemini_api_key=key,
            model=os.environ.get("GEMINI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL,
            mcp_url=os.environ.get("MCP_URL", DEFAULT_MCP_URL).strip() or DEFAULT_MCP_URL,
        )
