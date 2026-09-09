# Runbook de implantação do núcleo

Este runbook não autoriza iniciar o Hermes.

1. Confirme branch, commit, worktree e espaço/recursos da VPS.
2. Registre `docker ps`, redes e volumes com prefixo `mentor-concursos`.
3. Confirme ausência de conflitos de nomes.
4. Execute `scripts/prepare-production-env.sh` sem exibir `.env` ou secrets.
5. Crie checkpoint fora do Git com configurações sem segredos e checksums SHA-256.
6. Execute `docker compose config --quiet` e `scripts/validate-foundation.sh`.
7. Construa somente `mentor-concursos-api` e `mentor-concursos-worker`.
8. Baixe as três imagens por digest.
9. Inicie explicitamente PostgreSQL, Redis e Tika e aguarde saúde.
10. Execute `scripts/apply-migrations.sh`.
11. Inicie explicitamente API e worker e aguarde saúde.
12. Confirme que existem somente os cinco containers do núcleo, sem `ports`, e que Hermes não existe.
13. Valide banco, vector, Redis, Tika, autenticação, redes, reinício e recursos.
14. Execute o runbook de backup/restauração.

Rollback de aplicação recria somente API/worker pela imagem anterior. Não remova volumes e não reverta migration destrutivamente. Em falha de infraestrutura, pare somente serviços `mentor-concursos-*` criados nesta implantação e preserve o banco para diagnóstico.
