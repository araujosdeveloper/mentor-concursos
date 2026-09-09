# Núcleo acadêmico determinístico

O domínio fica no schema `mentor_concursos` e usa UUIDs, `TIMESTAMPTZ` em UTC,
foreign keys restritivas e índices parciais para invariantes de estado. A
migração `002_academic_core.sql` é aplicada pelo executor existente, sob
advisory lock e com SHA-256 registrado em `schema_migrations`. Alterações de
estrutura são feitas por forward migration; não há rollback destrutivo.

As entidades cobrem perfil, taxonomia referencial, objetivos, versões de edital,
ciclos, itens, sessões, pausas, domínio de mastery, auditoria e idempotência.
Nenhuma tabela acadêmica é gravada diretamente pelo Hermes: mutações passam pela
API autenticada.

## Invariantes

- um objetivo principal ativo por usuário;
- uma versão ativa de edital por objetivo;
- um ciclo ativo por objetivo;
- uma sessão `active`/`paused` por usuário;
- uma pausa aberta por sessão;
- transições e cálculo de duração feitos no servidor;
- `version` em objetivos, ciclos e sessões para concorrência otimista;
- auditoria append-only para mutações;
- `Idempotency-Key` com fingerprint impede repetição inconsistente.

`topic_mastery` começa em `not_started`; somente serviço determinístico pode
alterar evidências. IA não marca `consolidated` nesta fase.
