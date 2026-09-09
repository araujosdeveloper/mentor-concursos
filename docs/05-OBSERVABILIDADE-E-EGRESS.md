# Observabilidade mínima e egress controlado

## Topologia de redes

| Rede | `internal` | Participantes | Finalidade |
| --- | --- | --- | --- |
| `mentor-concursos-core` | sim | API, worker, PostgreSQL, Redis, Tika | dados e dependências internas |
| `mentor-concursos-agent` | sim | API e Hermes futuro | Hermes → API |
| `mentor-concursos-egress-internal` | sim | proxy e Hermes futuro | entrada obrigatória do proxy |
| `mentor-concursos-egress-uplink` | não | somente proxy | saída externa controlada |

Uma rede Docker marcada `internal` não fornece saída externa. O Hermes futuro terá somente
`agent` e `egress-internal`; sua configuração `HTTP_PROXY`/`HTTPS_PROXY` apontará para o Squid.
Somente o proxy participa da rede `egress-uplink`. API, worker, banco, Redis e Tika não possuem
rota de egress nesta fase.

## Política de egress

O Squid permite apenas HTTP na porta 80 e `CONNECT` na 443 para domínios presentes em
`infra/egress/allowlist-domains.txt`. Faixas privadas, loopback, link-local, documentação,
multicast e metadata são negadas antes da allowlist. URLs completas não são gravadas no log;
somente método, domínio de destino, código e cliente.

A lista inicial contém `api.telegram.org`, `.chatgpt.com` e `auth.openai.com`. Tavily não faz
parte da configuração atual. A consulta à documentação oficial disponível em 2026-09-08 não
produziu uma lista exaustiva e estável dos destinos do provider `openai-codex`; portanto esta
lista é deliberadamente mínima e deve ser revalidada com tráfego sem segredos antes de ativar
o Hermes. Adições exigem justificativa, revisão contra DNS rebinding e teste positivo/negativo.

## Logs e correlação

Todos os containers usam `json-file`, `max-size=10m` e `max-file=3`. API, worker e migrations
emitem JSON. A API aceita apenas `X-Request-ID` alfanumérico com `_`/`-`, até 64 caracteres;
caso contrário gera UUID. O ID aparece na resposta e nos eventos HTTP. Erros inesperados
retornam mensagem uniforme, sem stack trace para o cliente. Segredos, cabeçalhos Authorization,
query strings e corpos não devem ser registrados.

## Métricas

`GET /api/internal/metrics` usa o mesmo Bearer token de serviço e expõe texto Prometheus:
requisições por método/rota-modelo/status, soma de latência, falhas de autenticação, rejeições
por limite e estado de readiness. Não há labels com token, usuário, request ID ou URL livre.
O endpoint não é publicado no host.

## Rate limiting

Rotas internas protegidas usam contador de janela fixa atômico no Redis, separado por rota.
`RATE_LIMIT_REQUESTS` e `RATE_LIMIT_WINDOW_SECONDS` configuram a política. Excesso retorna 429
uniforme e `Retry-After`; indisponibilidade do Redis resulta em 503 (fail-closed) porque são
rotas de controle autenticadas. Healthchecks não usam limite nem autenticação.

## Limites iniciais

API 384 MiB/0,25 CPU; worker 512 MiB/0,35; PostgreSQL 768 MiB/0,40; Redis 128 MiB/0,10;
Tika 768 MiB/0,35; proxy 128 MiB/0,10; Hermes futuro 768 MiB/0,35. Os seis serviços ativos
somam no máximo 1,55 CPU e 2,688 GiB; com Hermes, 1,90 CPU e 3,456 GiB. São tetos, não reservas.

## Dependências reproduzíveis

`requirements.lock` e `requirements-dev.lock` fixam transitivas e hashes. O build instala o
lock de runtime com `--require-hashes --no-deps`. Para atualizar, crie ambiente virtual local,
instale exatamente `pip==25.1.1` e `pip-tools==7.5.0`, execute `scripts/update-locks.sh`, revise
o diff, rode `pip-audit --disable-pip -r requirements.lock` e toda a regressão. O CI executa
`scripts/verify-lock.sh`; divergência do `pyproject.toml` falha o pipeline. Atualizações nunca
são automáticas.

Na auditoria de 2026-09-09, o lock inicial revelou seis advisories em Starlette 0.47.3. FastAPI
foi atualizado explicitamente para 0.141.1, Starlette passou a 1.6.0 e os testes foram repetidos.
A nova execução do pip-audit retornou `No known vulnerabilities found`.

## Rollback

Pare somente serviços Mentor afetados, restaure os arquivos versionados do checkpoint
`/opt/backups/mentor-concursos/fase-1-2-51281aa2b14fca7fb5d4067c27ca8bc5678f32b9-prechange`,
valide checksums e Compose, reconstrua API/worker e recrie apenas os containers do projeto.
O checkpoint não contém `.env` nem `secrets/`. Não remova volumes.
