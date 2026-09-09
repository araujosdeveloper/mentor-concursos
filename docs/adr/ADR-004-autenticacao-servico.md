# ADR-004: autenticação Hermes para API

- Status: aceito
- Data: 2026-09-08

## Contexto

O Hermes futuro precisa chamar endpoints internos sem receber credenciais de banco. O segredo não pode residir no Compose ou em variável visível na inspeção do container.

## Decisão

Usar token opaco de pelo menos 256 bits em `Authorization: Bearer`. O arquivo host `secrets/mentor_api_service_token` é montado como Docker secret em `/run/secrets/mentor_api_service_token`. A API lê o arquivo por requisição, remove a quebra final e compara bytes com `secrets.compare_digest`. Ausência, esquema incorreto e token inválido retornam o mesmo 401 com `WWW-Authenticate: Bearer`. O valor nunca entra em logs.

Saúde permanece pública apenas na rede Docker interna. `/api/internal/auth-check` é uma rota técnica sem domínio acadêmico para validar o contrato. Todo endpoint acadêmico futuro deve aplicar a dependência de autenticação.

## Consequências

A leitura por requisição permite rotação do lado da API. A integração Hermes permanece pendente e deverá suportar token por arquivo antes da ativação.
