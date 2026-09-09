# ADR-009 — Autorização Telegram por DM pairing

## Status

Aceito — Fase 2A.

## Decisão

O bot privado `@MentorConcursosRobertoBot` usa polling, `dm_policy: pairing`,
`unauthorized_dm_behavior: pair` e `group_policy: disabled`. O primeiro usuário
não é aceito automaticamente: o operador deve listar a solicitação e aprovar
explicitamente o request ID. Após a aprovação, somente o user ID de Roberto
permanece no pairing store; grupos e usuários desconhecidos continuam negados.

## Revogação e rotação

`hermes pairing revoke telegram <id>` revoga um usuário; `pairing clear-pending`
remove solicitações não aprovadas. A rotação do token Telegram é feita trocando
o arquivo Docker secret com modo 600 e recriando apenas o serviço. O token nunca
é passado como valor Compose, logado ou incluído em backup documental.
