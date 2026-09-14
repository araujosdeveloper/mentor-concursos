-- Planejamento diário adaptativo: disponibilidade, propostas e proveniência.
SET LOCAL search_path TO mentor_concursos, public;

CREATE TABLE IF NOT EXISTS mentor_concursos.user_study_availability (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES mentor_concursos.users(id) ON DELETE RESTRICT,
  weekday SMALLINT NOT NULL CHECK (weekday BETWEEN 0 AND 6),
  available_minutes INTEGER NOT NULL CHECK (available_minutes = 0 OR available_minutes BETWEEN 15 AND 960),
  active BOOLEAN NOT NULL DEFAULT TRUE,
  version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (user_id, weekday)
);

CREATE TABLE IF NOT EXISTS mentor_concursos.study_plan_proposals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES mentor_concursos.users(id) ON DELETE RESTRICT,
  goal_id UUID REFERENCES mentor_concursos.study_goals(id) ON DELETE RESTRICT,
  exam_id UUID REFERENCES mentor_concursos.exams(id) ON DELETE RESTRICT,
  proposal_type TEXT NOT NULL DEFAULT 'create' CHECK (proposal_type IN ('create','replan')),
  normalized_payload JSONB NOT NULL CHECK (jsonb_typeof(normalized_payload) = 'object'),
  calculated_summary JSONB NOT NULL CHECK (jsonb_typeof(calculated_summary) = 'object'),
  fingerprint TEXT NOT NULL CHECK (fingerprint ~ '^[0-9a-f]{64}$'),
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','confirmed','expired','cancelled')),
  expires_at TIMESTAMPTZ NOT NULL,
  confirmed_at TIMESTAMPTZ,
  cancelled_at TIMESTAMPTZ,
  version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CHECK ((proposal_type = 'replan' AND goal_id IS NOT NULL) OR proposal_type = 'create')
);

CREATE UNIQUE INDEX IF NOT EXISTS one_draft_plan_proposal_per_user
  ON mentor_concursos.study_plan_proposals(user_id) WHERE status = 'draft';
CREATE INDEX IF NOT EXISTS study_plan_proposals_user_status_idx
  ON mentor_concursos.study_plan_proposals(user_id, status, created_at DESC);

CREATE OR REPLACE FUNCTION mentor_concursos.enforce_weekly_availability_limit()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF (SELECT COALESCE(SUM(available_minutes),0)
      FROM mentor_concursos.user_study_availability
      WHERE user_id = NEW.user_id AND active) > 6720 THEN
    RAISE EXCEPTION 'disponibilidade semanal acima de 6720 minutos' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS user_study_availability_weekly_limit
  ON mentor_concursos.user_study_availability;
CREATE CONSTRAINT TRIGGER user_study_availability_weekly_limit
AFTER INSERT OR UPDATE ON mentor_concursos.user_study_availability
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
EXECUTE FUNCTION mentor_concursos.enforce_weekly_availability_limit();

ALTER TABLE mentor_concursos.study_cycles
  ADD COLUMN IF NOT EXISTS proposal_id UUID REFERENCES mentor_concursos.study_plan_proposals(id) ON DELETE RESTRICT,
  ADD COLUMN IF NOT EXISTS plan_revision INTEGER NOT NULL DEFAULT 1 CHECK (plan_revision > 0);

ALTER TABLE mentor_concursos.study_plan_items
  ADD COLUMN IF NOT EXISTS proposal_id UUID REFERENCES mentor_concursos.study_plan_proposals(id) ON DELETE RESTRICT;

DROP TRIGGER IF EXISTS user_study_availability_updated_at ON mentor_concursos.user_study_availability;
CREATE TRIGGER user_study_availability_updated_at BEFORE UPDATE ON mentor_concursos.user_study_availability
FOR EACH ROW EXECUTE FUNCTION mentor_concursos.touch_updated_at();

DROP TRIGGER IF EXISTS study_plan_proposals_updated_at ON mentor_concursos.study_plan_proposals;
CREATE TRIGGER study_plan_proposals_updated_at BEFORE UPDATE ON mentor_concursos.study_plan_proposals
FOR EACH ROW EXECUTE FUNCTION mentor_concursos.touch_updated_at();

COMMENT ON TABLE mentor_concursos.study_plan_proposals IS 'Snapshot explicável; confirmação é explícita, idempotente e vinculada aos itens gerados.';
COMMENT ON COLUMN mentor_concursos.study_cycles.plan_revision IS 'Revisão monotônica do calendário; histórico concluído nunca é apagado.';
