# Operação

## Princípio desta fundação

O Compose inicia somente o núcleo por padrão. O Hermes está atrás do profile explícito `hermes-disabled` e não integra esta fase. Toda implantação segue `docs/runbooks/DEPLOY.md` e registra o inventário anterior para provar que outros projetos permaneceram intactos.

## Migrações

Arquivos em `database/migrations` são numerados, imutáveis e executados em ordem. `scripts/apply-migrations.sh` chama um executor efêmero dedicado. Ele usa advisory lock, checksum SHA-256, transação por arquivo e registro em `schema_migrations`. O entrypoint do PostgreSQL não recebe migrations da aplicação.

Antes de migrar: obter backup lógico consistente, conferir espaço, validar restore em ambiente isolado e registrar versão. Em falha, preservar evidência e restaurar somente segundo runbook aprovado. Nunca editar uma migration aplicada.

## Saúde e observabilidade

`live` verifica o processo; `ready` executa consultas autenticadas no PostgreSQL e Redis sem imprimir credenciais. O healthcheck do worker também consulta Tika. Logs de aplicação são JSON em stdout e todos os containers usam rotação de 10 MiB por arquivo, três arquivos. Métricas leves protegidas incluem tráfego, latência, status, readiness, falhas de autenticação e rate limiting. Tracing e alertas externos permanecem fora desta fase.

## Backup e rollback

- PostgreSQL: dump lógico criptografado, retenção definida e teste periódico de restauração.
- Redis: sem AOF ou snapshots; o volume nomeado runtime apenas substitui o `VOLUME /data` declarado pela imagem e não oferece persistência lógica. Fila e locks são reconstruíveis; PostgreSQL é a fonte definitiva.
- Hermes e documentos: backup separado, criptografado, sem compartilhamento com outras instâncias.
- Aplicação: imagens imutáveis e retorno à versão anterior; banco avança por migrations corretivas.

## Validação e implantação futura

Execute `./scripts/validate-foundation.sh`. Depois, revise o Compose renderizado sem gravar segredos. Confira consumo da VPS, coexistência com serviços intocáveis, nomes exclusivos e ausência de portas publicadas. Backup e restauração seguem o runbook dedicado.

Locks são atualizados somente em ambiente virtual com `scripts/update-locks.sh`, seguidos de auditoria e regressão. Diagnóstico de proxy, métricas e limites segue `runbooks/DIAGNOSTICO.md`.
