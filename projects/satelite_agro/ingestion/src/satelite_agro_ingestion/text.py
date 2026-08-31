"""Normalização de texto para casar nomes (sem acento, minúsculo)."""

from __future__ import annotations

import unicodedata


def norm(value: str) -> str:
    stripped = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return " ".join(stripped.lower().split())
