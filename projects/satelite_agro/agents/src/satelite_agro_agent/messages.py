"""Extração das saídas de um sub-agente ReAct (lista de `messages`).

Puro, sem rede: recebe as mensagens que o `create_agent` devolve e separa o
texto final, os nomes das tools chamadas e os payloads crus das tools (dicts
determinísticos — a fonte de verdade de todo número). Usado pelos nós de
especialista do grafo e pela síntese.
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage


def final_text(messages: list[Any]) -> str:
    """Texto da última AIMessage sem tool_calls (a resposta do sub-agente)."""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and not msg.tool_calls:
            content = msg.content
            if isinstance(content, str):
                return content.strip()
            # Gemini às vezes devolve blocos; concatena os de texto
            parts = [
                b.get("text", "") if isinstance(b, dict) else str(b)
                for b in content
                if not isinstance(b, dict) or b.get("type") == "text"
            ]
            return "".join(parts).strip()
    return ""


def tool_names(messages: list[Any]) -> list[str]:
    names: list[str] = []
    for msg in messages:
        for call in getattr(msg, "tool_calls", None) or []:
            name = call.get("name") if isinstance(call, dict) else getattr(call, "name", None)
            if name:
                names.append(name)
    return names


def tool_payloads(messages: list[Any]) -> list[dict[str, Any]]:
    """Conteúdo das ToolMessages, já como dict. Ignora o que não for JSON de objeto."""
    out: list[dict[str, Any]] = []
    for msg in messages:
        if not isinstance(msg, ToolMessage):
            continue
        content = msg.content
        if isinstance(content, list):  # blocos de conteúdo MCP
            content = "".join(
                b.get("text", "")
                for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            )
        if not isinstance(content, str):
            continue
        try:
            parsed = json.loads(content)
        except (ValueError, TypeError):
            continue
        if isinstance(parsed, dict):
            out.append(parsed)
    return out
