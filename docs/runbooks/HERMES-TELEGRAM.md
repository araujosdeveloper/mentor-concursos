# Runbook — Hermes Telegram Mentor Concursos

## Ativação controlada

1. Confira que `secrets/telegram_bot_token`, `secrets/mentor_api_service_token`
   e `secrets/hermes_context_hmac_key` existem, têm modo 600 e não serão
   exibidos. O token Telegram é obtido manualmente no BotFather; os demais são
   gerados idempotentemente por `scripts/prepare-production-env.sh`.
2. Valide `docker compose --profile mentor-concursos-hermes config --quiet`.
3. Inicie apenas `docker compose --profile mentor-concursos-hermes up -d --no-deps mentor-concursos-hermes`.
4. Aguarde o healthcheck do PID/state do gateway.
5. Para OAuth novo, execute `hermes auth add openai-codex --type oauth --no-browser`
   no serviço efêmero e pare para a ação humana quando surgir URL/código.
6. Consulte `hermes model --refresh`, selecione um modelo oferecido e execute
   um prompt mínimo sem dados reais.
7. Abra o bot e envie `/start`; liste com `hermes pairing list` e aprove somente
   o request ID conferido no terminal.

## Operação e revogação

- Listar autorização: `hermes pairing list`.
- Revogar: `hermes pairing revoke telegram <user-id>`.
- Limpar pendências: `hermes pairing clear-pending`.
- Estado do provider: `hermes auth status openai-codex`.
- Health: `docker compose --profile mentor-concursos-hermes ps`.
- Logs: `docker logs --since 10m mentor-concursos-hermes`; nunca colar tokens,
  cookies, OAuth ou mensagens privadas em relatórios.

## Backup/restore

Faça backup do volume em diretório protegido, sem copiar `.env` ou secrets:

```bash
install -d -m 700 /opt/backups/mentor-concursos/hermes
docker run --rm -v mentor_concursos_hermes_data:/data:ro \
  -v /opt/backups/mentor-concursos/hermes:/backup \
  alpine:3.20 tar czf /backup/hermes-data-<timestamp>.tar.gz -C /data .
sha256sum /opt/backups/mentor-concursos/hermes/hermes-data-<timestamp>.tar.gz
```

Teste restauração somente em volume temporário nomeado e removível após a
validação. Nunca sobrescreva o volume principal sem checkpoint e aprovação.

## Diagnóstico e rollback

Se o gateway estiver unhealthy, verifique `docker logs`, `gateway.pid`,
`gateway_state.json`, espaço e conectividade ao proxy. Não use `--yolo`, não
adicione allowlist ampla e não conecte core ao Hermes. Rollback: pare somente
Hermes, restaure a imagem/digest e o backup validados, e suba novamente com o
mesmo profile. O volume principal não deve ser removido durante diagnóstico.
