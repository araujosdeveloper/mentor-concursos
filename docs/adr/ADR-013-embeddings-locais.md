# ADR-013 — Embeddings locais

O contrato inicial usa `intfloat/multilingual-e5-small`, dimensão 384, licença
MIT e revisão imutável `fd1525a9fd15316a2d503bf26ab031a61d056e98`, com prefixos
`query:` e `passage:` e vetores normalizados. A variante pequena é adequada ao
limite inicial de CPU/memória, mas a qualidade deve ser medida no conjunto
sintético antes de qualquer fonte real.

O serviço é offline, sem saída externa e sem código remoto em runtime. A
imagem atual expõe o contrato determinístico de 384 dimensões para validação e
fixtures; a incorporação dos pesos oficiais deve ocorrer em build reprodutível
quando o artefato aprovado estiver disponível localmente.
