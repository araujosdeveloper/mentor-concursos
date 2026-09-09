# Runbook — migrações acadêmicas

1. Faça checkpoint e backup lógico antes da mudança.
2. Execute `./scripts/apply-migrations.sh`; o executor usa advisory lock e
   registra checksum.
3. Confirme `SELECT version, checksum_sha256 FROM mentor_concursos.schema_migrations`.
4. Uma segunda execução deve registrar `migration_already_applied`; checksum
   divergente interrompe a operação.
5. Corrija problemas por nova forward migration. Não edite migração aplicada.

O seed referencial é independente: `./scripts/seed-reference-taxonomy.sh`.
O provisionamento real de Roberto é idempotente em
`./scripts/provision-roberto.sh`; ele não cria objetivo, edital ou concurso.
