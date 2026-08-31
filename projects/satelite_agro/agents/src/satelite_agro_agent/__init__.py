"""Agente do Projeto 1 — Satélite + Agro/GIS.

Um único agente (sem orquestrador): LangGraph ReAct + Gemini, com as tools
servidas pelo MCP server do projeto. Papel do agente é raciocínio e redação —
todo dado vem de tool, nunca do modelo.
"""

from .agent import SYSTEM_PROMPT, build_agent
from .config import Settings

__all__ = ["SYSTEM_PROMPT", "Settings", "build_agent"]
