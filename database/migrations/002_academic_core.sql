-- Núcleo acadêmico determinístico. Aplicada atomicamente pelo executor com advisory lock.
SET LOCAL search_path TO mentor_concursos, public;

CREATE OR REPLACE FUNCTION mentor_concursos.touch_updated_at()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = CURRENT_TIMESTAMP;
  RETURN NEW;
END;
$$;

CREATE TABLE IF NOT EXISTS mentor_concursos.users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  telegram_user_id BIGINT UNIQUE,
  name TEXT NOT NULL CHECK (btrim(name) <> '' AND char_length(name) <= 160),
  timezone TEXT NOT NULL DEFAULT 'America/Sao_Paulo',
  available_minutes_per_day INTEGER NOT NULL DEFAULT 210 CHECK (available_minutes_per_day BETWEEN 1 AND 1440),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'suspended')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS mentor_concursos.study_tracks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code TEXT NOT NULL UNIQUE CHECK (code ~ '^[a-z][a-z0-9_]{1,63}$'),
  name TEXT NOT NULL CHECK (btrim(name) <> ''),
  description TEXT NOT NULL DEFAULT '',
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS mentor_concursos.exams (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization TEXT NOT NULL CHECK (btrim(organization) <> ''),
  role TEXT NOT NULL CHECK (btrim(role) <> ''),
  board TEXT NOT NULL DEFAULT '',
  level TEXT NOT NULL DEFAULT 'unknown' CHECK (level IN ('elementary', 'secondary', 'higher', 'unknown')),
  expected_date DATE,
  status TEXT NOT NULL DEFAULT 'unknown' CHECK (status IN ('unknown', 'planned', 'confirmed', 'cancelled', 'completed')),
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS mentor_concursos.study_goals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES mentor_concursos.users(id) ON DELETE RESTRICT,
  exam_id UUID REFERENCES mentor_concursos.exams(id) ON DELETE RESTRICT,
  name TEXT NOT NULL CHECK (btrim(name) <> ''),
  horizon TEXT NOT NULL CHECK (btrim(horizon) <> ''),
  weekly_minutes INTEGER NOT NULL CHECK (weekly_minutes BETWEEN 1 AND 10080),
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'active', 'paused', 'completed', 'cancelled')),
  active BOOLEAN NOT NULL DEFAULT FALSE,
  version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_goal_per_user ON mentor_concursos.study_goals(user_id) WHERE active;

CREATE TABLE IF NOT EXISTS mentor_concursos.goal_tracks (
  goal_id UUID NOT NULL REFERENCES mentor_concursos.study_goals(id) ON DELETE RESTRICT,
  track_id UUID NOT NULL REFERENCES mentor_concursos.study_tracks(id) ON DELETE RESTRICT,
  PRIMARY KEY (goal_id, track_id)
);

CREATE TABLE IF NOT EXISTS mentor_concursos.syllabus_versions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  goal_id UUID NOT NULL REFERENCES mentor_concursos.study_goals(id) ON DELETE RESTRICT,
  version INTEGER NOT NULL CHECK (version > 0),
  title TEXT NOT NULL CHECK (btrim(title) <> ''),
  source TEXT NOT NULL CHECK (btrim(source) <> ''),
  published_at DATE,
  checksum TEXT CHECK (checksum IS NULL OR checksum ~ '^[0-9a-f]{64}$'),
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'active', 'superseded', 'archived')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (goal_id, version)
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_syllabus_per_goal ON mentor_concursos.syllabus_versions(goal_id) WHERE status = 'active';

