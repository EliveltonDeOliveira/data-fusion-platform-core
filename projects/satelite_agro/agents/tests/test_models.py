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


def test_stats_vazio_antes_de_qualquer_for_role():
    pool = ModelPool(_settings(models=("m-a", "m-b")))
    assert pool.stats() == {}


def test_stats_tem_uma_entrada_por_modelo_ja_usado():
    pool = ModelPool(_settings(models=("m-a", "m-b"), max_rpm=7))
    pool.for_role("supervisor")  # -> m-a
    pool.for_role("clima")  # -> m-b

    stats = pool.stats()
    assert set(stats) == {"m-a", "m-b"}
    assert stats["m-a"].max_rpm == 7
    assert stats["m-a"].waiting == 0
