# Contrato da API acadêmica

As rotas ficam sob `/api/v1` e exigem o Bearer de serviço já provisionado. Para
rotas ligadas a usuário, o gateway deve enviar `X-Telegram-User-ID` de um usuário
já aprovado e provisionado; não existe autoinscrição. Toda mutação exige
`Idempotency-Key`.

Respostas são JSON, datas são ISO-8601 em UTC e listas retornam `items` e
`next_cursor`. Erros usam `detail` estável e o middleware propaga `X-Request-ID`.
`404` não revela entidades de outro usuário; `409` representa conflito de versão,
estado ou idempotência; `422` representa entrada inválida.

As sessões seguem `active -> paused -> active -> completed/cancelled` ou
`active -> completed/cancelled`. Duração é calculada no servidor, subtraindo
pausas. Objetivos, editais e ciclos ativos usam índices parciais no banco como
segunda camada de proteção.

## Planejador adaptativo

- `POST /api/v1/study/plan/proposals`: simula e cria proposta temporária;
- `GET /api/v1/study/plan/proposals/current`: consulta a proposta pendente;
- `POST /api/v1/study/plan/proposals/{id}/confirm`: confirma e persiste;
- `POST /api/v1/study/plan/proposals/{id}/cancel`: cancela somente a proposta;
- `POST /api/v1/study/plan/replan/proposals`: simula revisão do plano existente;
- `GET /api/v1/study/plan/today`: calendário do dia local do perfil;
- `GET /api/v1/study/plan/week`: resumo de segunda a domingo;
- `GET /api/v1/study/plan/status`: execução, atrasos e próxima revisão;
- `GET /api/v1/study/next-item`: próximo item ainda planejado.

`POST /api/v1/study/plan` permanece como adaptador do contrato antigo, mas por
segurança agora devolve uma proposta pendente. Clientes devem migrar para o
fluxo explícito de proposta e confirmação.

O contrato completo do planejador e seus limites estão em
`docs/12-PLANEJADOR-ADAPTATIVO.md`.
