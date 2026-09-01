"""Grafo multi-agente (LangGraph): Supervisor -> especialistas (fan-out) -> síntese.

    pergunta
       |
    supervisor                     (1 chamada LLM: quais especialistas + sub-perguntas)
       |  fan-out condicional (branches paralelas)
    clima  uso_terra  metodologia   (cada um: create_agent ReAct com as suas tools)
       \\     |      /
         synthesis                 (1 especialista -> devolve a sub-resposta;
          |                         2+ -> 1 chamada LLM compõe a correlação)
     {answer, data, tool_calls, specialists}

O contrato de saída é o mesmo do agente único da fase anterior, então a UI não
muda. Todo número objetivo vem dos payloads das tools, nunca do modelo —
inclusive o especialista de metodologia, que só cita o que a busca no corpus
RAG devolveu.
"""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from .agent import load_tools
from .config import Settings
from .guardrails import ensure_recommendation_refusal
from .messages import final_text, tool_names, tool_payloads
from .models import ModelPool
from .specialists import (
    build_clima_specialist,
    build_metodologia_specialist,
    build_uso_terra_specialist,
)
from .supervisor import SPECIALISTS, Plan, plan
from .synthesis import synthesize

_NO_SPECIALIST_ANSWER = (
    "Este serviço informa dado público de monitoramento do Rio Grande do Sul em "
    "três dimensões: clima e solo (Open-Meteo), uso e cobertura da terra "
    "(MapBiomas) e metodologia de classificação da MapBiomas. Reformule a "
    "pergunta nesses termos que eu consigo ajudar."
)


class GraphState(TypedDict, total=False):
    question: str
    plan: Plan
    specialists: list[str]
    clima: dict[str, Any]
    uso_terra: dict[str, Any]
    metodologia: dict[str, Any]
    answer: str
    data: list[dict[str, Any]]
    tool_calls: list[str]


async def _run_specialist(agent: Any, question: str) -> dict[str, Any]:
    out = await agent.ainvoke({"messages": [("user", question)]})
    msgs = out.get("messages", [])
    return {
        "sub_answer": final_text(msgs),
        "payloads": tool_payloads(msgs),
        "tool_calls": tool_names(msgs),
    }


def _build_nodes(planner, clima_agent, uso_terra_agent, metodologia_agent, synthesizer):
    async def supervisor(state: GraphState) -> dict[str, Any]:
        p: Plan = await planner(state["question"])
        specs = p.specialists
        out: dict[str, Any] = {"plan": p, "specialists": specs}
        if not specs:
            out.update(answer=_NO_SPECIALIST_ANSWER, data=[], tool_calls=[])
        return out

    async def clima(state: GraphState) -> dict[str, Any]:
        q = state["plan"].question_for("clima", state["question"])
        return {"clima": await _run_specialist(clima_agent, q)}

    async def uso_terra(state: GraphState) -> dict[str, Any]:
        q = state["plan"].question_for("uso_terra", state["question"])
        return {"uso_terra": await _run_specialist(uso_terra_agent, q)}

    async def metodologia(state: GraphState) -> dict[str, Any]:
        q = state["plan"].question_for("metodologia", state["question"])
        return {"metodologia": await _run_specialist(metodologia_agent, q)}

    async def synthesis(state: GraphState) -> dict[str, Any]:
        results = {name: state[name] for name in SPECIALISTS if state.get(name)}
        payloads: list[dict[str, Any]] = []
        calls: list[str] = []
        for r in results.values():
            payloads.extend(r["payloads"])
            calls.extend(r["tool_calls"])

        if len(results) == 1:
            answer = next(iter(results.values()))["sub_answer"]
        else:
            answer = await synthesizer(
                state["question"], {k: v["sub_answer"] for k, v in results.items()}
            )
        answer = ensure_recommendation_refusal(state["question"], answer)
        return {"answer": answer, "data": payloads, "tool_calls": calls}

    return supervisor, clima, uso_terra, metodologia, synthesis


def _route_after_supervisor(state: GraphState) -> list[str] | str:
    return state.get("specialists") or END


async def build_graph(
    settings: Settings,
    *,
    pool: ModelPool | None = None,
    tools: list[Any] | None = None,
    planner: Any | None = None,
    clima_agent: Any | None = None,
    uso_terra_agent: Any | None = None,
    metodologia_agent: Any | None = None,
    synthesizer: Any | None = None,
):
    """Grafo compilado, pronto para `.ainvoke({"question": pergunta})`.

    Injeção de `planner` / `*_agent` / `synthesizer` permite testar o roteamento
    sem rede nem carregar as tools do MCP.
    """
    pool = pool or ModelPool(settings)

    if clima_agent is None or uso_terra_agent is None or metodologia_agent is None:
        if tools is None:
            tools = await load_tools(settings)
        by_name = {t.name: t for t in tools}
        clima_agent = clima_agent or build_clima_specialist(pool.for_role("clima"), by_name)
        uso_terra_agent = uso_terra_agent or build_uso_terra_specialist(
            pool.for_role("uso_terra"), by_name
        )
        metodologia_agent = metodologia_agent or build_metodologia_specialist(
            pool.for_role("metodologia"), by_name
        )

    if planner is None:
        supervisor_model = pool.for_role("supervisor")

        async def planner(question: str) -> Plan:
            return await plan(question, supervisor_model)

    if synthesizer is None:
        synthesis_model = pool.for_role("synthesis")

        async def synthesizer(question: str, sub_answers: dict[str, str]) -> str:
            return await synthesize(question, sub_answers, synthesis_model)

    supervisor, clima, uso_terra, metodologia, synthesis = _build_nodes(
        planner, clima_agent, uso_terra_agent, metodologia_agent, synthesizer
    )

    builder = StateGraph(GraphState)
    builder.add_node("supervisor", supervisor)
    builder.add_node("clima", clima)
    builder.add_node("uso_terra", uso_terra)
    builder.add_node("metodologia", metodologia)
    # defer: só roda depois que todas as branches de especialista agendadas
    # terminam — inclusive quando só uma foi agendada.
    builder.add_node("synthesis", synthesis, defer=True)

    builder.add_edge(START, "supervisor")
    builder.add_conditional_edges(
        "supervisor", _route_after_supervisor, ["clima", "uso_terra", "metodologia", END]
    )
    builder.add_edge("clima", "synthesis")
    builder.add_edge("uso_terra", "synthesis")
    builder.add_edge("metodologia", "synthesis")
    builder.add_edge("synthesis", END)

    graph = builder.compile()
    graph.role_models = pool.role_models  # type: ignore[attr-defined]
    graph.model_pool = pool  # type: ignore[attr-defined]
    return graph
