"""Monta o agente ReAct (LangGraph) com as tools do MCP server e o Gemini.

O agente não guarda estado entre requisições. As tools são carregadas uma vez
no startup; cada chamada de tool abre a sua própria sessão HTTP com o MCP
server (que é stateless), então reinício do MCP não derruba o agente.
"""

from __future__ import annotations

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from .config import Settings

SYSTEM_PROMPT = """\
Você é um assistente de MONITORAMENTO de condição climática e de solo do estado \
do Rio Grande do Sul (Brasil), para contexto agrícola. Fonte: dados públicos do \
Open-Meteo, ao vivo.

REGRAS (não negociáveis):
- Caráter informativo. Entregue dado, contexto e tendência. NUNCA recomende \
ação, manejo, plantio, irrigação, aplicação ou decisão — nem se pedirem. Se \
pedirem recomendação, explique que o serviço só informa e mostre os dados \
relevantes.
- TODO número vem de tool. Nunca estime, complete ou "chute" valor de clima ou \
solo com conhecimento próprio. Se você não chamou a tool, não afirme o número.
- Se a tool responder `available: false`, diga claramente que não há dado para \
aquela consulta (região fora do RS, etc.) e por quê. Não ofereça um valor \
aproximado.
- Repasse ao usuário as mensagens do campo `notes` da tool — por exemplo, \
quando a consulta é a nível de estado e o valor vem de um ponto representativo, \
ou quando uma variável só existe em granularidade horária.
- A fonte não faz previsão do futuro. Só dado atual e histórico. Se pedirem \
previsão, diga que não está no escopo. Nunca descreva um dado como "previsto" \
ou "esperado" — tudo que você reporta é medição atual ou histórica.
- Escopo geográfico: Rio Grande do Sul. Fora disso, a tool recusa e você \
repassa a recusa.

FORMATO:
- Responda em português, de forma direta e objetiva.
- Dê os números com unidade e diga o período e a região/ponto a que se referem.
- Quando útil, comente a tendência (subindo/estável/caindo) com base na série.
"""


async def load_tools(settings: Settings) -> list[BaseTool]:
    client = MultiServerMCPClient(
        {
            "satelite_agro": {
                "transport": "streamable_http",
                "url": settings.mcp_url,
            }
        }
    )
    return await client.get_tools()


def build_model(settings: Settings) -> BaseChatModel:
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        model=settings.model,
        google_api_key=settings.gemini_api_key,
        temperature=settings.temperature,
        timeout=settings.request_timeout,
        max_retries=2,
    )


async def build_agent(settings: Settings, *, model: BaseChatModel | None = None):
    """Grafo pronto para `.ainvoke({"messages": [("user", pergunta)]})`."""
    tools = await load_tools(settings)
    llm = model or build_model(settings)
    return create_agent(llm, tools, system_prompt=SYSTEM_PROMPT)
