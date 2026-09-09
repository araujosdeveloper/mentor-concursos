# ADR-010 — Núcleo acadêmico determinístico

## Decisão

Implementar o domínio acadêmico em PostgreSQL com migrações versionadas,
constraints, transições explícitas e API `/api/v1`. O Hermes usa somente a API
com Bearer; não recebe acesso a banco, Redis ou Tika.

## Consequências

As métricas são recalculáveis a partir do histórico. O desenho é mais verboso
que uma tabela de progresso livre, mas evita que uma chamada de modelo altere
estado acadêmico sem validação ou auditoria.
