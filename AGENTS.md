# Instruções para agentes

Estas regras se aplicam a todo o repositório.

- Trabalhe apenas neste projeto e preserve alterações preexistentes.
- Nunca leia, copie ou reutilize segredos, memórias, identidades, bancos ou volumes de outros projetos.
- Não versione `.env`, tokens, `auth.json`, documentos de estudo, uploads, logs ou backups.
- Não publique portas no host. A API é estritamente interna.
- Não execute operações em containers ou serviços existentes sem autorização explícita.
- Mantenha timestamps persistidos em UTC; converta para `America/Sao_Paulo` apenas na apresentação.
- Use UUIDs, português do Brasil e o schema PostgreSQL `mentor_concursos`.
- Não crie conteúdo acadêmico como se fosse fonte real. Diferencie questões reais de autorais e registre a fonte.
- Toda mudança deve passar por `./scripts/validate-foundation.sh` quando aplicável.
- Decisões arquiteturais relevantes devem ser registradas em `docs/adr/`.
