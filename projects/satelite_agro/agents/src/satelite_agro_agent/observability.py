"""Trace de roteamento no MLflow — só metadado estrutural.

Registra por requisição: quais especialistas rodaram, que tools foram chamadas,
qual modelo em cada papel, latência. NUNCA registra o texto da pergunta nem da
resposta. O autolog do LangChain não é ativado aqui (o filtro fino fica para
mais adiante; este módulo já nasce sem persistir texto livre).

Usa `MlflowClient` (API não-fluente) em vez de `mlflow.start_run()`/`mlflow.
set_tag()` etc. — a API fluente guarda a "run ativa" numa pilha thread-local, e
o agente atende requisições concorrentes na mesma thread do event loop
(FastAPI/asyncio): duas perguntas em paralelo colidiam nessa pilha com
`Run ... is already active`, virando 502 pro usuário. Com `MlflowClient`, cada
requisição cria e referencia sua própria run por `run_id` explícito — sem
estado global compartilhado, seguro sob concorrência.

Sem `MLFLOW_TRACKING_URI` o context manager é um no-op — os testes rodam sem
rede.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any

_EXPERIMENT_NAME = "satelite_agro"


class _Trace:
    def log_routing(self, **_kw: Any) -> None: ...


class _MlflowTrace(_Trace):
    def __init__(self, client: Any, run_id: str, role_models: dict[str, str]) -> None:
        self._client = client
        self._run_id = run_id
        for role, model in role_models.items():
            client.set_tag(run_id, f"model.{role}", model)

    def log_routing(
        self,
        *,
        specialists: list[str],
        tool_calls: list[str],
        n_llm_calls: int | None = None,
    ) -> None:
        self._client.set_tag(self._run_id, "specialists", ",".join(specialists) or "none")
        self._client.set_tag(self._run_id, "tool_calls", ",".join(tool_calls) or "none")
        self._client.log_metric(self._run_id, "n_specialists", len(specialists))
        self._client.log_metric(self._run_id, "n_tool_calls", len(tool_calls))
        if n_llm_calls is not None:
            self._client.log_metric(self._run_id, "n_llm_calls", n_llm_calls)


def _experiment_id(client: Any, name: str) -> str:
    exp = client.get_experiment_by_name(name)
    if exp is not None:
        return exp.experiment_id
    try:
        return client.create_experiment(name)
    except Exception:  # corrida na 1ª criação: outra requisição já criou o experiment
        exp = client.get_experiment_by_name(name)
        if exp is not None:
            return exp.experiment_id
        raise


@contextmanager
def route_run(tracking_uri: str | None, *, role_models: dict[str, str] | None = None):
    if not tracking_uri:
        yield _Trace()
        return

    import mlflow

    client = mlflow.MlflowClient(tracking_uri=tracking_uri)
    experiment_id = _experiment_id(client, _EXPERIMENT_NAME)
    run_id = client.create_run(experiment_id, run_name="ask").info.run_id

    trace = _MlflowTrace(client, run_id, role_models or {})
    started = time.monotonic()
    try:
        yield trace
    finally:
        client.log_metric(run_id, "latency_ms", round((time.monotonic() - started) * 1000, 1))
        client.set_terminated(run_id)
