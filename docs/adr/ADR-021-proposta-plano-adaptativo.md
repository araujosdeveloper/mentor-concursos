# ADR-021 — Proposta confirmável e calendário adaptativo

## Decisão

Evoluir as entidades acadêmicas existentes com uma proposta temporária e
versionada, mantendo o calendário definitivo em `study_cycles` e
`study_plan_items`. O cálculo é um motor puro, inteiro e determinístico. JSONB
guarda somente o snapshot explicável da proposta; objetivos, disciplinas,
tópicos, ciclos e itens continuam relacionais.

## Consequências

A simulação não ativa objetivo nem cria itens. A confirmação concorrente é
serializada pelo lock da proposta e pelas constraints existentes. Replanejar
cancela logicamente somente o futuro não iniciado, preservando histórico e
sessões. A migration é aditiva e o rollback da aplicação não exige apagar dados.
