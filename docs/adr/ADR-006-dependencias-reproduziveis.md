# ADR-006 — Lockfiles Python com hashes

- Status: aceito
- Data: 2026-09-08

## Decisão

Manter `pyproject.toml` como declaração direta e dois locks gerados por pip-tools 7.5.0 sob
pip 25.1.1: runtime e desenvolvimento. Todas as versões transitivas e artefatos são fixados por
hash. Imagens instalam somente o lock de runtime usando `--require-hashes --no-deps`; CI compara
locks regenerados e audita vulnerabilidades conhecidas.

## Consequências

Builds deixam de resolver versões silenciosamente. Atualizar exige regeneração explícita,
revisão do diff, auditoria e testes. O lock pode listar hashes de várias plataformas; isso
mantém verificação criptográfica sem limitar o desenvolvimento, enquanto a imagem base amd64
continua fixada por digest.
