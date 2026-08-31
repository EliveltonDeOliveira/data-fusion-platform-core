"""Ingestão de dado público do Projeto 1 (Satélite + Agro/GIS).

Pipeline determinístico, sem LLM: lê os arquivos crus baixados manualmente
(MapBiomas) e as APIs institucionais (IBGE), funde e grava pré-agregado no
Postgres. Agregação espacial pesada acontece aqui, nunca numa consulta ao vivo.
"""
