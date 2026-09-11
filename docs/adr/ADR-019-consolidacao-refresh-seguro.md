# ADR-019 — Consolidação de atualização oficial e processamento controlado

## Decisão

O atualizador oficial valida cada redirect antes da conexão seguinte, limita a
três saltos e 30 segundos, rejeita destinos privados e grava artefatos por
SHA em quarentena. A decisão persistente usa lock transacional por fonte:
304 e SHA repetido apenas atualizam a verificação; SHA novo cria versão
inelegível e referencia a anterior.

O worker possui consumidor de um job por vez, com lease e modo `--once` para
operação controlada. O consumo contínuo permanece opt-in (`WORKER_CONSUME_ENABLED=true`)
até que um handler de processamento específico esteja habilitado e observado.

## Consequências

Não há crawler, promoção automática ou remoção de conteúdo aceito. A migration
006 registra metadados de verificação e a migration 007 define papéis de
revisão (`source_reviewer`/`admin`). A aplicação em produção deve seguir o
runbook de migrations e backup antes de ativar novos papéis.

## Consolidação pré-PR

Enquanto o modelo institucional não for decidido, a autorização permanece
baseada em propriedade: `source_reviewer` revisa apenas fontes do próprio
`owner_user_id`; `admin` pode revisar qualquer fonte; `student` e `operator`
não revisam. A promoção de papel é administrativa, por UUID explícito e com
auditoria.

A revisão promove ou rejeita fonte, versão e chunks numa única transação.
Aprovação exige chunks integralmente pendentes, embeddings E5 na revisão
aprovada, dimensão 384 e ausência de suspeita de prompt injection. O limiar
`min_score` incide somente sobre `vector_score`; zero preserva o ranking RRF.

Sem handlers registrados, o worker não consulta nem reclama jobs e `--once`
termina com sucesso. O consumo contínuo segue desabilitado por padrão.
