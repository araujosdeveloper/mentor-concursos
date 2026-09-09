-- Pipeline de conhecimento. Apenas metadados e estruturas; nenhuma fonte é
-- criada por esta migration. Executada atomicamente pelo executor versionado.
CREATE TABLE IF NOT EXISTS mentor_concursos.knowledge_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id UUID NOT NULL REFERENCES mentor_concursos.users(id) ON DELETE RESTRICT,
    source_type TEXT NOT NULL CHECK (source_type IN ('law', 'notice', 'manual', 'exam', 'synthetic')),
    title TEXT NOT NULL CHECK (btrim(title) <> '' AND length(title) <= 500),
    issuer TEXT CHECK (issuer IS NULL OR length(issuer) <= 300),
    authority TEXT CHECK (authority IS NULL OR length(authority) <= 300),
    canonical_url TEXT CHECK (canonical_url IS NULL OR canonical_url ~ '^https?://'),
    license_status TEXT NOT NULL CHECK (license_status IN ('unknown', 'allowed', 'restricted', 'denied')),
    trust_level TEXT NOT NULL CHECK (trust_level IN ('untrusted', 'review', 'trusted')),
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','pending_review','approved','rejected','superseded','archived')),
    subject_id UUID REFERENCES mentor_concursos.subjects(id) ON DELETE RESTRICT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS mentor_concursos.knowledge_source_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID NOT NULL REFERENCES mentor_concursos.knowledge_sources(id) ON DELETE RESTRICT,
    version_label TEXT NOT NULL CHECK (btrim(version_label) <> '' AND length(version_label) <= 120),
    published_at DATE,
    effective_from DATE,
    effective_until DATE,
    supersedes_version_id UUID REFERENCES mentor_concursos.knowledge_source_versions(id) ON DELETE RESTRICT,
    sha256 TEXT NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    mime_type TEXT NOT NULL CHECK (mime_type IN ('application/pdf','text/plain','text/markdown')),
    byte_size BIGINT NOT NULL CHECK (byte_size > 0 AND byte_size <= 52428800),
    page_count INTEGER CHECK (page_count IS NULL OR page_count >= 0),
    storage_key TEXT NOT NULL UNIQUE CHECK (storage_key !~ E'(^|/)\\.\\.?(/|$)' AND storage_key !~ E'(^|/)\\\\'),
    status TEXT NOT NULL DEFAULT 'received' CHECK (status IN ('received','quarantined','validated','extracted','normalized','chunked','embedded','pending_review','indexed','rejected','superseded')),
    extraction_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_id, version_label),
    UNIQUE(source_id, sha256),
    CHECK (effective_until IS NULL OR effective_from IS NULL OR effective_until >= effective_from)
);

CREATE TABLE IF NOT EXISTS mentor_concursos.ingestion_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_version_id UUID NOT NULL REFERENCES mentor_concursos.knowledge_source_versions(id) ON DELETE RESTRICT,
    requested_by UUID NOT NULL REFERENCES mentor_concursos.users(id) ON DELETE RESTRICT,
    idempotency_key TEXT NOT NULL CHECK (length(idempotency_key) BETWEEN 8 AND 128),
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','validating','extracting','normalizing','chunking','embedding','reviewing','completed','failed','cancelled')),
    stage TEXT NOT NULL DEFAULT 'queued',
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0 AND attempts <= 5),
    error_code TEXT CHECK (error_code IS NULL OR error_code ~ '^[a-z0-9_.-]+$'),
    lease_owner TEXT,
    lease_expires_at TIMESTAMPTZ,
    next_attempt_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_version_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS mentor_concursos.knowledge_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_version_id UUID NOT NULL REFERENCES mentor_concursos.knowledge_source_versions(id) ON DELETE RESTRICT,
    subject_id UUID REFERENCES mentor_concursos.subjects(id) ON DELETE RESTRICT,
    topic_id UUID REFERENCES mentor_concursos.topics(id) ON DELETE RESTRICT,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    text TEXT NOT NULL CHECK (btrim(text) <> ''),
    normalized_text TEXT NOT NULL CHECK (btrim(normalized_text) <> ''),
    content_sha256 TEXT NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    page_start INTEGER CHECK (page_start IS NULL OR page_start > 0),
    page_end INTEGER CHECK (page_end IS NULL OR page_end >= page_start),
    section_path TEXT[] NOT NULL DEFAULT '{}',
    legal_locator TEXT,
    character_count INTEGER NOT NULL CHECK (character_count > 0),
    token_count INTEGER NOT NULL CHECK (token_count > 0),
    search_vector TSVECTOR GENERATED ALWAYS AS (to_tsvector('portuguese', normalized_text)) STORED,
    status TEXT NOT NULL DEFAULT 'pending_review' CHECK (status IN ('pending_review','approved','rejected','indexed')),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_version_id, ordinal),
    UNIQUE(source_version_id, content_sha256)
);

