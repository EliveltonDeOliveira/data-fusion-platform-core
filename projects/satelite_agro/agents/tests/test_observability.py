from __future__ import annotations

import sys
import types
from typing import Any

from satelite_agro_agent.observability import _Trace, route_run


def test_sem_uri_e_noop():
    with route_run(None, role_models={"supervisor": "m"}) as trace:
        assert type(trace) is _Trace
        # não deve levantar
        trace.log_routing(specialists=["clima"], tool_calls=["get_weather_trend"])


class _FakeRunInfo:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id


class _FakeRun:
    def __init__(self, run_id: str) -> None:
        self.info = _FakeRunInfo(run_id)


class _FakeExperiment:
    def __init__(self, experiment_id: str) -> None:
        self.experiment_id = experiment_id


class _FakeMlflowClient:
    """Espelha só o que `route_run` usa da `MlflowClient` — sem estado global,
    então dá pra instanciar um por chamada (como duas requisições concorrentes
    fariam) sem uma colidir com a outra."""

    def __init__(self, *, tracking_uri: str | None = None, experiments: dict | None = None) -> None:
        self.tracking_uri = tracking_uri
        self._experiments = experiments if experiments is not None else {}
        self.logged: dict[str, Any] = {"tags": {}, "metrics": {}, "terminated": []}
        self.created_run_ids: list[str] = []

    def get_experiment_by_name(self, name):
        eid = self._experiments.get(name)
        return _FakeExperiment(eid) if eid is not None else None

    def create_experiment(self, name):
        eid = f"exp-{len(self._experiments) + 1}"
        self._experiments[name] = eid
        return eid

    def create_run(self, experiment_id, run_name=None):
        run_id = f"run-{len(self.created_run_ids) + 1}"
        self.created_run_ids.append(run_id)
        return _FakeRun(run_id)

    def set_tag(self, run_id, key, value):
        self.logged["tags"].setdefault(run_id, {})[key] = value

    def log_metric(self, run_id, key, value):
        self.logged["metrics"].setdefault(run_id, {})[key] = value

    def set_terminated(self, run_id):
        self.logged["terminated"].append(run_id)


def _install_fake_mlflow(monkeypatch, client: _FakeMlflowClient):
    fake = types.SimpleNamespace(MlflowClient=lambda tracking_uri=None: client)
    monkeypatch.setitem(sys.modules, "mlflow", fake)


def test_com_uri_loga_so_metadado_estrutural(monkeypatch):
    client = _FakeMlflowClient(experiments={"satelite_agro": "exp-1"})
    _install_fake_mlflow(monkeypatch, client)

    roles = {"supervisor": "m-a", "clima": "m-b"}
    with route_run("http://mlflow:5000", role_models=roles) as trace:
        trace.log_routing(
            specialists=["clima", "uso_terra"],
            tool_calls=["get_weather_trend", "get_land_use_summary"],
            n_llm_calls=4,
        )

    run_id = client.created_run_ids[0]
    tags = client.logged["tags"][run_id]
    metrics = client.logged["metrics"][run_id]
    assert tags["specialists"] == "clima,uso_terra"
    assert tags["model.supervisor"] == "m-a"
    assert metrics["n_specialists"] == 2
    assert metrics["n_llm_calls"] == 4
    assert "latency_ms" in metrics
    assert run_id in client.logged["terminated"]
    # nada de texto livre
    joined = " ".join(map(str, tags.values()))
    assert "?" not in joined


def test_cria_experiment_quando_ainda_nao_existe(monkeypatch):
    client = _FakeMlflowClient()  # sem "satelite_agro" pré-existente
    _install_fake_mlflow(monkeypatch, client)

    with route_run("http://mlflow:5000", role_models={}):
        pass

    assert client._experiments["satelite_agro"] == "exp-1"


def test_duas_requisicoes_concorrentes_nao_colidem(monkeypatch):
    """Reproduz o bug real: com a API fluente, duas `route_run` abertas ao
    mesmo tempo colidiam na pilha global de run ativa (`Run ... is already
    active`). Aqui, cada uma tem seu próprio run_id — abrir a 2ª antes de
    fechar a 1ª não pode levantar nem misturar dado."""
    client = _FakeMlflowClient(experiments={"satelite_agro": "exp-1"})
    _install_fake_mlflow(monkeypatch, client)

    with (
        route_run("http://mlflow:5000", role_models={"supervisor": "m-a"}) as trace_a,
        route_run("http://mlflow:5000", role_models={"supervisor": "m-b"}) as trace_b,
    ):
        trace_a.log_routing(specialists=["clima"], tool_calls=[])
        trace_b.log_routing(specialists=["uso_terra"], tool_calls=[])

    run_a, run_b = client.created_run_ids
    assert run_a != run_b
    assert client.logged["tags"][run_a]["specialists"] == "clima"
    assert client.logged["tags"][run_b]["specialists"] == "uso_terra"
    assert run_a in client.logged["terminated"]
    assert run_b in client.logged["terminated"]
