# Runbook de implantação do núcleo

Este runbook não autoriza iniciar o Hermes.

1. Confirme branch, commit, worktree e espaço/recursos da VPS.
2. Registre `docker ps`, redes e volumes com prefixo `mentor-concursos`.
3. Confirme ausência de conflitos de nomes.
4. Execute `scripts/prepare-production-env.sh` sem exibir `.env` ou secrets.
   O script cria idempotentemente POSTGRES_PASSWORD, REDIS_PASSWORD,
   `secrets/mentor_api_service_token` e
   `secrets/hermes_context_hmac_key` quando ausentes, sempre com modo 600.
5. Obtenha o token do bot diretamente no BotFather do Telegram. Esse valor não
   é gerável localmente: grave-o manualmente em
   `secrets/telegram_bot_token`, sem colocá-lo na linha de comando, com modo
   600. Não use token de outro projeto e nunca o inclua em Git ou relatórios.
6. Crie checkpoint fora do Git com configurações sem segredos e checksums SHA-256.
7. Execute `docker compose config --quiet` e `scripts/validate-foundation.sh`.
8. Construa somente `mentor-concursos-api` e `mentor-concursos-worker`.
9. Baixe as três imagens por digest.
10. Inicie explicitamente PostgreSQL, Redis e Tika e aguarde saúde.
11. Execute `scripts/apply-migrations.sh`.
12. Inicie explicitamente API e worker e aguarde saúde.
13. Confirme que existem somente os cinco containers do núcleo, sem `ports`, e que Hermes não existe.
14. Valide banco, vector, Redis, Tika, autenticação, redes, reinício e recursos.
15. Execute o runbook de backup/restauração.

Rollback de aplicação recria somente API/worker pela imagem anterior. Não remova volumes e não reverta migration destrutivamente. Em falha de infraestrutura, pare somente serviços `mentor-concursos-*` criados nesta implantação e preserve o banco para diagnóstico.
