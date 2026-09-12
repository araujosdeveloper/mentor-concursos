# ADR-020 — Consulta externa ao vivo a fontes oficiais, sem ingestão

## Status

Aceita.

## Contexto

A abordagem anterior previa ingerir, vetorizar e indexar fontes oficiais para
responder a partir de um corpus local curado. O requisito foi revisto: a
consulta deve ser **inteiramente externa e ao vivo**, para leis e jurisprudência
de todos os segmentos do direito. Nada é ingerido, indexado ou promovido
localmente; a evidência é obtida no momento da pergunta a partir de sites
oficiais.

## Decisão

1. **Sem ingestão.** O pipeline de coleta → chunk → embedding → revisão →
   indexação deixa de ser o caminho de resposta. A resposta é produzida a partir
   de conteúdo oficial obtido ao vivo.

2. **Consulta direcionada, não crawler.** Cada pergunta gera uma busca pontual
   no endpoint oficial correspondente (legislação ou jurisprudência), com
   paginação limitada e sem percorrer links recursivamente.

3. **Dois conectores de consulta.**
   - **Legislação/Constituição**: busca no portal oficial (Planalto/Câmara) pelo
     identificador normativo (lei, artigo) e leitura do texto vigente.
   - **Jurisprudência**: busca via agregador `jurisprudencias.ai` (stf, stj, tst,
     trf, tj...), devolvendo órgão, número do processo, data, ementa/trecho e o
     link do documento original no portal do tribunal. O agregador é usado apenas
     para a busca, pois os portais oficiais de STF/STJ bloqueiam acesso
     programático (proteção anti-bot); a citação continua apontando para a fonte
     oficial.

4. **Egress restrito.** Um serviço dedicado de consulta externa alcança a
   internet somente pela `egress-internal` + Squid, com allowlist limitada aos
   domínios oficiais aprovados. Permanecem o bloqueio de faixas privadas, o
   `CONNECT` restrito à porta 443 e a ausência de porta publicada.

5. **Grounding e citação ao vivo.** O conteúdo externo é evidência candidata,
   nunca autoridade automática. Toda resposta cita a origem exata (URL, norma ou
   número do processo, data). Ausência de fonte ou falha de consulta resulta em
   `insufficient_evidence`/`retrieval_failed`, sem completar por plausibilidade.
   "Não consta revogação expressa" não é prova de vigência.

6. **Catálogo como rota, não como armazenamento.** `config/official-sources.yaml`
   descreve os conectores oficiais disponíveis (host, tipo de consulta, limites),
   sem armazenar conteúdo.

7. **Aposentar o RAG local.** O corpus indexado (Lei nº 9.784/1999) deixa de ser
   o caminho de resposta; toda resposta passa a ser consulta externa ao vivo. O
   schema de conhecimento existente permanece adormecido (sem remoção destrutiva).

8. **Cache transitório curto.** Para reduzir latência e carga sobre os portais,
   o conteúdo bruto buscado (texto extraído e metadados) pode ser armazenado em
   cache efêmero de curta duração (Redis, sem persistência), apenas por
   performance. Não há revisão, indexação ou promoção; o cache expira sozinho e
   nunca é fonte de autoridade.

## Consequências

- Latência de resposta maior (busca + leitura externa em cada pergunta), sujeita
  a rate limits e a mudanças de HTML/estrutura dos portais oficiais.
- Fidelidade de citação depende de extração determinística no momento da
  consulta, o que exige testes de regressão por conector.
- O RAG local é desativado como caminho de resposta; o endpoint passa a orquestrar
  consulta externa + grounding, reutilizando a mesma forma de resposta
  (`answered` / `insufficient_evidence` / `retrieval_failed`).
- A API/worker passam a depender de um caminho de egress que hoje não possuem.

## Fora de escopo

Crawler, espelhamento, promoção automática e qualquer armazenamento local de
conteúdo obtido externamente.

## Busca web genérica (fallback)

Além dos conectores de legislação e jurisprudência, um conector de busca na web
(Tavily) é usado como **fallback**: somente quando os conectores primários não
retornam evidência, a pergunta é enviada à busca geral (ex.: "qual o último
edital do INSS?"). Cada resultado é tratado como evidência candidata com URL
citável, nunca como autoridade. O token do provedor é um secret separado
(`tavily_api_key`) e a ausência dele desativa apenas o fallback.
