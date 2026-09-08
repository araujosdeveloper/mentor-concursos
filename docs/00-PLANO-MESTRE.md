# Plano mestre

## Propósito e escopo

O Mentor Concursos é um agente pessoal de preparação para Roberto Araujo. O produto organiza estudo, revisão e evidências de aprendizagem sem substituir fontes oficiais. Direito Administrativo é a matéria piloto usada para validar o fluxo antes da expansão.

## Organização pedagógica

O núcleo comum reúne competências compartilhadas entre concursos, sem duplicar conteúdo. Sobre ele se apoiam três trilhas: administrativa, fiscal e tribunais. O sistema deverá aceitar múltiplos editais simultaneamente, mas somente um objetivo principal pode estar ativo em cada ciclo de planejamento; os demais ficam explicitamente em espera ou manutenção.

Questões reais e questões autorais serão armazenadas com classificação inequívoca. Questões reais exigem banca, certame, ano e referência verificável; conteúdo autoral deve ser rotulado como tal e nunca atribuído a uma banca. Toda afirmação acadêmica relevante deve apontar para fonte primária ou secundária confiável, sua versão/data e trecho de sustentação quando permitido.

## Fases, gates e aceite

1. **Fundação técnica.** Estrutura, isolamento, API de saúde, worker, autenticação interna, migração controlada e validação real do núcleo. Gate: cinco serviços do núcleo verificados, migração e vector validados, backup/restauração ensaiados, testes verdes, Hermes desativado e nenhuma porta ou segredo publicado.
2. **Ingestão piloto.** Pipeline rastreável de documentos de Direito Administrativo, extração via Tika, hash e metadados de proveniência. Gate: corpus pequeno recuperável, deduplicado e auditável, com teste de falhas.
3. **Aprendizagem piloto.** Planejamento, sessões, revisões espaçadas e caderno de erros. Gate: fluxos testados com dados reais autorizados, métricas compreensíveis e nenhum conteúdo sem fonte.
4. **Interface Telegram e Hermes.** Integração pelo contrato da API, identidade e armazenamento exclusivos. Gate: autorização, rate limiting, auditoria, isolamento de rede e ensaio de rollback.
5. **Expansão.** Núcleo comum e trilhas administrativa, fiscal e tribunais, incluindo múltiplos editais. Gate: cobertura definida, regressão do piloto e capacidade dentro dos limites da VPS.

## Prevenção de alucinação

- Recuperar evidência antes de responder e exibir a origem.
- Declarar incerteza ou ausência de fonte; não completar lacunas por plausibilidade.
- Preservar data, jurisdição e vigência normativa.
- Separar texto extraído, síntese do modelo e contribuição humana.
- Submeter amostras a revisão humana e manter testes de respostas sem evidência.

## Revisões e caderno de erros

O sistema futuro registrará tentativas, confiança, erro, causa provável, fonte correta e agenda de revisão. O caderno de erros será derivado desses eventos, sem apagar histórico. O algoritmo de revisão será introduzido por ADR e validado com métricas; não há regra acadêmica fictícia nesta fundação.

## Backup e rollback

Backups serão exclusivos do projeto, criptografados, com retenção e restauração testada. Cada release terá dump lógico antes de migração, versão imutável das imagens e procedimento de rollback. Migrações aplicadas não serão editadas: correções entram em nova versão. O rollback de aplicação não pressupõe rollback destrutivo de banco.
