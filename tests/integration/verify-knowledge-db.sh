#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

docker exec mentor-concursos-postgres sh -ceu 'PGPASSWORD="$POSTGRES_PASSWORD" psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'SQL'
BEGIN;
SET LOCAL search_path TO mentor_concursos, public;
CREATE TEMP TABLE fixture_ids (user_id uuid, source_id uuid, version_id uuid);
WITH u AS (SELECT id FROM users ORDER BY created_at LIMIT 1), s AS (
  INSERT INTO knowledge_sources(owner_user_id, source_type, title, license_status, trust_level)
  SELECT id, 'synthetic', 'FIXTURE — não é fonte real', 'allowed', 'review' FROM u RETURNING id, owner_user_id
), v AS (
  INSERT INTO knowledge_source_versions(source_id, version_label, sha256, mime_type, byte_size, storage_key)
  SELECT id, 'fixture-1', repeat('a',64), 'text/plain', 10, 'fixture/' || id || '/a.txt' FROM s RETURNING id, source_id
)
INSERT INTO fixture_ids SELECT s.owner_user_id, s.id, v.id FROM s JOIN v ON v.source_id=s.id;
INSERT INTO ingestion_jobs(source_version_id, requested_by, idempotency_key)
SELECT version_id, user_id, 'fixture-job-001' FROM fixture_ids;
DO $$ BEGIN
  INSERT INTO knowledge_source_versions(source_id, version_label, sha256, mime_type, byte_size, storage_key)
  SELECT source_id, 'fixture-duplicate', repeat('a',64), 'text/plain', 10, 'fixture/duplicate.txt' FROM fixture_ids;
  RAISE EXCEPTION 'duplicate sha constraint did not fire';
EXCEPTION WHEN unique_violation THEN NULL;
END $$;
DO $$ BEGIN
  INSERT INTO knowledge_chunks(source_version_id, ordinal, text, normalized_text, content_sha256, character_count, token_count)
  SELECT version_id, 0, '', '', repeat('b',64), 0, 0 FROM fixture_ids;
  RAISE EXCEPTION 'empty chunk constraint did not fire';
EXCEPTION WHEN check_violation THEN NULL;
END $$;
ROLLBACK;
SELECT 'PASS knowledge constraints and rollback';
SQL
