# Segurança

## Isolamento

Todos os nomes de redes e volumes são exclusivos e prefixados. O Hermes usa `mentor_concursos_hermes_data` e somente a rede `mentor-concursos-agent`. Credenciais nunca são reutilizadas entre projetos. Os serviços rodam sem modo privilegiado e com `no-new-privileges`; API e worker usam usuário não root.

Nenhuma porta é publicada no host. As redes Compose são internas. Não há Traefik. A futura interface Telegram deverá validar identidade, autorização e replay antes de entrar em produção.

## Segredos e dados

`.env.example` contém somente placeholders. O `.env` real fica fora do Git com permissões mínimas. Logs não podem conter tokens, senhas, conteúdo integral de documentos ou dados pessoais desnecessários. `auth.json`, tokens, bancos locais, uploads, documentos, backups e logs são bloqueados pelo `.gitignore`.

Documentos entram em `storage/inbox` e, após processamento validado, migram para `storage/processed`; apenas `.gitkeep` é versionado. Cada item futuro deve possuir hash, origem, licença/autorização e estado de processamento.

## Ameaças e controles iniciais

- **Prompt injection documental:** conteúdo recuperado é dado não confiável; nunca concede ferramentas ou autoridade.
- **Alucinação:** resposta baseada em fonte, incerteza explícita e rastreabilidade.
- **Supply chain:** imagens com versão explícita; Hermes exige referência imutável aprovada com digest.
- **Movimento lateral:** redes mínimas e ausência de socket Docker/host mounts.
- **Exfiltração:** respostas e logs minimizados; backups criptografados e segregados.

Antes da implantação devem ser adicionados gestão de segredos, autenticação serviço-a-serviço, política de egress, análise de imagens e rotação documentada.
