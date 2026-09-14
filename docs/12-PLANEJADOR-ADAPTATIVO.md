# Planejador de estudos diário e adaptativo

O planejamento ocorre em duas etapas. `POST /api/v1/study/plan/proposals`
calcula e persiste somente um snapshot temporário da simulação. Apenas
`POST /api/v1/study/plan/proposals/{id}/confirm`, após confirmação explícita,
cria ou revisa ciclos e itens. Propostas expiram em 30 minutos.

## Entrada e disponibilidade

A API recebe `goal_id` ou `exam_id`, exatamente um entre `end_date` e
`total_days`, `availability` com os sete dias em inglês, bloco preferido entre
15 e 240 minutos e percentuais inteiros. Zero representa dia indisponível;
outros valores ficam entre 15 e 960 minutos e o total semanal não supera 6.720.
Datas são interpretadas no timezone do perfil e timestamps persistem em UTC.

Os percentuais padrão são conteúdo novo 50%, questões 25%, revisões 20% e
margem de recuperação 5%. Simulados pertencem à parcela de questões e a margem
não cria carga fictícia.

## Algoritmo

O motor puro `study_plan_engine.py` enumera datas do horizonte, remove dias sem
disponibilidade e usa aritmética inteira com maiores restos. O peso efetivo é o
peso do edital multiplicado por prioridade e por fatores limitados de domínio,
progresso, desempenho e atraso. Desempates usam ordinal e UUID estáveis.
O desempenho é agregado por disciplina a partir de tentativas; tempo líquido,
evidências e itens atrasados entram em fatores limitados, impedindo que um único
resultado domine o calendário.

Blocos têm duração preferida configurável e mínimo de 15 minutos. Conteúdo,
questões e revisão compartilham a capacidade total. Revisões ocupam sua parcela
e são distribuídas depois do primeiro contato; D+1, D+7 e D+30 são preferências
limitadas pelo horizonte e pela capacidade. Um resultado ruim altera o fator de
desempenho somente entre 80% e 120%; atrasos acrescentam no máximo 15%.

## Replanejamento

`POST /api/v1/study/plan/replan/proposals` exige objetivo existente e nova
confirmação. Na confirmação, somente itens futuros `planned`, sem sessão ativa
ou pausada, são marcados `cancelled`. Itens concluídos, sessões e progresso são
preservados. Novos ciclos recebem revisão monotônica e vínculo com a proposta.

## Consultas

- `GET /api/v1/study/plan/proposals/current`
- `GET /api/v1/study/plan/today`
- `GET /api/v1/study/plan/week`
- `GET /api/v1/study/plan/status`
- `GET /api/v1/study/next-item`

Todas as rotas mantêm Bearer, identidade Telegram assinada em produção,
isolamento por usuário, auditoria, idempotência das mutações e request ID.

## Telegram

`/plano` inicia uma máquina de estados: concurso quando ausente, prazo, dias,
minutos por dia, duração do bloco, simulação e confirmação. Uma pergunta é
feita por mensagem. `/plano hoje`, `/plano semana`, `/plano status`,
`/plano ajustar` e `/plano cancelar` consultam as operações correspondentes.
Nenhuma mensagem é enviada espontaneamente: durante conversa iniciada pelo
usuário, a oferta contextual tem janela mínima de 24 horas.

## Operação e rollback

A migration `009_adaptive_study_plan.sql` é forward-only e não remove dados.
Antes da aplicação, faça backup lógico do schema acadêmico segundo o runbook.
Rollback funcional consiste em voltar a imagem da aplicação; as tabelas e
colunas novas permanecem inertes. Correções estruturais usam nova migration,
nunca edição da `009` aplicada.
