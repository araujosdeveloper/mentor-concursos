# Arquitetura

## Visão geral

A API FastAPI é o único limite de acesso do agente. Ela atende na porta 8080 somente dentro das redes Docker. O worker executa tarefas assíncronas e acessa PostgreSQL, Redis e Tika. O Hermes possui container, volume e rede próprios e não compartilha identidade, memória ou credenciais com qualquer outro projeto.

| Serviço | Rede core | Rede agent | Persistência | Responsabilidade |
| --- | --- | --- | --- | --- |
| API | sim | sim | banco via core | contrato interno e saúde |
| Worker | sim | não | banco/Redis via core | processamento futuro |
| PostgreSQL | sim | não | volume dedicado | dados UTC e vetores |
| Redis | sim | não | volume runtime sem persistência lógica | fila e locks reconstruíveis |
| Tika | sim | não | nenhuma | extração documental |
| Hermes | não | sim | volume dedicado | orquestração futura |

Ambas as redes são internas e não existem mapeamentos `ports`. O banco, o Redis e o Tika não têm caminho de rede para o Hermes. A API faz a ponte controlada entre `mentor-concursos-agent` e `mentor-concursos-core`.

## Convenções

- Python 3.12, typing e logs JSON em stdout.
- UUIDs para identificadores de domínio.
- PostgreSQL 16, schema `mentor_concursos` e `TIMESTAMPTZ` em UTC.
- `America/Sao_Paulo` somente como timezone de apresentação.
- Português do Brasil na experiência do usuário.
- Recursos limitados a 2,75 CPUs e cerca de 5,25 GiB no total, deixando margem para SO e serviços existentes; limites não são reserva simultânea.

O readiness executa `SELECT 1` autenticado no PostgreSQL e `PING` autenticado no Redis. O worker verifica essas dependências e uma resposta real do Tika. Migrações são aplicadas por processo efêmero, com advisory lock, transação e checksum; o entrypoint do banco não executa SQL da aplicação.

A imagem Redis declara `/data` como volume. O Compose o vincula explicitamente a `mentor_concursos_redis_runtime` para impedir volume anônimo sem identidade, mas desativa AOF e snapshots. Esse volume não é backup nem fonte de verdade e pode conter apenas artefatos runtime.

## Fronteiras futuras

Telegram e Hermes consumirão endpoints autenticados da API via `Authorization: Bearer`. O token vem de arquivo Docker secret e nunca de valor no Compose. Nenhum deles receberá conexão ou credencial direta do PostgreSQL/Redis. O worker não publica interface de rede. Traefik e exposição pública estão fora desta fase. O profile `hermes-disabled` impede a criação do Hermes na operação padrão.
