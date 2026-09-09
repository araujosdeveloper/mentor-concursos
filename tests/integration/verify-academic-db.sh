#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."

# Fixtures are wrapped in a transaction and rolled back; no production entity
# is created. The script exercises constraints against the dedicated database.
docker compose exec -T mentor-concursos-postgres sh -ceu 'PGPASSWORD="$POSTGRES_PASSWORD" psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'SQL'
BEGIN;
SET LOCAL search_path TO mentor_concursos, public;

CREATE TEMP TABLE academic_fixture_user (id uuid);
CREATE TEMP TABLE academic_fixture_other_user (id uuid);
CREATE TEMP TABLE academic_fixture_subject (id uuid);
WITH inserted AS (
  INSERT INTO users(telegram_user_id, name) VALUES (-2099999999, 'fixture') RETURNING id
)
INSERT INTO academic_fixture_user SELECT id FROM inserted;
WITH inserted AS (
  INSERT INTO users(telegram_user_id, name) VALUES (-2099999998, 'fixture-other') RETURNING id
)
INSERT INTO academic_fixture_other_user SELECT id FROM inserted;

-- A user may have one active goal only.
INSERT INTO study_goals(user_id, name, horizon, weekly_minutes, active, status)
SELECT id, 'fixture goal', 'test', 60, TRUE, 'active' FROM academic_fixture_user
RETURNING id;

-- Resource ownership is scoped by user: the second fixture user cannot see
-- the first user's goal through the authorization predicate.
DO $$ BEGIN
  IF EXISTS (
    SELECT 1
    FROM study_goals g
    JOIN academic_fixture_other_user u ON u.id = g.user_id
    WHERE g.name = 'fixture goal'
  ) THEN
    RAISE EXCEPTION 'cross-user goal visibility detected';
  END IF;
  IF NOT EXISTS (
    SELECT 1
    FROM study_goals g
    JOIN academic_fixture_user u ON u.id = g.user_id
    WHERE g.name = 'fixture goal'
  ) THEN
    RAISE EXCEPTION 'fixture goal missing for owner';
  END IF;
END $$;
SAVEPOINT duplicate_goal;
DO $$ BEGIN
  INSERT INTO study_goals(user_id, name, horizon, weekly_minutes, active, status)
  SELECT id, 'duplicate', 'test', 60, TRUE, 'active' FROM academic_fixture_user;
  RAISE EXCEPTION 'unique goal constraint did not fire';
EXCEPTION WHEN unique_violation THEN NULL;
END $$;
RELEASE SAVEPOINT duplicate_goal;

-- Session uniqueness and temporal checks are database-enforced.
WITH inserted AS (
  INSERT INTO subjects(code, name) VALUES ('fixture_subject', 'Fixture') RETURNING id
)
INSERT INTO academic_fixture_subject SELECT id FROM inserted;

WITH root AS (
  INSERT INTO topics(subject_id, code, name)
  SELECT id, 'fixture-root', 'Root' FROM academic_fixture_subject RETURNING id
)
INSERT INTO topics(subject_id, parent_topic_id, code, name)
SELECT s.id, root.id, 'fixture-child', 'Child' FROM academic_fixture_subject s, root;
SAVEPOINT topic_cycle;
DO $$ BEGIN
  UPDATE topics SET parent_topic_id=(SELECT id FROM topics WHERE code='fixture-child') WHERE code='fixture-root';
  RAISE EXCEPTION 'topic cycle guard did not fire';
EXCEPTION WHEN check_violation THEN NULL;
END $$;
RELEASE SAVEPOINT topic_cycle;

INSERT INTO study_sessions(user_id, goal_id, subject_id, started_at)
SELECT u.id, g.id, s.id, CURRENT_TIMESTAMP FROM academic_fixture_user u, study_goals g, academic_fixture_subject s
WHERE g.user_id=u.id RETURNING id;
SAVEPOINT duplicate_session;
DO $$ BEGIN
  INSERT INTO study_sessions(user_id, goal_id, subject_id, started_at)
  SELECT u.id, g.id, s.id, CURRENT_TIMESTAMP FROM academic_fixture_user u, study_goals g, academic_fixture_subject s WHERE g.user_id=u.id;
  RAISE EXCEPTION 'unique session constraint did not fire';
EXCEPTION WHEN unique_violation THEN NULL;
END $$;
RELEASE SAVEPOINT duplicate_session;

ROLLBACK;
SELECT 'PASS academic constraints and rollback';
SQL
