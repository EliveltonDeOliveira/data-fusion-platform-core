"""CLI da ingestão. Roda sob demanda. Determinístico, idempotente, sem LLM.

python -m satelite_agro_ingestion                 # todas as etapas
python -m satelite_agro_ingestion --only land-use raster
python -m satelite_agro_ingestion --skip raster
"""

from __future__ import annotations

import argparse
import sys

from . import db
from .config import UF_NAME, Settings
from .embeddings import embed_texts, to_vector_literal
from .land_use import LandUseStats, stream_land_use
from .legend import validate_legend
from .municipios import fetch_municipios
from .rag_corpus import build_corpus, documents_in
from .raster import clip_raster, fetch_uf_boundary

STEPS = ("legend", "municipios", "land-use", "raster", "rag-corpus")


def _log(msg: str) -> None:
    print(msg, flush=True)


def step_legend(settings: Settings) -> None:
    csv_path = settings.raw(settings.legend_csv)
    if not csv_path.exists():
        raise FileNotFoundError(f"legenda não encontrada: {csv_path}")
    with db.connect(settings.database_url) as conn, conn.cursor() as cur:
        cur.execute("SELECT class_id, name_pt, hex_color FROM satelite_agro.mapbiomas_legend")
        db_legend = {cid: (name, hexc) for cid, name, hexc in cur.fetchall()}

    report = validate_legend(csv_path, db_legend)
    _log(f"  legenda: {report.csv_classes} classes no CSV, {len(db_legend)} no seed")
    for line in report.name_mismatch:
        _log(f"  [aviso] nome diverge — {line}")
    if not report.ok:
        for cid in report.missing_in_db:
            _log(f"  [erro] class_id {cid} do CSV não está no seed")
        for line in report.hex_mismatch:
            _log(f"  [erro] hex diverge — {line}")
        raise SystemExit("seed da legenda divergiu do CSV oficial — revisar 000002")


def step_municipios(settings: Settings) -> None:
    rows = fetch_municipios(settings.ibge_api_base)
    if not rows:
        raise SystemExit("IBGE não retornou municípios")
    with db.connect(settings.database_url) as conn:
        written = db.replace_municipios(conn, rows)
    _log(f"  municípios: {written} gravados ({UF_NAME})")


def step_land_use(settings: Settings) -> None:
    xlsx_path = settings.raw(settings.stats_xlsx)
    if not xlsx_path.exists():
        raise FileNotFoundError(f"planilha não encontrada: {xlsx_path}")

    with db.connect(settings.database_url) as conn:
        legend_ids = db.fetch_legend_class_ids(conn)
        geocodes = db.fetch_municipio_geocodes(conn)
        if not geocodes:
            raise SystemExit("rode a etapa 'municipios' antes de 'land-use'")

        stats = LandUseStats()
        rows = stream_land_use(
            xlsx_path,
            state_name=UF_NAME,
            legend_class_ids=legend_ids,
            known_geocodes=geocodes,
            stats=stats,
        )
        written = db.replace_land_use(conn, rows)

    _log(
        f"  uso da terra: {written} linhas de {len(stats.municipios)} municípios, "
        f"anos {min(stats.years, default='-')}-{max(stats.years, default='-')}, "
        f"biomas {sorted(stats.biomes)} "
        f"({stats.cells_summed} células somadas de {stats.rows_kept} linhas do RS)"
    )
    if stats.unknown_geocodes:
        _log(
            f"  [aviso] {len(stats.unknown_geocodes)} geocodes fora da malha de "
            f"municípios, pulados: {sorted(stats.unknown_geocodes)}"
        )
    if stats.unknown_class_ids:
        raise SystemExit(
            f"class_id sem correspondência na legenda: "
            f"{sorted(stats.unknown_class_ids)} — revisar seed 000002"
        )


def step_raster(settings: Settings) -> None:
    national = settings.raw(settings.coverage_raster)
    if not national.exists():
        raise FileNotFoundError(f"GeoTIFF nacional não encontrado: {national}")
    geoms = fetch_uf_boundary(settings.ibge_api_base, settings.malha_quality)
    result = clip_raster(national, geoms, settings.clipped_raster_path)
    _log(
        f"  raster: {result.out_path} ({result.width}x{result.height}, {result.crs}); "
        f"nacional preservado em {national}"
    )


def step_rag_corpus(settings: Settings) -> None:
    if not settings.gemini_api_key:
        raise SystemExit("GEMINI_API_KEY é obrigatório para a etapa rag-corpus (embedding)")

    chunks = build_corpus(settings.raw_dir)
    if not chunks:
        raise SystemExit("nenhum trecho gerado pro corpus RAG")

    vectors = embed_texts((content for _, _, content in chunks), api_key=settings.gemini_api_key)
    rows = (
        (doc, idx, content, to_vector_literal(vec))
        for (doc, idx, content), vec in zip(chunks, vectors, strict=True)
    )
    with db.connect(settings.database_url) as conn:
        written = db.replace_rag_chunks(conn, rows)
    _log(f"  corpus RAG: {written} trechos de {len(documents_in(chunks))} documentos")


RUNNERS = {
    "legend": step_legend,
    "municipios": step_municipios,
    "land-use": step_land_use,
    "raster": step_raster,
    "rag-corpus": step_rag_corpus,
}


def _selected_steps(args: argparse.Namespace) -> list[str]:
    if args.only:
        return [s for s in STEPS if s in args.only]
    return [s for s in STEPS if s not in args.skip]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="satelite-agro-ingestion")
    parser.add_argument("--only", nargs="+", choices=STEPS, default=[])
    parser.add_argument("--skip", nargs="+", choices=STEPS, default=[])
    args = parser.parse_args(argv)

    settings = Settings.from_env()
    steps = _selected_steps(args)
    _log(f"ingestão · ano-alvo {settings.target_year} · etapas: {', '.join(steps)}")
    for name in steps:
        _log(f"[{name}]")
        RUNNERS[name](settings)
    _log("ingestão concluída")
    return 0


if __name__ == "__main__":
    sys.exit(main())
