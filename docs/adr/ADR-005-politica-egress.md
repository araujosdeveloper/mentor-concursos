# ADR-005 — Egress exclusivamente por proxy dedicado

- Status: aceito
- Data: 2026-09-08

## Decisão

O Hermes dedicado, quando ativado, terá redes internas `agent` e `egress-internal`, sem a rede
com uplink. Toda saída HTTP/HTTPS será encaminhada pelo `mentor-concursos-egress-proxy`, único
participante simultâneo de `egress-internal` e `egress-uplink`. O proxy usa allowlist de
domínios, bloqueia endereços especiais/privados, restringe CONNECT à porta 443 e não publica
porta no host. API, worker, PostgreSQL, Redis e Tika permanecem fora das redes de egress.

## Imagem

Em 2026-09-08, `docker buildx imagetools inspect ubuntu/squid:6.6-24.04_edge` resolveu o
manifest amd64 `sha256:94f844158e12b52f51b4ae996515e37e8fb3e8d85e1c86caba1a297376e4ec4f`.
O Compose fixa tag e manifest digest; o digest não é um image ID/config digest.

## Consequências

Há um ponto controlável e auditável para egress, com custo de disponibilidade: falha do proxy
interrompe acesso externo. Allowlist por domínio depende de DNS; por isso ACL de destino nega
faixas privadas após resolução. O provider OpenAI deve ser revalidado antes da ativação do
Hermes, pois não foi encontrada lista oficial exaustiva e estável de hosts nesta fase.
