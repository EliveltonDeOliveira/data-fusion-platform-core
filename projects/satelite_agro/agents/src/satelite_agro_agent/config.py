"""Configuração via ambiente. Nada de segredo em código."""

from __future__ import annotations

import os
from dataclasses import dataclass

# Um agente, modelo direto. Flash-Lite — nunca Pro.
DEFAULT_MODEL = "gemini-3.5-flash-lite"
# host/porta reais vêm de MCP_URL no ambiente
DEFAULT_MCP_URL = "http://mcp:8000/mcp"
# O provedor de LLM limita requisições por minuto. O agente segura as chamadas
# ao modelo abaixo de um teto (token bucket local), pra não estourar esse limite
# — vale pra produção e pros testes de ponta a ponta. O loop ReAct faz várias
# chamadas por pergunta, então configure com folga.
DEFAULT_MAX_RPM = 10
DEFAULT_MAX_RETRIES = 3


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str
    model: str = DEFAULT_MODEL
    mcp_url: str = DEFAULT_MCP_URL
    temperature: float = 0.0
    request_timeout: float = 60.0
    max_rpm: int = DEFAULT_MAX_RPM
    max_retries: int = DEFAULT_MAX_RETRIES

    @classmethod
    def from_env(cls) -> Settings:
        key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not key:
            raise RuntimeError("GEMINI_API_KEY não definido.")
        return cls(
            gemini_api_key=key,
            model=os.environ.get("GEMINI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL,
            mcp_url=os.environ.get("MCP_URL", DEFAULT_MCP_URL).strip() or DEFAULT_MCP_URL,
            max_rpm=_positive_int("GEMINI_MAX_RPM", DEFAULT_MAX_RPM),
            max_retries=_positive_int("GEMINI_MAX_RETRIES", DEFAULT_MAX_RETRIES),
        )


def _positive_int(env: str, default: int) -> int:
    raw = os.environ.get(env, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default
