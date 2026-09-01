"""Corpus RAG: extrai e fragmenta o subconjunto dos ATBDs da MapBiomas Coleção
11 usado nesta demo, a partir dos PDFs baixados manualmente pelo dono do
projeto (ver `Settings.raw_dir` / `DOCS_SUBDIR` para onde a etapa espera
encontrá-los, conforme o ambiente de execução).

Subconjunto deliberado (nem todo PDF baixado entra): cobre metodologia geral,
o bioma dominante do RS (Pampa) e as classes mais relevantes pro escopo atual
(agricultura, pastagem/campo, área urbana) mais o apêndice de acurácia, que
ajuda a responder "o quão confiável é esse dado". Fora do escopo desta rodada:
módulo de agricultura genérico (sobreposto ao apêndice de agricultura já
incluído) e os apêndices de usina fotovoltaica/eólica (fora do que o projeto
hoje monitora). Podem entrar depois, ajustando `DOCUMENTS`.

Fragmentação é determinística (sem LLM): documento inteiro vira uma string
normalizada, dividida em janelas de tamanho fixo com sobreposição por palavra.
O embedding (fora deste módulo, ver `embeddings.py`) é a única chamada de rede
da etapa — computa um vetor por trecho, não gera texto novo.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from pypdf import PdfReader

DOCS_SUBDIR = "documentos_e_notas_tecnicas"

DOCUMENTS: tuple[str, ...] = (
    "ATBD-General-Collection-11-versao-1.pdf",
    "Pampa-Appendix-ATBD-Collection-11.pdf",
    "Agriculture-and-Forest-Plantation-Appendix_C11-REVISADO.pdf",
    "Pasture-Appendix-ATBD-Collection-11-V1.pdf",
    "Urban-Areas-ATBD-Collection-11_v1.pdf",
    "Accuracy-Assessment-Appendix-Collection-11-v1.pdf",
)

CHUNK_SIZE = 1200
CHUNK_OVERLAP = 200

RagChunkRow = tuple[str, int, str]  # source_document, chunk_index, content


def extract_text(path: Path) -> str:
    reader = PdfReader(str(path))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages)


def _normalize(text: str) -> str:
    return " ".join(text.split())


def chunk_text(text: str, *, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Janelas de ~`size` caracteres por palavras inteiras, com sobreposição."""
    words = _normalize(text).split(" ")
    words = [w for w in words if w]
    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = start
        length = 0
        while end < len(words) and (length == 0 or length + len(words[end]) + 1 <= size):
            length += len(words[end]) + 1
            end += 1
        chunks.append(" ".join(words[start:end]))
        if end >= len(words):
            break
        back = 0
        cut = end
        while cut > start and back < overlap:
            cut -= 1
            back += len(words[cut]) + 1
        start = max(cut, start + 1)
    return chunks


def build_corpus(raw_dir: Path, *, documents: tuple[str, ...] = DOCUMENTS) -> list[RagChunkRow]:
    rows: list[RagChunkRow] = []
    for filename in documents:
        path = raw_dir / DOCS_SUBDIR / filename
        if not path.exists():
            raise FileNotFoundError(f"documento do corpus RAG não encontrado: {path}")
        text = extract_text(path)
        for idx, chunk in enumerate(chunk_text(text)):
            rows.append((filename, idx, chunk))
    return rows


def documents_in(rows: Iterator[RagChunkRow] | list[RagChunkRow]) -> list[str]:
    return sorted({doc for doc, _, _ in rows})
