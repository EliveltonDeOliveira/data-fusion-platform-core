"""Checagens deterministicas sobre a resposta do agente (`POST /ask`).

Funcoes puras, sem rede e sem dependencia externa: recebem um caso do dataset
dourado (`cases/<projeto>.json`) e o JSON da resposta do agente, devolvem um
`Report` com as falhas. O runner (`run.py`) cuida do I/O.

O contrato da resposta (ver o servico do agente):
    {"answer": str, "model": str, "tool_calls": [str], "data": [<payload da tool>]}
`data` traz os payloads crus das tools (deterministicos, nao texto do modelo) —
a fonte de verdade para checar se um numero ou uma classe citada foi inventada.
As checagens sao agnosticas de tool: `get_weather_trend` (clima) e
`get_land_use_summary` / `get_land_use_at_point` (uso da terra) usam o mesmo
`evaluate`, cada `expect` liga so os checadores que fazem sentido.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

# --------------------------------------------------------------------------- #
# normalizacao de texto (sem acento, minusculo) — o dataset e escrito em ascii


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return " ".join(text.lower().split())


# --------------------------------------------------------------------------- #
# numeros "de medicao" no texto: valor colado a uma unidade de clima/solo.
# Numeros sem unidade (7 dias, 2024, "um ponto") sao ignorados de proposito.

_MEASURE_RE = re.compile(
    r"(-?\d+(?:[.,]\d+)?)\s?(graus\b|mm\b|m3/m3|%)",
    re.IGNORECASE,
)
_DEGREE_RE = re.compile(r"(-?\d+(?:[.,]\d+)?)\s?°\s?c?", re.IGNORECASE)

# tripwire de recomendacao. Heuristica — casos marcados sao revisados a mao.
_ADVICE_IMPERATIVE = re.compile(
    r"\b(irrigue|adube|pulverize|semeie|fertilize|plante agora|aplique \w+)\b"
)
_ADVICE_MODAL = re.compile(r"(recomend\w*|aconselh\w*|\bsugiro\b|\bvoce deveria\b|\bvoce deve\b)")
_NEGATION = re.compile(r"\b(nao|nunca|jamais|sem)\b")

_UNAVAILABLE_RE = re.compile(
    r"(nao ha dado|nao tenho dado|sem dado|nao encontrei|nao foi possivel|"
    r"fora do (escopo|rio grande do sul)|escopo (e|desta|deste|da ferramenta)|"
    r"nao disponivel|nao esta disponivel|apenas o rio grande do sul|"
    r"so cobre o rio grande do sul|limitad. ao rio grande do sul)"
)


@dataclass
class Report:
    case_id: str
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures


# --------------------------------------------------------------------------- #
# helpers sobre o payload da tool


def tool_payloads(response: dict[str, Any]) -> list[dict[str, Any]]:
    """Todos os payloads de tool (dicts com `available`), de qualquer tool do projeto."""
    return [
        item
        for item in response.get("data") or []
        if isinstance(item, dict) and "available" in item
    ]


def weather_payloads(response: dict[str, Any]) -> list[dict[str, Any]]:
    """Payloads que parecem de `get_weather_trend` (`region_query` + série/granularidade)."""
    return [
        p
        for p in tool_payloads(response)
        if "region_query" in p and ("series" in p or "granularity" in p)
    ]


def land_use_payloads(response: dict[str, Any]) -> list[dict[str, Any]]:
    """Payloads das tools de uso da terra (`get_land_use_summary` / `_at_point`)."""
    return [p for p in tool_payloads(response) if "classes" in p or "class_id" in p]


def _first_available(payloads: list[dict[str, Any]]) -> dict[str, Any] | None:
    for p in payloads:
        if p.get("available"):
            return p
    return payloads[0] if payloads else None


def _series_variables(payload: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for key in ("series", "summary"):
        for row in payload.get(key) or []:
            if isinstance(row, dict) and row.get("variable"):
                names.add(str(row["variable"]))
    return names


def _data_numbers(payloads: list[dict[str, Any]]) -> set[float]:
    """Todo valor numerico presente no dado da tool, arredondado a 1 casa."""
    vals: set[float] = set()

    def add(v: object) -> None:
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            vals.add(round(float(v), 1))
            vals.add(round(float(v)))

    for p in payloads:
        for row in p.get("summary") or []:
            for k in ("mean", "min", "max", "total"):
                add(row.get(k))
        for row in p.get("series") or []:
            for pt in row.get("points") or []:
                add(pt.get("value"))
        for v in (p.get("current") or {}).values():
            add(v)
        # uso da terra: percentuais e áreas por classe
        add(p.get("total_area_ha"))
        for row in p.get("classes") or []:
            add(row.get("area_ha"))
            add(row.get("area_pct"))
    return vals


def _answer_measures(answer: str) -> list[float]:
    text = norm(answer)
    found = [m.group(1) for m in _MEASURE_RE.finditer(text)]
    found += [m.group(1) for m in _DEGREE_RE.finditer(answer)]
    return [float(x.replace(",", ".")) for x in found]


def _grounded(value: float, allowed: set[float]) -> bool:
    return any(abs(a - value) <= max(0.5, abs(a) * 0.15) for a in allowed)


# --------------------------------------------------------------------------- #
# checagens individuais — cada uma adiciona 0+ falhas ao report


def _check_tool_calls(expect: dict, response: dict, rep: Report) -> None:
    want = expect.get("tool_calls")
    if not want:
        return
    got = list(response.get("tool_calls") or [])
    for name in want:
        if name not in got:
            rep.failures.append(f"esperava chamada da tool {name!r}; tool_calls={got}")


def _check_available(expect: dict, payloads: list[dict], rep: Report) -> None:
    if "available" not in expect:
        return
    want = expect["available"]
    any_available = any(p.get("available") for p in payloads)
    if want and not any_available:
        rep.failures.append("esperava available=true, mas nenhum payload da tool veio disponivel")
    if not want and any_available:
        rep.failures.append("esperava available=false, mas a tool respondeu com dado disponivel")


def _check_location(expect: dict, payloads: list[dict], rep: Report) -> None:
    payload = _first_available(payloads)
    loc = (payload or {}).get("location") or {}

    if "is_state_level" in expect:
        want = expect["is_state_level"]
        # clima: campo `is_state_level`; uso da terra: `location.kind == "state"`
        got = bool(loc.get("is_state_level")) or loc.get("kind") == "state"
        if got != want:
            rep.failures.append(f"is_state_level: esperava {want}, veio {got}")

    sub = expect.get("location_name_contains")
    if sub:
        name = norm(str(loc.get("name", "")))
        if norm(sub) not in name:
            rep.failures.append(f"location.name {loc.get('name')!r} nao contem {sub!r}")


def _check_year(expect: dict, payloads: list[dict], rep: Report) -> None:
    want = expect.get("year")
    if want is None:
        return
    got = (_first_available(payloads) or {}).get("year")
    if got != want:
        rep.failures.append(f"year: esperava {want}, veio {got}")


def _check_level(expect: dict, payloads: list[dict], rep: Report) -> None:
    want = expect.get("level")
    if want is None:
        return
    got = (_first_available(payloads) or {}).get("level")
    if got != want:
        rep.failures.append(f"level: esperava {want}, veio {got}")


def _check_class_grounding(expect: dict, answer: str, payloads: list[dict], rep: Report) -> None:
    """A resposta cita ao menos uma classe de uso da terra que veio no dado da tool."""
    if not expect.get("classes_grounded"):
        return
    text = norm(answer)
    labels: list[str] = []
    for p in payloads:
        for row in p.get("classes") or []:
            if row.get("label"):
                labels.append(norm(str(row["label"])))
        if p.get("label"):  # get_land_use_at_point
            labels.append(norm(str(p["label"])))
        if p.get("name_pt"):
            labels.append(norm(str(p["name_pt"])))
    if labels and not any(lbl in text for lbl in labels):
        rep.failures.append("nenhuma classe citada na resposta bate com o dado da tool")


def _check_variables(expect: dict, payloads: list[dict], rep: Report) -> None:
    want = expect.get("variables_any")
    if not want:
        return
    payload = _first_available(payloads)
    got = _series_variables(payload or {})
    if not (set(want) & got):
        rep.failures.append(f"nenhuma das variaveis {want} na resposta da tool; veio {sorted(got)}")


def _check_period_mode(expect: dict, payloads: list[dict], rep: Report) -> None:
    want = expect.get("period_mode")
    if not want:
        return
    payload = _first_available(payloads)
    got = ((payload or {}).get("period") or {}).get("mode")
    if got != want:
        rep.failures.append(f"period.mode: esperava {want!r}, veio {got!r}")


def _check_answer_mentions(expect: dict, answer: str, rep: Report) -> None:
    want = expect.get("answer_mentions_any")
    if not want:
        return
    text = norm(answer)
    if not any(norm(s) in text for s in want):
        rep.failures.append(f"a resposta nao menciona nenhum de {want}")


def _check_answer_has_measure(expect: dict, answer: str, rep: Report) -> None:
    if "answer_has_measure" not in expect:
        return
    has = bool(_answer_measures(answer))
    if expect["answer_has_measure"] and not has:
        rep.failures.append("a resposta nao traz nenhum numero com unidade de clima/solo")
    if not expect["answer_has_measure"] and has:
        rep.failures.append("a resposta traz numero com unidade, e nao deveria")


def _check_unavailable_wording(expect: dict, answer: str, rep: Report) -> None:
    if not expect.get("answer_indicates_unavailable"):
        return
    if not _UNAVAILABLE_RE.search(norm(answer)):
        rep.failures.append("a resposta nao deixa claro que nao ha dado para essa consulta")


def _check_no_prescription(expect: dict, answer: str, rep: Report) -> None:
    if not expect.get("no_prescription"):
        return
    text = norm(answer)

    for m in _ADVICE_IMPERATIVE.finditer(text):
        rep.failures.append(f"tom prescritivo: {m.group(0)!r} (imperativo de manejo)")

    for m in _ADVICE_MODAL.finditer(text):
        janela = text[max(0, m.start() - 35) : m.start()]
        if not _NEGATION.search(janela):
            rep.failures.append(f"tom prescritivo: {m.group(0)!r} sem negacao antes ({janela!r})")


def _check_grounded(expect: dict, answer: str, payloads: list[dict], rep: Report) -> None:
    if not expect.get("grounded_numbers"):
        return
    allowed = _data_numbers(payloads)
    for value in _answer_measures(answer):
        if not _grounded(value, allowed):
            rep.failures.append(
                f"numero {value} citado na resposta nao bate com nenhum valor da tool "
                f"(chute de dado)"
            )


# --------------------------------------------------------------------------- #
# entrada


def evaluate(case: dict[str, Any], response: dict[str, Any]) -> Report:
    rep = Report(case_id=str(case.get("id", "?")))
    expect = case.get("expect") or {}
    answer = str(response.get("answer", ""))
    payloads = tool_payloads(response)

    if not answer.strip():
        rep.failures.append("resposta vazia")

    _check_tool_calls(expect, response, rep)
    _check_available(expect, payloads, rep)
    _check_location(expect, payloads, rep)
    _check_year(expect, payloads, rep)
    _check_level(expect, payloads, rep)
    _check_variables(expect, payloads, rep)
    _check_period_mode(expect, payloads, rep)
    _check_answer_mentions(expect, answer, rep)
    _check_answer_has_measure(expect, answer, rep)
    _check_unavailable_wording(expect, answer, rep)
    _check_no_prescription(expect, answer, rep)
    _check_grounded(expect, answer, payloads, rep)
    _check_class_grounding(expect, answer, payloads, rep)
    return rep
