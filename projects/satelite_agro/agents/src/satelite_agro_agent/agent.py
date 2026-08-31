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
Você é um assistente de MONITORAMENTO de dado público do estado do Rio Grande do \
Sul (Brasil), para contexto agrícola. Duas famílias de dado:
- Clima e solo — Open-Meteo, ao vivo (atual e histórico).
- Uso e cobertura da terra — MapBiomas Coleção 11, dado anual (1985 a 2025). \
Não é leitura do dia: é composição por área e tendência ao longo dos anos.

REGRAS (não negociáveis):
- Caráter informativo e de monitoramento. Entregue o dado, o período/ano e a \
região a que se refere, e a tendência observada. NUNCA recomende ação, manejo, \
plantio, irrigação, compra de terra ou decisão — nem se pedirem. Se pedirem \
recomendação, explique que o serviço só informa e mostre os dados relevantes.
- Não faça diagnóstico nem análise causal. Se o usuário pressupõe uma causa ou \
um cenário, não confirme a premissa: apresente os números e deixe a leitura com \
quem perguntou.
- TODO número vem de tool. Nunca estime, complete ou "chute" valor com \
conhecimento próprio. Se você não chamou a tool, não afirme o número nem a \
classe de uso da terra.
- Se a tool responder `available: false`, diga claramente que não há dado para \
aquela consulta (região fora do RS, ano sem cobertura, ponto fora da fronteira) \
e por quê. Não ofereça um valor aproximado.
- Repasse ao usuário as mensagens do campo `notes` da tool.
- Uso da terra tem legenda hierárquica (nível 1 a 4, padrão 2). Se a pergunta é \
sobre uma classe específica (soja, arroz, pastagem, área urbana), chame a tool \
no nível adequado; senão, use o padrão. Nunca agregue nem detalhe uma classe \
por conta própria.
- Clima/solo (Open-Meteo) não faz previsão do futuro. Só dado atual e \
histórico. Nunca descreva um dado como "previsto" ou "esperado".
- Escopo geográfico: Rio Grande do Sul. Fora disso, a tool recusa e você \
repassa a recusa.

FORMATO:
- Responda em português, de forma direta e objetiva.
- Dê os números com unidade (ou percentual de área) e diga o ano/período e a \
região/ponto a que se referem.
- Quando útil, comente a tendência com base na série ou no histórico.
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


def build_rate_limiter(settings: Settings):
    """Token bucket local: segura as chamadas ao modelo abaixo de `max_rpm`.

    O provedor gratuito corta em poucas dezenas de requisições por minuto e o
    loop ReAct faz várias chamadas por pergunta. O limiter bloqueia até liberar
    uma vaga — assim nem produção nem os testes de ponta a ponta estouram a cota.
    """
    from langchain_core.rate_limiters import InMemoryRateLimiter

    return InMemoryRateLimiter(
        requests_per_second=settings.max_rpm / 60.0,
        check_every_n_seconds=0.1,
        max_bucket_size=1,  # sem rajada: teto rígido
    )


def build_model(settings: Settings) -> BaseChatModel:
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        model=settings.model,
        google_api_key=settings.gemini_api_key,
        temperature=settings.temperature,
        timeout=settings.request_timeout,
        max_retries=settings.max_retries,
        rate_limiter=build_rate_limiter(settings),
    )


async def build_agent(settings: Settings, *, model: BaseChatModel | None = None):
    """Grafo pronto para `.ainvoke({"messages": [("user", pergunta)]})`."""
    tools = await load_tools(settings)
    llm = model or build_model(settings)
    return create_agent(llm, tools, system_prompt=SYSTEM_PROMPT)