CREATE TABLE IF NOT EXISTS mentor_concursos.subjects (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code TEXT NOT NULL UNIQUE CHECK (code ~ '^[a-z][a-z0-9_]{1,79}$'),
  name TEXT NOT NULL CHECK (btrim(name) <> ''),
  description TEXT NOT NULL DEFAULT '',
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS mentor_concursos.subject_tracks (
  subject_id UUID NOT NULL REFERENCES mentor_concursos.subjects(id) ON DELETE RESTRICT,
  track_id UUID NOT NULL REFERENCES mentor_concursos.study_tracks(id) ON DELETE RESTRICT,
  PRIMARY KEY (subject_id, track_id)
);

CREATE TABLE IF NOT EXISTS mentor_concursos.syllabus_subjects (
  syllabus_id UUID NOT NULL REFERENCES mentor_concursos.syllabus_versions(id) ON DELETE RESTRICT,
  subject_id UUID NOT NULL REFERENCES mentor_concursos.subjects(id) ON DELETE RESTRICT,
  weight NUMERIC(8,3) CHECK (weight IS NULL OR weight >= 0),
  ordinal INTEGER NOT NULL CHECK (ordinal > 0),
  priority TEXT NOT NULL DEFAULT 'normal' CHECK (priority IN ('low', 'normal', 'high')),
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  PRIMARY KEY (syllabus_id, subject_id)
);

CREATE TABLE IF NOT EXISTS mentor_concursos.topics (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  subject_id UUID NOT NULL REFERENCES mentor_concursos.subjects(id) ON DELETE RESTRICT,
  parent_topic_id UUID REFERENCES mentor_concursos.topics(id) ON DELETE RESTRICT,
  code TEXT NOT NULL CHECK (code ~ '^[a-z0-9][a-z0-9_.-]{0,79}$'),
  name TEXT NOT NULL CHECK (btrim(name) <> ''),
  ordinal INTEGER NOT NULL DEFAULT 1 CHECK (ordinal > 0),
  active BOOLEAN NOT NULL DEFAULT TRUE,
  path TEXT NOT NULL DEFAULT '',
  UNIQUE (subject_id, code),
  CHECK (parent_topic_id IS NULL OR parent_topic_id <> id)
);
CREATE INDEX IF NOT EXISTS topics_parent_idx ON mentor_concursos.topics(parent_topic_id);

CREATE TABLE IF NOT EXISTS mentor_concursos.syllabus_topics (
  syllabus_id UUID NOT NULL REFERENCES mentor_concursos.syllabus_versions(id) ON DELETE RESTRICT,
  topic_id UUID NOT NULL REFERENCES mentor_concursos.topics(id) ON DELETE RESTRICT,
  incidence NUMERIC(8,3) CHECK (incidence IS NULL OR incidence >= 0),
  status TEXT NOT NULL DEFAULT 'included' CHECK (status IN ('included', 'excluded', 'unknown')),
  PRIMARY KEY (syllabus_id, topic_id)
);

CREATE TABLE IF NOT EXISTS mentor_concursos.study_cycles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  goal_id UUID NOT NULL REFERENCES mentor_concursos.study_goals(id) ON DELETE RESTRICT,
  name TEXT NOT NULL CHECK (btrim(name) <> ''),
  starts_at TIMESTAMPTZ NOT NULL,
  ends_at TIMESTAMPTZ NOT NULL,
  weekly_minutes INTEGER NOT NULL CHECK (weekly_minutes BETWEEN 1 AND 10080),
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'active', 'paused', 'completed', 'cancelled')),
  version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CHECK (ends_at > starts_at)
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_cycle_per_goal ON mentor_concursos.study_cycles(goal_id) WHERE status = 'active';

CREATE TABLE IF NOT EXISTS mentor_concursos.study_plan_items (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  cycle_id UUID NOT NULL REFERENCES mentor_concursos.study_cycles(id) ON DELETE RESTRICT,
  subject_id UUID NOT NULL REFERENCES mentor_concursos.subjects(id) ON DELETE RESTRICT,
  topic_id UUID REFERENCES mentor_concursos.topics(id) ON DELETE RESTRICT,
  activity_type TEXT NOT NULL CHECK (activity_type IN ('study', 'review', 'revision', 'exercise')),
  planned_minutes INTEGER NOT NULL CHECK (planned_minutes > 0),
  ordinal INTEGER NOT NULL CHECK (ordinal > 0),
  status TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('planned', 'in_progress', 'completed', 'cancelled')),
  planned_for DATE,
  completion_criteria TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS mentor_concursos.study_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES mentor_concursos.users(id) ON DELETE RESTRICT,
  goal_id UUID NOT NULL REFERENCES mentor_concursos.study_goals(id) ON DELETE RESTRICT,
  plan_item_id UUID REFERENCES mentor_concursos.study_plan_items(id) ON DELETE RESTRICT,
  subject_id UUID NOT NULL REFERENCES mentor_concursos.subjects(id) ON DELETE RESTRICT,
  topic_id UUID REFERENCES mentor_concursos.topics(id) ON DELETE RESTRICT,
  started_at TIMESTAMPTZ NOT NULL,
  ended_at TIMESTAMPTZ,
  accumulated_pause_seconds INTEGER NOT NULL DEFAULT 0 CHECK (accumulated_pause_seconds >= 0),
  net_duration_seconds INTEGER NOT NULL DEFAULT 0 CHECK (net_duration_seconds >= 0),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused', 'completed', 'cancelled')),
  version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
  observation TEXT CHECK (observation IS NULL OR char_length(observation) <= 1000),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CHECK (ended_at IS NULL OR ended_at >= started_at)
);
CREATE UNIQUE INDEX IF NOT EXISTS one_open_session_per_user ON mentor_concursos.study_sessions(user_id) WHERE status IN ('active', 'paused');

