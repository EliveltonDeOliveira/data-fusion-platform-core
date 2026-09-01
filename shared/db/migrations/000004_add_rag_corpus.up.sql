-- Corpus RAG (metodologia MapBiomas): trechos de ATBD embarcados, para busca
-- por similaridade. Populado pelo job de ingestão (projects/satelite_agro/
-- ingestion), a partir dos PDFs baixados manualmente. Embedding: gemini-embedding-2
-- (3072 dimensões), chamado uma vez por trecho no momento da ingestão.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE satelite_agro.rag_chunk (
    id               bigserial PRIMARY KEY,
    source_document  text NOT NULL,
    chunk_index      smallint NOT NULL,
    content          text NOT NULL,
    embedding        vector(3072) NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_document, chunk_index)
);

COMMENT ON TABLE satelite_agro.rag_chunk IS
    'Trechos dos ATBDs da MapBiomas Coleção 11 (metodologia/classificação), '
    'com embedding pré-computado. Corpus pequeno (dezenas a poucas centenas de '
    'linhas) — busca por similaridade exata (<=>), sem índice aproximado.';
