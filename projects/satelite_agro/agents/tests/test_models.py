from __future__ import annotations

from satelite_agro_agent.config import Settings
from satelite_agro_agent.models import ROLES, ModelPool


def _settings(**kw) -> Settings:
    return Settings(gemini_api_key="k", **kw)


def test_alterna_modelos_por_papel():
    pool = ModelPool(_settings(models=("m-a", "m-b")))
    rm = pool.role_models
    assert [rm[r] for r in ROLES] == ["m-a", "m-b", "m-a", "m-b", "m-a"]


def test_um_modelo_so_todos_os_papeis():
    pool = ModelPool(_settings(models=("only",)))
    assert set(pool.role_models.values()) == {"only"}


def test_rate_limiter_compartilhado_por_modelo():
    pool = ModelPool(_settings(models=("m-a", "m-b")))
    # supervisor, uso_terra e synthesis -> m-a; clima e metodologia -> m-b
    assert pool._limiter("m-a") is pool._limiter("m-a")
    assert pool._limiter("m-a") is not pool._limiter("m-b")


def test_for_role_usa_o_modelo_do_papel():
    pool = ModelPool(_settings(models=("m-a", "m-b")))
    assert pool.for_role("clima").model.endswith("m-b")
    assert pool.for_role("supervisor").model.endswith("m-a")


def test_for_role_desconhecido_cai_no_model_padrao():
    pool = ModelPool(_settings(models=("m-a", "m-b"), model="fallback"))
    assert pool.for_role("qualquer").model.endswith("fallback")
