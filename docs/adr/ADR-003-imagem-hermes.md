# ADR-003: imagem imutável do Hermes

- Status: aceito para documentação; execução adiada
- Data: 2026-09-08

## Contexto

A imagem existente foi observada como `ghcr.io/hostinger/hvps-hermes-agent:latest`, Hermes Agent v0.20.4 de 2026-08-18, com image ID `sha256:7af25fad...`. Tags móveis e config/image IDs isolados não comprovam identidade de manifesto.

## Decisão

`docker image inspect` retornou em `RepoDigests` a referência `ghcr.io/hostinger/hvps-hermes-agent@sha256:7af25fad2af3673f5be39824e38772a9895cb70af83c157917b4cd5e3983e9f9`, para arquitetura amd64. O Compose registra somente essa referência por digest, sem a tag `latest`. A coincidência com o image ID foi registrada, mas não usada como inferência: a evidência é o campo `RepoDigests`.

O serviço fica no profile `hermes-disabled`, não será criado nesta fase e não reutiliza container, volume, rede, memória ou configuração existente.

## Consequências

Uma futura ativação deverá revalidar assinatura/proveniência, compatibilidade do contrato de secrets e versão reportada pelo binário. Esta ADR não autoriza iniciar Hermes nem Telegram.
