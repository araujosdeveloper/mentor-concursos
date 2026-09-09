# Runbook de backup e restauração

1. Crie `/opt/backups/mentor-concursos` com modo 700.
2. Execute `pg_dump` de dentro do container principal, formato custom, redirecionando para arquivo modo 600 sem senha na linha de comando.
3. Calcule `sha256sum` e armazene o checksum ao lado do dump.
4. Crie uma database temporária com nome explícito e owner dedicado no mesmo PostgreSQL.
5. Restaure com `pg_restore --no-owner --no-privileges` na database temporária.
6. Valide extensão `vector`, schema `mentor_concursos`, tabela `schema_migrations` e checksums registrados.
7. Termine conexões da database temporária e remova somente essa database.
8. Confirme que a database principal e seu volume permanecem intactos.

O dump e o checksum ficam fora do Git e não contêm o arquivo de secrets. O nome do backup, resultado da restauração e SHA-256 podem ser registrados no relatório; credenciais e conteúdo sensível não.

## Backup do volume Hermes

O backup do volume `mentor_concursos_hermes_data` contém OAuth, estado de sessão e
autorizações Telegram; portanto é material sensível. O modo 600 protege o arquivo
somente no host e não substitui criptografia. Cópias externas exigem criptografia
autenticada, com a chave gerenciada separadamente (nunca junto do backup). O arquivo
não pode ser enviado ao Git, chat, armazenamento público ou anexo. Uma restauração
após suspeita de exposição exige rotação das credenciais OAuth, do token Telegram e
dos demais segredos antes de reativar o gateway. O procedimento de backup deve
registrar apenas caminho, permissões e checksum, nunca o conteúdo.
