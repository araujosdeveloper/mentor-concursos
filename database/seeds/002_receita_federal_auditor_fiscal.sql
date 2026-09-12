-- Edital piloto: Receita Federal — Auditor-Fiscal 2023 (banca FGV).
--
-- Referencial (sem usuário): adiciona a disciplina fiscal ausente da taxonomia
-- e cria o exame. O vínculo por usuário (goal -> syllabus -> subjects/topics)
-- é criado em tempo de execução pelo agente via API.
--
-- Mapeamento do conteúdo programático para a taxonomia (núcleo comum):
--   Língua Portuguesa        -> lingua_portuguesa        (comum)
--   Raciocínio Lógico-Quant. -> raciocinio_logico_matematica (comum)
--   Direito Constitucional   -> direito_constitucional   (comum)
--   Direito Administrativo   -> direito_administrativo   (comum)
--   Direito Tributário       -> direito_tributario       (fiscal)
--   Auditoria                -> auditoria                (fiscal)
--   Contabilidade Geral      -> contabilidade_geral      (fiscal)
--   Comércio Internacional   -> comercio_internacional   (fiscal; NOVO)

INSERT INTO mentor_concursos.subjects (code, name, description)
VALUES
  ('comercio_internacional', 'Comércio Internacional', 'Comércio exterior, regimes aduaneiros e blocos econômicos.')
ON CONFLICT (code) DO UPDATE SET name=EXCLUDED.name, description=EXCLUDED.description, active=TRUE;

INSERT INTO mentor_concursos.subject_tracks(subject_id, track_id)
SELECT s.id, t.id FROM mentor_concursos.subjects s CROSS JOIN mentor_concursos.study_tracks t
WHERE t.code = 'fiscal' AND s.code = 'comercio_internacional'
ON CONFLICT DO NOTHING;

INSERT INTO mentor_concursos.exams (id, organization, role, board, level, status, metadata)
VALUES
  ('6f8b9c1e-4a2d-4b7a-9e3c-8d5f1a2b3c4d', 'Receita Federal do Brasil', 'Auditor-Fiscal da Receita Federal', 'FGV', 'higher', 'completed',
   '{"year": 2023, "vagas": 699, "salario_inicial": 21029.09, "etapas": ["prova objetiva", "prova discursiva"]}')
ON CONFLICT (id) DO NOTHING;
