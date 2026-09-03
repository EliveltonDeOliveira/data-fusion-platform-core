"""Configuração via ambiente. Nada de segredo em código."""

from __future__ import annotations

import os
from dataclasses import dataclass

# Modelo padrão. Sobrescreva com GEMINI_MODEL / GEMINI_MODELS no ambiente.
DEFAULT_MODEL = "gemini-3.5-flash-lite"
# Vários modelos equivalentes: o pool alterna entre eles por papel (supervisor,
# especialistas, síntese) para distribuir as chamadas — cada modelo tem o seu
# próprio limite de requisições por minuto no provedor.
DEFAULT_MODELS: tuple[str, ...] = ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite")
# host/porta reais vêm de MCP_URL no ambiente
DEFAULT_MCP_URL = "http://mcp:8000/mcp"
# O provedor de LLM limita requisições por minuto. Cada modelo tem um token
# bucket local abaixo desse teto (vale para produção e para os testes de ponta a
# ponta). O grafo faz várias chamadas por pergunta, então configure com folga.
DEFAULT_MAX_RPM = 10
DEFAULT_MAX_RETRIES = 3


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str
    model: str = DEFAULT_MODEL
    models: tuple[str, ...] = DEFAULT_MODELS
    mcp_url: str = DEFAULT_MCP_URL
    temperature: float = 0.0
    request_timeout: float = 60.0
    max_rpm: int = DEFAULT_MAX_RPM
    max_retries: int = DEFAULT_MAX_RETRIES
    # Opcional: destino do trace de roteamento. Sem valor -> sem trace.
    mlflow_tracking_uri: str | None = None

    @classmethod
    def from_env(cls) -> Settings:
        key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not key:
            raise RuntimeError("GEMINI_API_KEY não definido.")

        single = os.environ.get("GEMINI_MODEL", "").strip()
        models_raw = os.environ.get("GEMINI_MODELS", "").strip()
        if models_raw:
            models = tuple(m.strip() for m in models_raw.split(",") if m.strip())
        elif single:
            models = (single,)
        else:
            models = DEFAULT_MODELS
        models = models or DEFAULT_MODELS

        return cls(
            gemini_api_key=key,
            model=single or models[0],
            models=models,
            mcp_url=os.environ.get("MCP_URL", DEFAULT_MCP_URL).strip() or DEFAULT_MCP_URL,
            max_rpm=_positive_int("GEMINI_MAX_RPM", DEFAULT_MAX_RPM),
            max_retries=_positive_int("GEMINI_MAX_RETRIES", DEFAULT_MAX_RETRIES),
            mlflow_tracking_uri=os.environ.get("MLFLOW_TRACKING_URI", "").strip() or None,
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
