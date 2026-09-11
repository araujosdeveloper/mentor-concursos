-- Papéis explícitos para ações de revisão de fontes.
ALTER TABLE mentor_concursos.users
  ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'student'
  CHECK (role IN ('student','operator','source_reviewer','admin'));
COMMENT ON COLUMN mentor_concursos.users.role IS 'Papel de autorização; revisão de fontes exige source_reviewer ou admin.';
