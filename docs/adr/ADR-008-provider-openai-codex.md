# ADR-008 — Provider OpenAI Codex independente

## Status

Aceito — Fase 2A.

## Decisão

O provider `openai-codex` é autenticado pelo fluxo oficial de OAuth do Hermes
v0.20.4, sem `auth.json` importado, Codex CLI do host, cookies ou sessão de
outro projeto. A credencial fica no volume Hermes e o modelo explícito é
`gpt-5.6-sol`, escolhido entre os modelos oferecidos pelo endpoint autenticado.

Os hosts observados e permitidos são `chatgpt.com` (incluindo o endpoint Codex)
e `auth.openai.com` para OAuth. `api.telegram.org` permanece permitido para o
bot. A allowlist não contém wildcard de internet, IP privado, metadata ou
portas arbitrárias.

## Consequências

Reautenticação requer ação humana e nunca deve ser automatizada ou registrada
em relatório. Mudanças de modelo exigem consultar novamente a lista do Hermes e
um smoke test sem dados acadêmicos.
