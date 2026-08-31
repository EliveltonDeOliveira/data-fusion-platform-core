"""Testes das checagens de `checks.py` — offline, so stdlib (`unittest`).

    python -m unittest discover -s tests/eval

Verifica a logica dos checadores com respostas sinteticas do agente e valida a
estrutura do dataset dourado. Nao chama rede nem LLM.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import checks

_CASES_DIR = Path(__file__).parent / "cases"

_WEATHER_OK = {
    "region_query": "Porto Alegre",
    "available": True,
    "location": {"name": "Porto Alegre", "is_state_level": False},
    "period": {"mode": "range"},
    "series": [{"variable": "temperature", "measure": "temperature_2m_mean", "points": []}],
    "summary": [{"variable": "temperature", "mean": 18.2, "min": 12.0, "max": 24.5}],
    "current": None,
}


_LAND_SUMMARY_OK = {
    "region_query": "Santa Maria",
    "available": True,
    "location": {"name": "Santa Maria", "kind": "municipality", "geocode": "4316907"},
    "year": 2025,
    "level": 2,
    "total_area_ha": 178020.5,
    "classes": [
        {"code": "3.2", "label": "Agricultura", "area_ha": 63933.6, "area_pct": 35.91},
        {"code": "2.1", "label": "Formação Campestre", "area_ha": 52185.2, "area_pct": 29.31},
    ],
}
_LAND_STATE_OK = {
    "region_query": "RS",
    "available": True,
    "location": {"name": "Rio Grande do Sul", "kind": "state"},
    "year": 2025,
    "level": 2,
    "classes": [{"code": "3.2", "label": "Agricultura", "area_ha": 8.6e6, "area_pct": 32.3}],
}
_LAND_POINT_OK = {
    "available": True,
    "point": {"lat": -29.68, "lon": -53.81},
    "year": 2025,
    "level": 2,
    "class_id": 24,
    "code": "4.2",
    "label": "Área Urbanizada",
    "name_pt": "Área Urbanizada",
}


def _resp(answer: str, *, tools=("get_weather_trend",), data=(_WEATHER_OK,)) -> dict:
    return {"answer": answer, "model": "x", "tool_calls": list(tools), "data": list(data)}


class GroundingTests(unittest.TestCase):
    def test_numero_que_bate_com_a_tool_passa(self):
        case = {"id": "g1", "expect": {"grounded_numbers": True}}
        rep = checks.evaluate(case, _resp("A media foi de 18,2 graus, com maxima de 24,5 graus."))
        self.assertTrue(rep.ok, rep.failures)

    def test_numero_inventado_falha(self):
        case = {"id": "g2", "expect": {"grounded_numbers": True}}
        rep = checks.evaluate(case, _resp("A media foi de 31 graus."))
        self.assertFalse(rep.ok)

    def test_available_false_com_numero_de_medicao_falha(self):
        case = {"id": "g3", "expect": {"available": False, "grounded_numbers": True}}
        resp = _resp("Em Curitiba a media foi 22 graus.", data=())
        rep = checks.evaluate(case, resp)
        self.assertFalse(rep.ok)


class PrescriptionTests(unittest.TestCase):
    def test_imperativo_de_manejo_falha(self):
        case = {"id": "p1", "expect": {"no_prescription": True}}
        rep = checks.evaluate(case, _resp("A umidade esta baixa; irrigue a lavoura hoje."))
        self.assertFalse(rep.ok)

    def test_recomendacao_negada_passa(self):
        case = {"id": "p2", "expect": {"no_prescription": True}}
        rep = checks.evaluate(
            case, _resp("O servico e informativo e nao faz recomendacoes de manejo.")
        )
        self.assertTrue(rep.ok, rep.failures)

    def test_recomendacao_afirmativa_falha(self):
        case = {"id": "p3", "expect": {"no_prescription": True}}
        rep = checks.evaluate(case, _resp("Recomendo irrigar por causa do deficit."))
        self.assertFalse(rep.ok)


class StructuralTests(unittest.TestCase):
    def test_tool_call_faltando_falha(self):
        case = {"id": "t1", "expect": {"tool_calls": ["get_weather_trend"]}}
        rep = checks.evaluate(case, _resp("resposta qualquer", tools=()))
        self.assertFalse(rep.ok)

    def test_estado_esperado_mas_ponto_de_municipio_falha(self):
        case = {"id": "t2", "expect": {"is_state_level": True}}
        rep = checks.evaluate(case, _resp("choveu 10 mm"))
        self.assertFalse(rep.ok)

    def test_unavailable_wording(self):
        case = {"id": "t3", "expect": {"answer_indicates_unavailable": True}}
        ok = checks.evaluate(case, _resp("Nao ha dado para Curitiba: fora do escopo.", data=()))
        bad = checks.evaluate(case, _resp("Curitiba e uma cidade bonita.", data=()))
        self.assertTrue(ok.ok, ok.failures)
        self.assertFalse(bad.ok)


class LandUseTests(unittest.TestCase):
    def test_summary_municipio_ok(self):
        case = {
            "id": "lu1",
            "expect": {
                "tool_calls": ["get_land_use_summary"],
                "available": True,
                "location_name_contains": "Santa Maria",
                "year": 2025,
                "level": 2,
                "classes_grounded": True,
                "grounded_numbers": True,
            },
        }
        resp = _resp(
            "Em Santa Maria (2025), a Agricultura ocupa 35,9% da area; "
            "a Formacao Campestre, 29,3%.",
            tools=("get_land_use_summary",),
            data=(_LAND_SUMMARY_OK,),
        )
        rep = checks.evaluate(case, resp)
        self.assertTrue(rep.ok, rep.failures)

    def test_estado_via_kind(self):
        case = {"id": "lu2", "expect": {"is_state_level": True}}
        resp = _resp("...", tools=("get_land_use_summary",), data=(_LAND_STATE_OK,))
        self.assertTrue(checks.evaluate(case, resp).ok)

    def test_classe_inventada_falha(self):
        case = {"id": "lu3", "expect": {"classes_grounded": True}}
        resp = _resp(
            "O ponto e coberto por Floresta Ombrofila Densa.",
            tools=("get_land_use_at_point",),
            data=(_LAND_POINT_OK,),
        )
        self.assertFalse(checks.evaluate(case, resp).ok)

    def test_classe_grounded_ponto_passa(self):
        case = {"id": "lu4", "expect": {"classes_grounded": True, "year": 2025}}
        resp = _resp(
            "No ponto (-29.68, -53.81) a classe e Area Urbanizada (2025).",
            tools=("get_land_use_at_point",),
            data=(_LAND_POINT_OK,),
        )
        self.assertTrue(checks.evaluate(case, resp).ok)

    def test_percentual_inventado_falha(self):
        case = {"id": "lu5", "expect": {"grounded_numbers": True}}
        resp = _resp(
            "A Agricultura ocupa 80% da area.",
            tools=("get_land_use_summary",),
            data=(_LAND_SUMMARY_OK,),
        )
        self.assertFalse(checks.evaluate(case, resp).ok)

    def test_ano_divergente_falha(self):
        case = {"id": "lu6", "expect": {"year": 2020}}
        resp = _resp("...", tools=("get_land_use_summary",), data=(_LAND_SUMMARY_OK,))
        self.assertFalse(checks.evaluate(case, resp).ok)

    def test_payload_classifiers(self):
        resp = _resp("x", tools=(), data=(_WEATHER_OK, _LAND_SUMMARY_OK, _LAND_POINT_OK))
        self.assertEqual(len(checks.weather_payloads(resp)), 1)
        self.assertEqual(len(checks.land_use_payloads(resp)), 2)
        self.assertEqual(len(checks.tool_payloads(resp)), 3)


class DatasetTests(unittest.TestCase):
    def test_todos_os_datasets_sao_validos(self):
        files = list(_CASES_DIR.glob("*.json"))
        self.assertTrue(files, "nenhum dataset em cases/")
        for path in files:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("cases", data, path.name)
            ids = [c["id"] for c in data["cases"]]
            self.assertEqual(len(ids), len(set(ids)), f"ids repetidos em {path.name}")
            for case in data["cases"]:
                self.assertIn("question", case)
                self.assertIsInstance(case.get("expect"), dict, case["id"])

    def test_perguntas_ancora_presentes(self):
        data = json.loads((_CASES_DIR / "satelite_agro.json").read_text(encoding="utf-8"))
        blob = " ".join(c["question"].lower() for c in data["cases"])
        self.assertIn("porto alegre", blob)
        self.assertIn("rio grande do sul", blob)
        self.assertIn("santa maria", blob)
        self.assertIn("curitiba", blob)


if __name__ == "__main__":
    unittest.main()
