from __future__ import annotations

import sys
import types

from satelite_agro_agent.observability import _Trace, route_run


def test_sem_uri_e_noop():
    with route_run(None, role_models={"supervisor": "m"}) as trace:
        assert type(trace) is _Trace
        # não deve levantar
        trace.log_routing(specialists=["clima"], tool_calls=["get_weather_trend"])


def test_com_uri_loga_so_metadado_estrutural(monkeypatch):
    logged: dict = {"tags": {}, "metrics": {}, "params": {}}

    fake = types.SimpleNamespace()
    fake.set_tracking_uri = lambda uri: logged.setdefault("uri", uri)
    fake.set_experiment = lambda name: logged.setdefault("experiment", name)
    fake.set_tag = lambda k, v: logged["tags"].__setitem__(k, v)
    fake.log_metric = lambda k, v: logged["metrics"].__setitem__(k, v)
    fake.log_param = lambda k, v: logged["params"].__setitem__(k, v)

    class _Run:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    fake.start_run = lambda run_name=None: _Run()
    monkeypatch.setitem(sys.modules, "mlflow", fake)

    roles = {"supervisor": "m-a", "clima": "m-b"}
    with route_run("http://mlflow:5000", role_models=roles) as trace:
        trace.log_routing(
            specialists=["clima", "uso_terra"],
            tool_calls=["get_weather_trend", "get_land_use_summary"],
            n_llm_calls=4,
        )

    assert logged["uri"] == "http://mlflow:5000"
    assert logged["experiment"] == "satelite_agro"
    assert logged["tags"]["specialists"] == "clima,uso_terra"
    assert logged["tags"]["model.supervisor"] == "m-a"
    assert logged["metrics"]["n_specialists"] == 2
    assert logged["metrics"]["n_llm_calls"] == 4
    assert "latency_ms" in logged["metrics"]
    # nada de texto livre
    joined = " ".join(map(str, logged["tags"].values()))
    assert "?" not in joined
