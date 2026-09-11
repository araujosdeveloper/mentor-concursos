# Fontes oficiais e atualização controlada

A base local é um acervo curado, pequeno e versionado. Cada fonte possui
organização, domínio exato, URL canônica, autoridade, formato e limites de
aquisição. Não há crawler nem espelhamento de portais.

O registro configurável está em `config/official-sources.yaml` e contém apenas
a fonte piloto autorizada. Novas fontes exigem revisão técnica e não são
coletadas automaticamente.

`scripts/refresh-official-source.py` executa aquisição somente por HTTPS,
allowlist exata, no máximo três redirects, timeout total de 30 segundos,
streaming limitado a 20 MiB, validação de MIME/magic bytes e SHA-256. URLs com
credenciais ou endereços privados são rejeitadas.

ETag e Last-Modified são usados em requisições condicionais. Resposta 304 ou
200 com hash igual apenas registra a verificação e descarta o temporário. Hash
novo cria versão em quarentena, preserva a versão indexada anterior e nunca
promove automaticamente. Falhas externas não removem conteúdo aceito.

Atualizações são concorrentes por fonte (limite 1), idempotentes e com retries
limitados. O rollback é feito por IDs exatos em transação forward, sem cascade
genérico. A Lei nº 9.784/1999 permanece a única fonte real do piloto; nenhuma
nova aquisição foi feita nesta fase.
