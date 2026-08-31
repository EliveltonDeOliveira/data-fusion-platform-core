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
