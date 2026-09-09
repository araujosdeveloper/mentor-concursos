# Runbook de diagnóstico operacional

1. Confirme `git status`, branch e `docker compose config --quiet` sem exibir `.env`.
2. Use `docker compose ps` e `docker stats --no-stream` somente para containers Mentor.
3. Inspecione health com `docker inspect --format '{{json .State.Health}}' <container>`.
4. Consulte logs com `docker compose logs --tail 100 <serviço>`; não copie tokens no chamado.
5. Para API, valide live/ready internamente e preserve `X-Request-ID` na investigação.
6. Para 401, confira existência/permissão do secret sem ler seu conteúdo. Para 429, aguarde
   `Retry-After`; para 503 em rota interna, valide Redis.
7. Para egress, confirme as duas redes do proxy e que o cliente usa `HTTPS_PROXY`; 403 é a
   negação esperada para destino fora da allowlist. Nunca amplie para `allow all`.
8. Antes de recriar container Mentor, registre estado e confirme pelo nome/labels que ele
   pertence ao projeto. Não execute prune nem remova volumes.
