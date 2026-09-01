"""Pool de modelos por papel.

Papéis no grafo — `supervisor`, `clima`, `uso_terra`, `metodologia`,
`synthesis` — recebem um modelo cada, alternando a lista de `settings.models`
em ordem. Cada nome de modelo distinto tem um `InMemoryRateLimiter`
compartilhado entre os papéis que o usam: o provedor conta requisições por
minuto por modelo, então alternar dois modelos equivalentes distribui o
orçamento sem estourar nenhum.
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel

from .agent import build_model, build_rate_limiter
from .config import Settings

ROLES: tuple[str, ...] = ("supervisor", "clima", "uso_terra", "metodologia", "synthesis")


class ModelPool:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        models = settings.models or (settings.model,)
        self._role_model = {role: models[i % len(models)] for i, role in enumerate(ROLES)}
        self._limiters: dict[str, object] = {}

    def _limiter(self, model_name: str):
        if model_name not in self._limiters:
            self._limiters[model_name] = build_rate_limiter(self._settings)
        return self._limiters[model_name]

    def for_role(self, role: str) -> BaseChatModel:
        model_name = self._role_model.get(role, self._settings.model)
        return build_model(self._settings, model=model_name, rate_limiter=self._limiter(model_name))

    @property
    def role_models(self) -> dict[str, str]:
        return dict(self._role_model)
