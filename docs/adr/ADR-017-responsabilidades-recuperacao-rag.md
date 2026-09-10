# ADR-017 — Separação entre recuperação, evidência e resposta

## Status

Aceita para a preparação da fonte piloto; a camada RAG ainda não foi implementada.

## Contexto

Um embedding denso sempre produz vizinhos. Isso também ocorre quando a consulta
está fora do domínio ou não possui suporte no corpus. Portanto, a posição de um
chunk no ranking não prova relevância jurídica, vigência, suficiência ou
resposta.

## Decisão

O retriever retorna somente candidatos para processamento interno. Ele combina
busca lexical, vetorial e RRF, aplica filtros de autorização/estado e devolve
proveniência, localização e scores. Nenhum resultado do retriever é apresentado
diretamente ao usuário como resposta jurídica.

A futura camada RAG será responsável por avaliar a evidência e decidir entre
responder e declarar insuficiência. Para responder, deverá exigir, no mínimo:

1. suporte textual explícito para cada afirmação;
2. proveniência completa e fonte elegível;
3. cobertura suficiente das afirmações da resposta;
4. nível mínimo de evidência definido para o tipo de afirmação;
5. citações correspondentes aos trechos usados.

Quando não houver suporte suficiente, a camada RAG deverá produzir uma resposta
explícita de insuficiência, sem preencher lacunas por similaridade semântica.
Abstention definitiva não é responsabilidade isolada do retriever.

## Consequências

O gate anterior que exigia 100% de abstention no retriever foi tecnicamente mal
posicionado e passa a ser uma obrigação da camada RAG. O resultado histórico da
avaliação permanece preservado: Recall@5 independente 0,9412, MRR 0,7804 e
nDCG@5 0,8466. MRR e nDCG continuam métricas diagnósticas nesta amostra; filtros,
isolamento, proveniência e fidelidade estrutural permanecem gates do retriever.

Esta decisão não aprova, indexa ou publica a fonte piloto e não implementa a
camada RAG.
