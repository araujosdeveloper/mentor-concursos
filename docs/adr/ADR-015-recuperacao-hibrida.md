# ADR-015 — Recuperação híbrida

A recuperação combina busca textual PostgreSQL (`tsvector`/GIN) e cosine em
pgvector com ordenação determinística e limite controlado. Somente chunks de
versões `indexed` retornam; rejeitados e superseded ficam excluídos por padrão.
Cada consulta é auditada por hash, filtros, IDs e scores, sem persistir o
texto da consulta.