CREATE TABLE IF NOT EXISTS mentor_concursos.knowledge_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_id UUID NOT NULL REFERENCES mentor_concursos.knowledge_chunks(id) ON DELETE RESTRICT,
    model_id TEXT NOT NULL,
    model_revision TEXT NOT NULL,
    dimensions INTEGER NOT NULL CHECK (dimensions = 384),
    embedding vector(384) NOT NULL,
    normalized BOOLEAN NOT NULL DEFAULT TRUE,
    content_sha256 TEXT NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(chunk_id, model_id, model_revision)
);

CREATE TABLE IF NOT EXISTS mentor_concursos.source_reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID NOT NULL REFERENCES mentor_concursos.knowledge_sources(id) ON DELETE RESTRICT,
    source_version_id UUID REFERENCES mentor_concursos.knowledge_source_versions(id) ON DELETE RESTRICT,
    reviewer UUID NOT NULL REFERENCES mentor_concursos.users(id) ON DELETE RESTRICT,
    decision TEXT NOT NULL CHECK (decision IN ('approved','rejected','superseded')),
    reason TEXT NOT NULL CHECK (btrim(reason) <> '' AND length(reason) <= 2000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS mentor_concursos.retrieval_audit (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES mentor_concursos.users(id) ON DELETE RESTRICT,
    query_hash TEXT NOT NULL CHECK (query_hash ~ '^[0-9a-f]{64}$'),
    filters JSONB NOT NULL DEFAULT '{}'::jsonb,
    returned_chunk_ids UUID[] NOT NULL DEFAULT '{}',
    scores JSONB NOT NULL DEFAULT '[]'::jsonb,
    model_id TEXT NOT NULL,
    model_revision TEXT NOT NULL,
    request_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS mentor_concursos.ingestion_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES mentor_concursos.ingestion_jobs(id) ON DELETE RESTRICT,
    stage TEXT NOT NULL,
    result TEXT NOT NULL CHECK (result IN ('started','succeeded','failed','skipped')),
    duration_ms INTEGER CHECK (duration_ms IS NULL OR duration_ms >= 0),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS knowledge_sources_owner_status_idx ON mentor_concursos.knowledge_sources(owner_user_id, status);
CREATE INDEX IF NOT EXISTS knowledge_versions_status_idx ON mentor_concursos.knowledge_source_versions(status, source_id);
CREATE INDEX IF NOT EXISTS ingestion_jobs_queue_idx ON mentor_concursos.ingestion_jobs(status, next_attempt_at, created_at);
CREATE INDEX IF NOT EXISTS knowledge_chunks_search_idx ON mentor_concursos.knowledge_chunks USING GIN(search_vector);
CREATE INDEX IF NOT EXISTS knowledge_chunks_filter_idx ON mentor_concursos.knowledge_chunks(source_version_id, subject_id, topic_id, status);
CREATE INDEX IF NOT EXISTS knowledge_embeddings_hnsw_idx ON mentor_concursos.knowledge_embeddings USING hnsw (embedding vector_cosine_ops);

CREATE OR REPLACE FUNCTION mentor_concursos.knowledge_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = CURRENT_TIMESTAMP; RETURN NEW; END $$;

DROP TRIGGER IF EXISTS knowledge_sources_updated_at ON mentor_concursos.knowledge_sources;
CREATE TRIGGER knowledge_sources_updated_at BEFORE UPDATE ON mentor_concursos.knowledge_sources FOR EACH ROW EXECUTE FUNCTION mentor_concursos.knowledge_updated_at();
DROP TRIGGER IF EXISTS knowledge_versions_updated_at ON mentor_concursos.knowledge_source_versions;
CREATE TRIGGER knowledge_versions_updated_at BEFORE UPDATE ON mentor_concursos.knowledge_source_versions FOR EACH ROW EXECUTE FUNCTION mentor_concursos.knowledge_updated_at();
DROP TRIGGER IF EXISTS ingestion_jobs_updated_at ON mentor_concursos.ingestion_jobs;
CREATE TRIGGER ingestion_jobs_updated_at BEFORE UPDATE ON mentor_concursos.ingestion_jobs FOR EACH ROW EXECUTE FUNCTION mentor_concursos.knowledge_updated_at();

COMMENT ON TABLE mentor_concursos.knowledge_chunks IS 'Trechos imutáveis e rastreáveis; só versões aprovadas podem ser indexadas.';
COMMENT ON TABLE mentor_concursos.knowledge_embeddings IS 'Vetores locais normalizados; dimensão contratual 384.';
COMMENT ON TABLE mentor_concursos.retrieval_audit IS 'Auditoria sem texto de consulta, somente hash e resultados.';
