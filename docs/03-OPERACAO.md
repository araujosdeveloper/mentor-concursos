# Operação

## Princípio desta fundação

Os arquivos Compose são especificação futura. A validação usa exclusivamente `docker compose config`; não cria containers, redes ou volumes. O primeiro start exige revisão humana, preenchimento seguro de `.env`, imagem Hermes aprovada e janela de mudança.

## Migrações

Arquivos em `database/migrations` são numerados, imutáveis e executados em ordem. A migração inicial é idempotente onde tecnicamente apropriado, roda em transação, habilita `vector` e `pgcrypto`, cria o schema e registra a própria versão. Em banco novo, o entrypoint do PostgreSQL executa os scripts. Em banco existente, um executor dedicado de migrations deverá controlar lock, checksum e registro; não se deve depender novamente do entrypoint.

Antes de migrar: obter backup lógico consistente, conferir espaço, validar restore em ambiente isolado e registrar versão. Em falha, preservar evidência e restaurar somente segundo runbook aprovado. Nunca editar uma migration aplicada.

## Saúde e observabilidade

`live` verifica o processo; `ready` testa alcance TCP de PostgreSQL e Redis sem imprimir credenciais. Logs são JSON em stdout. Métricas, tracing e alertas são gates antes de uso real.

## Backup e rollback

- PostgreSQL: dump lógico criptografado, retenção definida e teste periódico de restauração.
- Redis: AOF no volume exclusivo; não é fonte definitiva de dados acadêmicos.
- Hermes e documentos: backup separado, criptografado, sem compartilhamento com outras instâncias.
- Aplicação: imagens imutáveis e retorno à versão anterior; banco avança por migrations corretivas.

## Validação e implantação futura

Execute `./scripts/validate-foundation.sh`. Depois, revise o Compose renderizado sem gravar segredos. A implantação futura deve conferir consumo da VPS, coexistência com serviços intocáveis, nomes exclusivos e ausência de portas publicadas. Comandos que iniciam ou alteram containers estão deliberadamente fora desta fase.
