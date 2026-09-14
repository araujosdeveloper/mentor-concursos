#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."

docker compose exec -T mentor-concursos-postgres sh -ceu \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'SQL'
BEGIN;
SET LOCAL search_path TO mentor_concursos, public;

DO $$ BEGIN
  IF to_regclass('mentor_concursos.user_study_availability') IS NULL OR
     to_regclass('mentor_concursos.study_plan_proposals') IS NULL THEN
    RAISE EXCEPTION 'adaptive plan tables missing';
  END IF;
END $$;

CREATE TEMP TABLE fixture_plan_user(id uuid);
WITH inserted AS (
  INSERT INTO users(telegram_user_id,name) VALUES (-2099999901,'fixture-plan') RETURNING id
)
INSERT INTO fixture_plan_user SELECT id FROM inserted;

INSERT INTO user_study_availability(user_id,weekday,available_minutes)
SELECT id,0,90 FROM fixture_plan_user;

DO $$ BEGIN
  BEGIN
    INSERT INTO user_study_availability(user_id,weekday,available_minutes)
    SELECT id,1,14 FROM fixture_plan_user;
    RAISE EXCEPTION 'daily minimum constraint did not fire';
  EXCEPTION WHEN check_violation THEN NULL;
  END;
END $$;

INSERT INTO study_plan_proposals(user_id,proposal_type,normalized_payload,calculated_summary,fingerprint,expires_at)
SELECT id,'create','{}','{}',repeat('a',64),CURRENT_TIMESTAMP + interval '10 minutes'
FROM fixture_plan_user;

DO $$ BEGIN
  BEGIN
    INSERT INTO study_plan_proposals(user_id,proposal_type,normalized_payload,calculated_summary,fingerprint,expires_at)
    SELECT id,'create','{}','{}',repeat('b',64),CURRENT_TIMESTAMP + interval '10 minutes'
    FROM fixture_plan_user;
    RAISE EXCEPTION 'single draft proposal constraint did not fire';
  EXCEPTION WHEN unique_violation THEN NULL;
  END;
END $$;

ROLLBACK;
SELECT 'PASS adaptive plan migration constraints and rollback';
SQL
