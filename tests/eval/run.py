"""Roda o dataset dourado contra um agente ja no ar.

    AGENT_URL=<url-do-agente> python run.py [--dataset cases/satelite_agro.json]
                                            [--case ID] [--json] [--timeout 180]

So stdlib. Envia cada pergunta a `POST {AGENT_URL}/ask`, aplica as checagens de
`checks.py` e imprime um relatorio. Sai com codigo 1 se algum caso falhar — da
pra usar em CI. Consome cota do provedor de LLM do agente.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

import checks

_HERE = Path(__file__).parent


def ask(agent_url: str, question: str, timeout: float) -> dict:
    payload = json.dumps({"question": question}).encode()
    req = urllib.request.Request(  # noqa: S310 — URL vem de env do operador, nao de entrada externa
        agent_url.rstrip("/") + "/ask",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return json.load(resp)


def load_dataset(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def run(agent_url: str, dataset: dict, *, only: str | None, timeout: float) -> list[checks.Report]:
    reports: list[checks.Report] = []
    for case in dataset.get("cases", []):
        if only and case.get("id") != only:
            continue
        try:
            response = ask(agent_url, case["question"], timeout)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            rep = checks.Report(case_id=str(case.get("id", "?")))
            rep.failures.append(f"falha ao chamar o agente: {exc}")
            reports.append(rep)
            continue
        reports.append(checks.evaluate(case, response))
    return reports


def _print_human(reports: list[checks.Report]) -> None:
    for rep in reports:
        mark = "PASS" if rep.ok else "FAIL"
        print(f"[{mark}] {rep.case_id}")
        for f in rep.failures:
            print(f"       x {f}")
        for w in rep.warnings:
            print(f"       ! {w}")
    passed = sum(r.ok for r in reports)
    print(f"\n{passed}/{len(reports)} casos passaram")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default=str(_HERE / "cases" / "satelite_agro.json"))
    parser.add_argument("--case", dest="only", default=None, help="roda so um caso pelo id")
    parser.add_argument("--json", action="store_true", help="saida em JSON")
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--agent-url", default=os.environ.get("AGENT_URL", ""))
    args = parser.parse_args()

    if not args.agent_url:
        parser.error("defina AGENT_URL no ambiente ou passe --agent-url")

    dataset = load_dataset(Path(args.dataset))
    reports = run(args.agent_url, dataset, only=args.only, timeout=args.timeout)

    if args.json:
        print(
            json.dumps(
                [
                    {"case": r.case_id, "ok": r.ok, "failures": r.failures, "warnings": r.warnings}
                    for r in reports
                ],
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        _print_human(reports)

    return 0 if all(r.ok for r in reports) and reports else 1


if __name__ == "__main__":
    sys.exit(main())
