# ADR-011 — Cálculo de tempo líquido

O servidor calcula `net_duration_seconds` como tempo entre início e encerramento
menos pausas fechadas (e a pausa aberta, quando a sessão é concluída). O cliente
envia apenas timestamps opcionais sujeitos a validação temporal; nunca envia
duração confiável. Timestamps persistem em UTC e respostas usam ISO-8601 UTC.
