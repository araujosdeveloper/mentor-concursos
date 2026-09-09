-- Taxonomia oficial do produto. Não contém editais, pesos, tópicos ou dados de usuário.
INSERT INTO mentor_concursos.study_tracks (code, name, description)
VALUES
 ('common', 'Núcleo comum', 'Disciplinas transversais às trilhas do produto.'),
 ('administrative', 'Administrativa', 'Trilha de concursos da área administrativa.'),
 ('fiscal', 'Fiscal', 'Trilha de concursos da área fiscal.'),
 ('courts', 'Tribunais', 'Trilha de concursos de tribunais.')
ON CONFLICT (code) DO UPDATE SET name=EXCLUDED.name, description=EXCLUDED.description, active=TRUE;

INSERT INTO mentor_concursos.subjects (code, name, description)
VALUES
 ('lingua_portuguesa', 'Língua Portuguesa', ''),
 ('direito_constitucional', 'Direito Constitucional', ''),
 ('direito_administrativo', 'Direito Administrativo', ''),
 ('raciocinio_logico_matematica', 'Raciocínio Lógico e Matemática', ''),
 ('informatica_ti', 'Informática/Tecnologia da Informação', ''),
 ('administracao_publica', 'Administração Pública', ''),
 ('administracao_geral', 'Administração Geral', ''),
 ('gestao_de_pessoas', 'Gestão de Pessoas', ''),
 ('arquivologia', 'Arquivologia', ''),
 ('afo', 'Administração Financeira e Orçamentária', ''),
 ('gestao_materiais_contratos', 'Gestão de Materiais e Contratos', ''),
 ('direito_tributario', 'Direito Tributário', ''),
 ('legislacao_tributaria', 'Legislação Tributária', ''),
 ('contabilidade_geral', 'Contabilidade Geral', ''),
 ('contabilidade_avancada', 'Contabilidade Avançada', ''),
 ('auditoria', 'Auditoria', ''),
 ('estatistica', 'Estatística', ''),
 ('economia', 'Economia', ''),
 ('direito_civil', 'Direito Civil', ''),
 ('processo_civil', 'Processo Civil', ''),
 ('direito_penal', 'Direito Penal', ''),
 ('processo_penal', 'Processo Penal', ''),
 ('legislacao_institucional', 'Legislação Institucional', 'Disciplina genérica; não representa conteúdo de órgão específico.')
ON CONFLICT (code) DO UPDATE SET name=EXCLUDED.name, description=EXCLUDED.description, active=TRUE;

INSERT INTO mentor_concursos.subject_tracks(subject_id, track_id)
SELECT s.id, t.id FROM mentor_concursos.subjects s CROSS JOIN mentor_concursos.study_tracks t
WHERE t.code='common' AND s.code IN ('lingua_portuguesa','direito_constitucional','direito_administrativo','raciocinio_logico_matematica','informatica_ti','administracao_publica')
ON CONFLICT DO NOTHING;
INSERT INTO mentor_concursos.subject_tracks(subject_id, track_id)
SELECT s.id, t.id FROM mentor_concursos.subjects s CROSS JOIN mentor_concursos.study_tracks t
WHERE t.code='administrative' AND s.code IN ('administracao_geral','gestao_de_pessoas','arquivologia','afo','gestao_materiais_contratos')
ON CONFLICT DO NOTHING;
INSERT INTO mentor_concursos.subject_tracks(subject_id, track_id)
SELECT s.id, t.id FROM mentor_concursos.subjects s CROSS JOIN mentor_concursos.study_tracks t
WHERE t.code='fiscal' AND s.code IN ('direito_tributario','legislacao_tributaria','contabilidade_geral','contabilidade_avancada','auditoria','estatistica','economia')
ON CONFLICT DO NOTHING;
INSERT INTO mentor_concursos.subject_tracks(subject_id, track_id)
SELECT s.id, t.id FROM mentor_concursos.subjects s CROSS JOIN mentor_concursos.study_tracks t
WHERE t.code='courts' AND s.code IN ('direito_civil','processo_civil','direito_penal','processo_penal','legislacao_institucional')
ON CONFLICT DO NOTHING;
