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

Nesta fase não há endpoint de questões, conteúdo, RAG, ingestão ou comandos
acadêmicos Telegram.
