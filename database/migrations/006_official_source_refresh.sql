-- Metadados de verificação do atualizador oficial; não altera conteúdo aceito.
ALTER TABLE mentor_concursos.knowledge_sources
  ADD COLUMN IF NOT EXISTS source_page_url TEXT,
  ADD COLUMN IF NOT EXISTS last_checked_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS etag TEXT,
  ADD COLUMN IF NOT EXISTS last_modified TEXT;
ALTER TABLE mentor_concursos.knowledge_source_versions
  ADD COLUMN IF NOT EXISTS artifact_url TEXT,
  ADD COLUMN IF NOT EXISTS quarantine_checked_at TIMESTAMPTZ;
COMMENT ON COLUMN mentor_concursos.knowledge_sources.last_checked_at IS 'Última verificação condicional do artefato oficial.';
