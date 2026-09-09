# ADR-014 — Armazenamento e quarentena

Documentos ficam no volume exclusivo `mentor_concursos_documents`, separados
em `quarantine`, `accepted`, `extracted` e `rejected`. Chaves físicas são
aleatórias, o SHA-256 é registrado e apenas PDF/texto UTF-8 são aceitos. Não
há documentos reais nesta fase. Tamanho máximo inicial: 50 MiB; OCR e ClamAV
ficam fora do escopo, com risco residual documentado.
