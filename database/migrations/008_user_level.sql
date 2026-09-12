-- Nível do aluno, usado pelo professor para ajustar ritmo e profundidade.
ALTER TABLE mentor_concursos.users
  ADD COLUMN IF NOT EXISTS level TEXT NOT NULL DEFAULT 'beginner'
  CHECK (level IN ('beginner','intermediate','advanced'));
COMMENT ON COLUMN mentor_concursos.users.level IS 'Nível de conhecimento base do aluno.';
