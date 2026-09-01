"""Trace de roteamento no MLflow — só metadado estrutural.

Registra por requisição: quais especialistas rodaram, que tools foram chamadas,
qual modelo em cada papel, latência. NUNCA registra o texto da pergunta nem da
resposta. O autolog do LangChain não é ativado aqui (o filtro fino é assunto de
uma fase posterior; este módulo já nasce sem persistir texto livre).

Sem `MLFLOW_TRACKING_URI` o context manager é um no-op — os testes rodam sem
rede.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any


class _Trace:
    def log_routing(self, **_kw: Any) -> None: ...


class _MlflowTrace(_Trace):
    def __init__(self, mlflow: Any, role_models: dict[str, str]) -> None:
        self._mlflow = mlflow
        for role, model in role_models.items():
            mlflow.set_tag(f"model.{role}", model)

    def log_routing(
        self,
        *,
        specialists: list[str],
        tool_calls: list[str],
        n_llm_calls: int | None = None,
    ) -> None:
        self._mlflow.set_tag("specialists", ",".join(specialists) or "none")
        self._mlflow.set_tag("tool_calls", ",".join(tool_calls) or "none")
        self._mlflow.log_metric("n_specialists", len(specialists))
        self._mlflow.log_metric("n_tool_calls", len(tool_calls))
        if n_llm_calls is not None:
            self._mlflow.log_metric("n_llm_calls", n_llm_calls)


@contextmanager
def route_run(tracking_uri: str | None, *, role_models: dict[str, str] | None = None):
    if not tracking_uri:
        yield _Trace()
        return

    import mlflow

    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment("satelite_agro")
    started = time.monotonic()
    with mlflow.start_run(run_name="ask"):
        trace = _MlflowTrace(mlflow, role_models or {})
        try:
            yield trace
        finally:
            mlflow.log_metric("latency_ms", round((time.monotonic() - started) * 1000, 1))
