# ADR-012 — Idempotência das mutações acadêmicas

Toda mutação exige `Idempotency-Key`. A API registra chave, escopo e SHA-256 do
payload. Repetição com o mesmo fingerprint devolve a resposta persistida;
reutilização com fingerprint diferente retorna 409. As chaves expiram em 24
horas. O registro ocorre na mesma transação da mutação e da auditoria.
