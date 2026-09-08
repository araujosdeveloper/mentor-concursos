# ADR-001: isolamento do Hermes

- Status: aceito
- Data: 2026-09-08

## Contexto

Há outras cargas em produção na VPS e nenhuma memória, token, identidade ou armazenamento pode ser compartilhado. O Hermes precisa orquestrar o Mentor sem acesso direto à persistência.

## Decisão

Usar uma instância Hermes dedicada, com imagem aprovada e imutável, volume `mentor_concursos_hermes_data` e somente a rede interna `mentor-concursos-agent`. Ela acessa exclusivamente a API em `http://mentor-concursos-api:8080`. Não recebe credenciais nem rota para PostgreSQL, Redis ou Tika.

## Consequências

Há maior custo de memória e operação, compensado por menor risco de vazamento e acoplamento. A autenticação entre Hermes e API e a imagem definitiva são gates anteriores à ativação.
