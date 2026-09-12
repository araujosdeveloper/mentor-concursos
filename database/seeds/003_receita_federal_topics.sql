-- Tópicos do edital piloto (Receita Federal — Auditor-Fiscal), mapeados às
-- disciplinas (subjects) da taxonomia comum. Estrutura plana nesta fase.

INSERT INTO mentor_concursos.topics (subject_id, code, name, ordinal)
SELECT s.id, t.code, t.name, t.ordinal
FROM (VALUES
  ('lingua_portuguesa', 'compreensao_interpretacao', 'Compreensão e interpretação de textos', 1),
  ('lingua_portuguesa', 'tipologia_generos', 'Tipologia e gêneros textuais', 2),
  ('lingua_portuguesa', 'coesao_coerencia', 'Coesão e coerência', 3),
  ('lingua_portuguesa', 'norma_culta', 'Norma culta: ortografia e acentuação', 4),
  ('lingua_portuguesa', 'sintaxe_regencia', 'Sintaxe e regência', 5),
  ('lingua_portuguesa', 'concordancia', 'Concordância nominal e verbal', 6),
  ('lingua_portuguesa', 'pontuacao', 'Pontuação', 7),
  ('lingua_portuguesa', 'reescrita_equivalencia', 'Reescrita e equivalência de períodos', 8),

  ('raciocinio_logico_matematica', 'logica_proposicional', 'Lógica proposicional', 1),
  ('raciocinio_logico_matematica', 'argumentacao_silogismos', 'Argumentação e silogismos', 2),
  ('raciocinio_logico_matematica', 'analise_combinatoria', 'Análise combinatória', 3),
  ('raciocinio_logico_matematica', 'probabilidade', 'Probabilidade', 4),
  ('raciocinio_logico_matematica', 'estatistica_descritiva', 'Estatística descritiva', 5),
  ('raciocinio_logico_matematica', 'matematica_financeira', 'Matemática financeira', 6),
  ('raciocinio_logico_matematica', 'geometria_basica', 'Geometria básica', 7),

  ('direito_constitucional', 'principios_fundamentais', 'Princípios fundamentais', 1),
  ('direito_constitucional', 'direitos_garantias', 'Direitos e garantias individuais e coletivos', 2),
  ('direito_constitucional', 'direitos_sociais_nacionalidade', 'Direitos sociais e nacionalidade', 3),
  ('direito_constitucional', 'organizacao_estado', 'Organização político-administrativa do Estado', 4),
  ('direito_constitucional', 'adm_publica_cf', 'Administração Pública: princípios e servidores', 5),
  ('direito_constitucional', 'poderes', 'Poder Legislativo, Executivo e Judiciário', 6),
  ('direito_constitucional', 'funcoes_essenciais', 'Funções essenciais à Justiça', 7),
  ('direito_constitucional', 'stn_cf', 'Sistema Tributário Nacional na CF/88', 8),
  ('direito_constitucional', 'ordem_economica', 'Ordem econômica e financeira', 9),
  ('direito_constitucional', 'controle_constitucionalidade', 'Controle de constitucionalidade', 10),

  ('direito_administrativo', 'principios_adm', 'Princípios da Administração Pública', 1),
  ('direito_administrativo', 'atos_administrativos', 'Atos administrativos', 2),
  ('direito_administrativo', 'licitacoes_14133', 'Licitações e contratos (Lei 14.133/21)', 3),
  ('direito_administrativo', 'servidores_8112', 'Servidores públicos e Lei 8.112/90', 4),
  ('direito_administrativo', 'processo_adm_9784', 'Processo administrativo (Lei 9.784/99)', 5),
  ('direito_administrativo', 'improbidade', 'Improbidade administrativa', 6),
  ('direito_administrativo', 'responsabilidade_civil', 'Responsabilidade civil do Estado', 7),
  ('direito_administrativo', 'controle_adm', 'Controle da Administração', 8),

  ('direito_tributario', 'stn', 'Sistema Tributário Nacional', 1),
  ('direito_tributario', 'competencia_tributaria', 'Competência tributária', 2),
  ('direito_tributario', 'principios_tributarios', 'Princípios constitucionais tributários', 3),
  ('direito_tributario', 'limitacoes_imunidades', 'Limitações ao poder de tributar e imunidades', 4),
  ('direito_tributario', 'tributos_especies', 'Tributos: classificação e espécies', 5),
  ('direito_tributario', 'obrigacao_tributaria', 'Obrigação tributária', 6),
  ('direito_tributario', 'credito_tributario', 'Crédito tributário: lançamento e modalidades', 7),
  ('direito_tributario', 'suspensao_extincao', 'Suspensão, extinção e exclusão do crédito', 8),
  ('direito_tributario', 'adm_tributaria', 'Administração tributária e fiscalização', 9),
  ('direito_tributario', 'tributos_federais', 'Tributos federais: IR, IPI, II, IE, ITR, IOF', 10),
  ('direito_tributario', 'contribuicoes_sociais', 'Contribuições sociais: PIS/COFINS, CSLL', 11),
  ('direito_tributario', 'processo_adm_fiscal', 'Processo administrativo fiscal', 12),

  ('auditoria', 'conceitos_auditoria', 'Conceitos e princípios de auditoria', 1),
  ('auditoria', 'normas_auditoria', 'Normas brasileiras e internacionais de auditoria', 2),
  ('auditoria', 'planejamento_auditoria', 'Planejamento e procedimentos de auditoria', 3),
  ('auditoria', 'risco_materialidade', 'Risco de auditoria e materialidade', 4),
  ('auditoria', 'papeis_trabalho', 'Papéis de trabalho', 5),
  ('auditoria', 'parecer_auditoria', 'Parecer de auditoria', 6),

  ('contabilidade_geral', 'principios_normas', 'Princípios e normas contábeis', 1),
  ('contabilidade_geral', 'patrimonio_demonstracoes', 'Patrimônio e demonstrações contábeis', 2),
  ('contabilidade_geral', 'balanco_patrimonial', 'Balanço Patrimonial', 3),
  ('contabilidade_geral', 'dre', 'Demonstração do Resultado do Exercício (DRE)', 4),
  ('contabilidade_geral', 'dfc_dmpl_dva', 'DFC, DMPL e DVA', 5),
  ('contabilidade_geral', 'operacoes_mercadorias', 'Operações com mercadorias', 6),
  ('contabilidade_geral', 'avaliacao_ativos', 'Avaliação de ativos: estoques, investimentos, imobilizado', 7),
  ('contabilidade_geral', 'provisoes_contingencias', 'Provisões e contingências', 8),
  ('contabilidade_geral', 'tributos_lucro', 'Tributos sobre o lucro e diferidos', 9),

  ('comercio_internacional', 'conceitos_comex', 'Conceitos básicos do comércio exterior', 1),
  ('comercio_internacional', 'importacao_exportacao', 'Operações de importação e exportação', 2),
  ('comercio_internacional', 'regimes_aduaneiros', 'Regimes aduaneiros', 3),
  ('comercio_internacional', 'mercosul_blocos', 'Mercosul e blocos econômicos', 4)
) AS t(subject_code, code, name, ordinal)
JOIN mentor_concursos.subjects s ON s.code = t.subject_code
ON CONFLICT (subject_id, code) DO UPDATE SET name=EXCLUDED.name, ordinal=EXCLUDED.ordinal, active=TRUE;
