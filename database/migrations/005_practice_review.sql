-- Questões e revisão espaçada determinísticas, sempre vinculadas a evidência indexed.
CREATE TABLE IF NOT EXISTS mentor_concursos.practice_questions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id UUID NOT NULL REFERENCES mentor_concursos.users(id) ON DELETE RESTRICT,
    source_version_id UUID NOT NULL REFERENCES mentor_concursos.knowledge_source_versions(id) ON DELETE RESTRICT,
    prompt TEXT NOT NULL CHECK (btrim(prompt) <> '' AND length(prompt) <= 2000),
    alternatives JSONB NOT NULL CHECK (jsonb_typeof(alternatives) = 'array' AND jsonb_array_length(alternatives) BETWEEN 4 AND 5),
    correct_option TEXT NOT NULL CHECK (correct_option IN ('A','B','C','D','E')),
    explanation TEXT NOT NULL CHECK (btrim(explanation) <> ''),
    citation JSONB NOT NULL CHECK (jsonb_typeof(citation) = 'object'),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','retired')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS mentor_concursos.practice_attempts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    question_id UUID NOT NULL REFERENCES mentor_concursos.practice_questions(id) ON DELETE RESTRICT,
    user_id UUID NOT NULL REFERENCES mentor_concursos.users(id) ON DELETE RESTRICT,
    selected_option TEXT NOT NULL CHECK (selected_option IN ('A','B','C','D','E')),
    correct BOOLEAN NOT NULL,
    idempotency_key TEXT NOT NULL CHECK (length(idempotency_key) BETWEEN 8 AND 128),
    request_id TEXT NOT NULL,
    answered_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, idempotency_key),
    UNIQUE(user_id, question_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS mentor_concursos.practice_review_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES mentor_concursos.users(id) ON DELETE RESTRICT,
    question_id UUID NOT NULL REFERENCES mentor_concursos.practice_questions(id) ON DELETE RESTRICT,
    next_review_at TIMESTAMPTZ NOT NULL,
    interval_days INTEGER NOT NULL CHECK (interval_days > 0),
    consecutive_correct INTEGER NOT NULL DEFAULT 0 CHECK (consecutive_correct >= 0),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    last_correct BOOLEAN NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','completed','cancelled')),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, question_id)
);

CREATE TABLE IF NOT EXISTS mentor_concursos.practice_error_book (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES mentor_concursos.users(id) ON DELETE RESTRICT,
    question_id UUID NOT NULL REFERENCES mentor_concursos.practice_questions(id) ON DELETE RESTRICT,
    wrong_count INTEGER NOT NULL DEFAULT 1 CHECK (wrong_count > 0),
    last_wrong_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMPTZ,
    UNIQUE(user_id, question_id)
);

CREATE TABLE IF NOT EXISTS mentor_concursos.practice_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES mentor_concursos.users(id) ON DELETE RESTRICT,
    quantity INTEGER NOT NULL CHECK (quantity BETWEEN 1 AND 20),
    question_ids UUID[] NOT NULL CHECK (cardinality(question_ids) = quantity),
    current_index INTEGER NOT NULL DEFAULT 0 CHECK (current_index >= 0),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','completed','cancelled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS practice_runs_one_active_idx
    ON mentor_concursos.practice_runs(user_id) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS practice_questions_owner_idx ON mentor_concursos.practice_questions(owner_user_id, status, created_at);
CREATE INDEX IF NOT EXISTS practice_attempts_user_idx ON mentor_concursos.practice_attempts(user_id, answered_at DESC);
CREATE INDEX IF NOT EXISTS practice_reviews_due_idx ON mentor_concursos.practice_review_items(user_id, status, next_review_at);
CREATE INDEX IF NOT EXISTS practice_errors_user_idx ON mentor_concursos.practice_error_book(user_id, resolved_at, last_wrong_at DESC);

CREATE OR REPLACE FUNCTION mentor_concursos.practice_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = CURRENT_TIMESTAMP; RETURN NEW; END $$;
DROP TRIGGER IF EXISTS practice_questions_updated_at ON mentor_concursos.practice_questions;
CREATE TRIGGER practice_questions_updated_at BEFORE UPDATE ON mentor_concursos.practice_questions FOR EACH ROW EXECUTE FUNCTION mentor_concursos.practice_updated_at();
DROP TRIGGER IF EXISTS practice_runs_updated_at ON mentor_concursos.practice_runs;
CREATE TRIGGER practice_runs_updated_at BEFORE UPDATE ON mentor_concursos.practice_runs FOR EACH ROW EXECUTE FUNCTION mentor_concursos.practice_updated_at();
