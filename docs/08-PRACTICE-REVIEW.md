# Questões e revisão espaçada

O núcleo de prática cria questões somente a partir de chunks com estado
`indexed`. Cada questão guarda a fonte, versão, locator e hash do chunk usado;
questões sem evidência indexed não são criadas.

As respostas são registradas com chave de idempotência por usuário. O caderno
de erros mantém histórico e não apaga tentativas anteriores. O agendamento é
determinístico: erro em 1 dia; primeiro acerto em 3 dias; segundo em 7 dias;
terceiro em 15 dias; acertos seguintes em 30 dias. Timestamps permanecem em
UTC e a apresentação ao usuário usa o fuso configurado.

Os comandos do Telegram são apenas uma camada de transporte para a API:
`/questao`, `/responder`, `/simulado`, `/revisar`, `/erros`, `/desempenho` e
`/cancelar`. Hermes não acessa o banco. Fixtures de testes não são executadas
nem persistidas para o usuário real.
