# ADR-013 — Embeddings locais

O contrato inicial usa `intfloat/multilingual-e5-small`, dimensão 384, licença
MIT e revisão imutável `fd1525a9fd15316a2d503bf26ab031a61d056e98`, com prefixos
`query:` e `passage:` e vetores normalizados. A variante pequena é adequada ao
limite inicial de CPU/memória, mas a qualidade deve ser medida no conjunto
sintético antes de qualquer fonte real.

O serviço é offline, sem saída externa e sem código remoto em runtime. A
imagem `mentor-concursos-embeddings:0.2.1` incorpora `model.safetensors`,
tokenizer e manifesto SHA-256 do snapshot aprovado; o startup verifica o
manifesto, `trust_remote_code=False`, dimensão 384 e falha fechado. O backend
determinístico não é permitido em produção. A inferência usa diretamente
Transformers/AutoModel com mean-pooling mascarado, sem dependência de
`sentence-transformers`; a auditoria pip-audit do lock real não encontrou
vulnerabilidades conhecidas.
