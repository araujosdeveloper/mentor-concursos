# Fonte piloto — Lei nº 9.784/1999

Esta ficha registra a política e a proveniência da primeira fonte real preparada
para revisão humana. O documento original e o texto extraído permanecem fora do
Git, no volume dedicado, em `quarantine/` e `extracted/` com permissões restritas.

## Política

- Domínio permitido: `www2.camara.leg.br`.
- Organização: Câmara dos Deputados, Centro de Documentação e Informação.
- Tipo: legislação federal; assunto: processo administrativo federal.
- Disciplina: Direito Administrativo; trilhas relacionadas: administrativa,
  fiscal e tribunais.
- Autoridade: fonte oficial primária; licença registrada como `allowed` para uso
  interno de estudo, sujeita à confirmação jurídica e de direitos na revisão.
- Atualização: revalidar a página oficial antes de cada nova versão; uma nova
  coleta gera versão e hash distintos e supersede a anterior somente após revisão.

## Coleta registrada

- Página de origem: https://www2.camara.leg.br/legin/fed/lei/1999/lei-9784-29-janeiro-1999-322239-norma-pl.html
- Artefato: https://www2.camara.leg.br/legin/fed/lei/1999/lei-9784-29-janeiro-1999-322239-normaatualizada-pl.pdf
- Coleta UTC: 2026-09-10T09:45:39Z.
- Método: HTTPS controlado, sem cookies, autenticação ou rastreamento.
- Redirects: nenhum.
- HTTP: 200; Content-Type `application/pdf`; tamanho 100483 bytes.
- Last-Modified: `Mon, 09 Feb 2026 14:43:14 GMT`.
- ETag: `18883-64a6528aa9a82`.
- SHA-256: `d698c78220576ffa3981b89e001a28f25114f4a9e05fb241e04dcdaadfcd1b65`.
- O portal informa “Texto Atualizado” e “Não consta revogação expressa”; isso
  não é tratado como prova suficiente de vigência jurídica.

## Estado da revisão

A fonte e a versão estão em `pending_review`; o job terminou a etapa técnica em
`reviewing`. Foram gerados 84 chunks e 84 embeddings E5 reais, mas todos os
chunks permanecem `pending_review`, portanto a recuperação normal (`indexed`)
os exclui. A versão não está aprovada, publicada ou disponível ao Telegram.

Extração: Apache Tika 3.2.2. Texto extraído com 34145 caracteres; SHA-256
`c2cf5b1aef775d066539efb59711a8d97625109deaf7c1aaa0defb22a54c8e8f`. O PDF
passou `qpdf --check`, não é criptografado, não possui JavaScript, formulário ou
anexo; a ação de abertura é apenas destino de página.

## Segmentação

A segmentação normativa preserva preâmbulo, artigo, parágrafos, incisos e
localizador `Art. ...`; quando um artigo excede 1400 caracteres, a divisão usa
linhas sem perder o identificador do artigo. Não há resumo, correção silenciosa
ou remoção de negações/exceções. O algoritmo é `normative-article-v1`.

## Avaliação isolada

Foram avaliadas 15 consultas derivadas somente do texto extraído (literais,
paráfrases, artigo, inciso, negação, exceção, prazo e sem resposta). Resultados:

- lexical Recall@5: 0,4667;
- vetorial Recall@5: 0,8000;
- híbrido Recall@5: 0,7333;
- híbrido MRR/nDCG@5: 0,7333/0,7333;
- filtros: 1,00; rejected/superseded: 0; proveniência ausente: 0.

O resultado não atende os gates de recomendação (Recall@5 0,90; MRR 0,80;
nDCG@5 0,85). A consulta sem resposta não foi separada por threshold nesta
primeira avaliação e é um alerta para calibração posterior; não houve promoção
de estado.

## Rollback

Após aprovação explícita, o rollback deve ser uma transação específica que
exclua embeddings, chunks, eventos, job, reviews, versão, fonte e os dois
arquivos usando os IDs/hash desta ficha, verificando contagens antes/depois.
Não usar cascade genérico nem tocar usuário, taxonomia ou outras fontes. O
procedimento foi testado em fixtures na suíte de constraints; não foi executado
destrutivamente sobre este piloto.
