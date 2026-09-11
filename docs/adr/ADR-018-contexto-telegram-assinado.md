# ADR-018 — Contexto Telegram assinado Hermes → API

## Status

Aceito para rollout gradual.

## Contexto

O Bearer de serviço autentica o processo Hermes, mas um header Telegram cru não
prova a origem da identidade do remetente. Em cenário multiusuário isso permite
forjar o ID de outro usuário.

## Decisão

O Hermes assina um envelope JSON contendo `telegram_user_id`, `chat_id`, `ts` e
`nonce` com uma chave HMAC dedicada. A API valida Bearer, assinatura com
`compare_digest`, janela de 60 segundos e nonce único em Redis por 120 segundos
antes de consultar o usuário. O header `X-Telegram-User-ID` permanece somente
para compatibilidade durante a migração e nunca prevalece sobre o envelope.

`REQUIRE_SIGNED_CONTEXT` permanece `false` inicialmente: requests sem envelope
seguem o caminho legado; requests com envelope inválido são rejeitados. Depois
de observação operacional, a flag será ativada e o caminho legado removido em
forward change separado.

## Consequências

Há uma chave adicional a rotacionar, uma chamada Redis por request e proteção
contra replay. A API e o Hermes precisam ler a chave; demais serviços não devem
recebê-la. A operação é fail-closed quando a chave, assinatura, frescor ou
Redis não podem ser validados.
