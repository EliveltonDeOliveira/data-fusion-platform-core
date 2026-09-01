"""Agente do Projeto 1 — Satélite + Agro/GIS.

Arquitetura multi-agente (LangGraph): um Supervisor decompõe a pergunta e delega
a especialistas (Clima, Uso-da-Terra), que rodam em paralelo; uma etapa de
síntese junta as respostas quando mais de um especialista age. As tools vêm do
MCP server do projeto. O papel dos agentes é raciocínio e redação — todo dado
vem de tool, nunca do modelo.
"""

from .agent import SYSTEM_PROMPT, build_agent
from .config import Settings
from .graph import build_graph

__all__ = ["SYSTEM_PROMPT", "Settings", "build_agent", "build_graph"]
