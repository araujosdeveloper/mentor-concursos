# Pipeline de conhecimento — Fase 3A

O fluxo é `recebido → quarentena → validado → extraído → normalizado →
chunked → embedded → revisão → indexado`. Apenas versões `indexed` de fontes
aprovadas participam da recuperação. Rejeitadas e superseded ficam fora por
padrão; nenhum histórico é apagado.

Documentos são dados não confiáveis. A entrada aceita apenas PDF com magic
bytes correto e texto UTF-8, até 50 MiB, com chave física aleatória. Path
traversal, links simbólicos, executáveis, HTML ativo, macros e zip bombs são
rejeitados. PDF sem texto exige `ocr_required`; OCR não faz parte desta fase.

Chunks preservam texto original, normalização, ordinal e localização. O
algoritmo `headings-paragraphs-v1` é determinístico e registra suspeita de
prompt injection como metadado, nunca como instrução.

## Embeddings

O contrato candidato é `intfloat/multilingual-e5-small`, dimensão 384, licença
MIT, revisão `fd1525a9fd15316a2d503bf26ab031a61d056e98`; consultas usam
`query:` e documentos `passage:`. O serviço é interno, CPU, offline e sem
porta publicada. A imagem atual expõe um backend determinístico de contrato
para fixtures; os pesos oficiais só entram em build quando o artefato aprovado
estiver disponível localmente, sem download em runtime.

## Recuperação

Busca textual PostgreSQL/GIN e cosine/pgvector são combinadas com ordenação
determinística. Filtros de disciplina/tópico e limite são controlados pelo
schema. Cada consulta grava apenas hash, filtros, IDs, scores, modelo e
request ID em `retrieval_audit`; nunca o texto integral da consulta.
