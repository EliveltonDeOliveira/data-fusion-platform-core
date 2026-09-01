from __future__ import annotations

from pathlib import Path

import pytest
from satelite_agro_ingestion.rag_corpus import (
    build_corpus,
    chunk_text,
    documents_in,
)


def test_chunk_text_janelas_dentro_do_tamanho():
    text = " ".join(f"palavra{i}" for i in range(500))
    chunks = chunk_text(text, size=100, overlap=20)
    assert len(chunks) > 1
    assert all(len(c) <= 110 for c in chunks)  # folga: última palavra pode passar um pouco


def test_chunk_text_cobre_texto_inteiro_sem_perder_conteudo():
    text = " ".join(f"palavra{i}" for i in range(50))
    chunks = chunk_text(text, size=200, overlap=30)
    assert "palavra0" in chunks[0]
    assert "palavra49" in chunks[-1]


def test_chunk_text_sobreposicao_entre_janelas_consecutivas():
    text = " ".join(f"w{i}" for i in range(200))
    chunks = chunk_text(text, size=100, overlap=30)
    # as ultimas palavras do 1o chunk reaparecem em algum lugar do 2o (overlap real)
    tail = set(chunks[0].split(" ")[-3:])
    assert tail & set(chunks[1].split(" "))


def test_chunk_text_texto_curto_vira_um_chunk_so():
    assert chunk_text("um texto bem curto", size=1200, overlap=200) == ["um texto bem curto"]


def test_chunk_text_normaliza_espacos_bagunçados():
    chunks = chunk_text("linha1  \n  linha2\n\n\nlinha3", size=1200, overlap=200)
    assert chunks == ["linha1 linha2 linha3"]


def test_build_corpus_le_todos_os_documentos(monkeypatch, tmp_path: Path):
    docs = ("a.pdf", "b.pdf")
    subdir = tmp_path / "documentos_e_notas_tecnicas"
    subdir.mkdir()
    for name in docs:
        (subdir / name).write_bytes(b"stub")

    monkeypatch.setattr(
        "satelite_agro_ingestion.rag_corpus.extract_text",
        lambda path: f"conteudo de {path.name} " * 100,
    )
    rows = build_corpus(tmp_path, documents=docs)
    assert {r[0] for r in rows} == set(docs)
    # chunk_index comeca em 0 e e contiguo por documento
    for doc in docs:
        idxs = [r[1] for r in rows if r[0] == doc]
        assert idxs == list(range(len(idxs)))


def test_build_corpus_documento_ausente_falha_alto(tmp_path: Path):
    (tmp_path / "documentos_e_notas_tecnicas").mkdir()
    with pytest.raises(FileNotFoundError):
        build_corpus(tmp_path, documents=("nao-existe.pdf",))


def test_documents_in():
    rows = [("a.pdf", 0, "x"), ("b.pdf", 0, "y"), ("a.pdf", 1, "z")]
    assert documents_in(rows) == ["a.pdf", "b.pdf"]
