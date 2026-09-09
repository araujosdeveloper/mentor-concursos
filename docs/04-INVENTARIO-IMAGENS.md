# Inventário de imagens imutáveis

Verificação realizada em 2026-09-08 para `linux/amd64` com:

```bash
docker buildx imagetools inspect <imagem:versão>
docker image inspect ghcr.io/hostinger/hvps-hermes-agent:latest \
  --format 'RepoDigests={{json .RepoDigests}} ImageID={{.Id}} Architecture={{.Architecture}}'
```

| Componente | Versão/tag consultada | Manifest digest amd64 fixado |
| --- | --- | --- |
| Python | 3.12.10-slim-bookworm | `sha256:97983fa8cc88343512862c62307159a82261c3528dc025f79e5a3f7af43e50b4` |
| PostgreSQL/pgvector | 0.8.0-pg16 | `sha256:c72df104202409108a1660ecccd2b7ffac6b17e44c31b2636d10e983f410f8eb` |
| Redis | 7.4.2-alpine3.21 | `sha256:519f0189dfdee3bc0bad61fb265fe73d864b5c64020e6579ad48a45c49965635` |
| Apache Tika | 3.2.2.0-full | `sha256:00604ce6ca877b4c533c1a2c13fd7cd98f031a1eb5b86f05904e85b480f48de8` |
| Hermes Agent | v0.20.4 observada; tag de origem `latest` | `sha256:7af25fad2af3673f5be39824e38772a9895cb70af83c157917b4cd5e3983e9f9` |
| Squid | 6.6-24.04_edge | `sha256:94f844158e12b52f51b4ae996515e37e8fb3e8d85e1c86caba1a297376e4ec4f` |

Os digests de runtime, inclusive Squid, foram obtidos do manifesto específico `linux/amd64`, não do image index multi-arquitetura. Para o Hermes, o daemon retornou esse valor em `RepoDigests` e também como image ID. A igualdade numérica não transforma um config digest em manifest digest; o uso só foi aceito porque a referência apareceu explicitamente em `RepoDigests`. O serviço permanece desativado.
