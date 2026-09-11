# Segurança

## Isolamento

Todos os nomes de redes e volumes são exclusivos e prefixados. O Hermes usa `mentor_concursos_hermes_data` e somente a rede `mentor-concursos-agent`. Credenciais nunca são reutilizadas entre projetos. Os serviços rodam sem modo privilegiado e com `no-new-privileges`; API e worker usam usuário não root.

Nenhuma porta é publicada no host. As redes Compose são internas. Não há Traefik. A futura interface Telegram deverá validar identidade, autorização e replay antes de entrar em produção.

## Segredos e dados

`.env.example` contém somente placeholders. O `.env` real usa modo 600; `secrets/` usa 700 e seus arquivos usam 600. O token da API tem ao menos 256 bits. O Docker secret host permanece 600; um entrypoint mínimo, executado como root, copia-o para `/run/secrets/mentor_api_service_token` em modo 400 e transfere o processo imediatamente para UID/GID 10001. A API compara em tempo constante e nunca registra o valor. Logs não podem conter tokens, senhas, conteúdo integral de documentos ou dados pessoais desnecessários. `auth.json`, tokens, bancos locais, uploads, documentos, backups e logs são bloqueados pelo `.gitignore`.

Documentos entram em `storage/inbox` e, após processamento validado, migram para `storage/processed`; apenas `.gitkeep` é versionado. Cada item futuro deve possuir hash, origem, licença/autorização e estado de processamento.

## Ameaças e controles iniciais

- **Prompt injection documental:** conteúdo recuperado é dado não confiável; nunca concede ferramentas ou autoridade.
- **Alucinação:** resposta baseada em fonte, incerteza explícita e rastreabilidade.
- **Supply chain:** imagens com versão explícita; Hermes exige referência imutável aprovada com digest.
- **Movimento lateral:** redes mínimas e ausência de socket Docker/host mounts.
- **Exfiltração:** respostas e logs minimizados; backups criptografados e segregados; egress somente pelo proxy com allowlist, bloqueio de redes privadas e CONNECT restrito à porta 443.

Endpoints acadêmicos futuros devem depender do mesmo controle de autenticação ou de mecanismo mais restritivo. Saúde permanece sem autenticação por não haver porta publicada. Métricas e auth-check exigem Bearer token e rate limiting distribuído no Redis, em modo fail-closed. O proxy não registra URL completa nem cabeçalhos e não contém credenciais.

## Rotação do token de serviço

1. Gere um novo token de 256 bits ou mais em arquivo temporário protegido.
2. Substitua atomicamente `secrets/mentor_api_service_token`, sem exibir seu conteúdo.
3. Reinicie somente API e, futuramente, o Hermes dedicado.
4. Valide 401 para o token anterior e 200 para o novo.
5. Remova de forma segura qualquer cópia temporária. Nunca registre o token em ticket ou log.

## Contexto Telegram assinado

O Hermes envia, além do header legado, um envelope `X-Hermes-Context` com
`telegram_user_id`, `chat_id`, timestamp e nonce, acompanhado de assinatura
HMAC-SHA256 em `X-Hermes-Signature`. A chave dedicada
`hermes_context_hmac_key` é montada somente na API e no Hermes. A API valida a
assinatura com comparação em tempo constante, exige frescor de 60 segundos e
consome o nonce em Redis com `NX/EX` por 120 segundos para impedir replay.

Durante a migração, `REQUIRE_SIGNED_CONTEXT=false` aceita o header legado apenas
quando não há envelope; um envelope presente e inválido nunca sofre downgrade.
Após observar consistência operacional, ativar `REQUIRE_SIGNED_CONTEXT=true` e
remover o caminho legado em alteração posterior. A chave HMAC deve ser rotada
independentemente do Bearer de serviço, recriando apenas API e Hermes e
validando replay, expiração e discrepâncias sem registrar IDs ou segredos.
