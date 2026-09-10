# ADR-015 — Recuperação híbrida

A recuperação combina busca textual PostgreSQL (`tsvector`/GIN) e cosine em
pgvector por Reciprocal Rank Fusion (RRF), com `k=60`, peso lexical 5,0 para
preservar termos jurídicos exatos, ordenação determinística e limite controlado.
O peso não soma scores de escalas incompatíveis: ele pondera apenas as parcelas
de rank do RRF e é auditado junto da consulta. Somente chunks de versões
`indexed` retornam; rejeitados e superseded ficam excluídos por padrão.
Cada consulta é auditada por hash, filtros, IDs e scores, sem persistir o
texto da consulta.