CREATE TABLE IF NOT EXISTS mentor_concursos.study_session_pauses (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id UUID NOT NULL REFERENCES mentor_concursos.study_sessions(id) ON DELETE RESTRICT,
  started_at TIMESTAMPTZ NOT NULL,
  ended_at TIMESTAMPTZ,
  CHECK (ended_at IS NULL OR ended_at >= started_at)
);
CREATE UNIQUE INDEX IF NOT EXISTS one_open_pause_per_session ON mentor_concursos.study_session_pauses(session_id) WHERE ended_at IS NULL;

CREATE TABLE IF NOT EXISTS mentor_concursos.topic_mastery (
  user_id UUID NOT NULL REFERENCES mentor_concursos.users(id) ON DELETE RESTRICT,
  goal_id UUID NOT NULL REFERENCES mentor_concursos.study_goals(id) ON DELETE RESTRICT,
  topic_id UUID NOT NULL REFERENCES mentor_concursos.topics(id) ON DELETE RESTRICT,
  state TEXT NOT NULL DEFAULT 'not_started' CHECK (state IN ('not_started', 'in_progress', 'review', 'consolidated')),
  evidence_count INTEGER NOT NULL DEFAULT 0 CHECK (evidence_count >= 0),
  evidence_seconds INTEGER NOT NULL DEFAULT 0 CHECK (evidence_seconds >= 0),
  version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id, goal_id, topic_id)
);

CREATE TABLE IF NOT EXISTS mentor_concursos.audit_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  actor TEXT NOT NULL CHECK (btrim(actor) <> ''),
  action TEXT NOT NULL CHECK (btrim(action) <> ''),
  entity TEXT NOT NULL CHECK (btrim(entity) <> ''),
  entity_id UUID,
  request_id TEXT NOT NULL CHECK (request_id ~ '^[A-Za-z0-9_-]{1,64}$'),
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS audit_events_entity_idx ON mentor_concursos.audit_events(entity, entity_id, occurred_at DESC);

CREATE TABLE IF NOT EXISTS mentor_concursos.idempotency_keys (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  key TEXT NOT NULL CHECK (key ~ '^[A-Za-z0-9._:-]{8,128}$'),
  scope TEXT NOT NULL CHECK (btrim(scope) <> ''),
  fingerprint TEXT NOT NULL CHECK (fingerprint ~ '^[0-9a-f]{64}$'),
  status TEXT NOT NULL CHECK (status IN ('processing', 'completed', 'failed')),
  response JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(response) = 'object'),
  expires_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (key, scope)
);

DO $$
DECLARE
  table_name TEXT;
BEGIN
  FOREACH table_name IN ARRAY ARRAY['users','study_tracks','exams','study_goals','syllabus_versions','subjects','study_plan_items','study_sessions'] LOOP
    EXECUTE format('DROP TRIGGER IF EXISTS %I_updated_at ON mentor_concursos.%I', table_name, table_name);
    EXECUTE format('CREATE TRIGGER %I_updated_at BEFORE UPDATE ON mentor_concursos.%I FOR EACH ROW EXECUTE FUNCTION mentor_concursos.touch_updated_at()', table_name, table_name);
  END LOOP;
END $$;

COMMENT ON TABLE mentor_concursos.study_sessions IS 'Sessões são histórico; encerramento nunca depende de duração enviada pelo cliente.';
COMMENT ON TABLE mentor_concursos.idempotency_keys IS 'Chaves de mutação com fingerprint para impedir repetição inconsistente.';
COMMENT ON TABLE mentor_concursos.audit_events IS 'Trilha append-only de mutações do domínio acadêmico.';
