-- Correção forward: impede ciclos na árvore de tópicos sem editar migration aplicada.
SET LOCAL search_path TO mentor_concursos, public;

CREATE OR REPLACE FUNCTION mentor_concursos.prevent_topic_cycle()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  found_cycle BOOLEAN;
BEGIN
  IF NEW.parent_topic_id IS NULL THEN
    RETURN NEW;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM mentor_concursos.topics p WHERE p.id = NEW.parent_topic_id AND p.subject_id = NEW.subject_id) THEN
    RAISE EXCEPTION 'parent_topic_id deve pertencer à mesma disciplina' USING ERRCODE = '23514';
  END IF;
  WITH RECURSIVE ancestors(id) AS (
    SELECT NEW.parent_topic_id
    UNION ALL
    SELECT t.parent_topic_id FROM mentor_concursos.topics t JOIN ancestors a ON t.id = a.id WHERE t.parent_topic_id IS NOT NULL
  )
  SELECT EXISTS (SELECT 1 FROM ancestors WHERE id = NEW.id) INTO found_cycle;
  IF found_cycle THEN
    RAISE EXCEPTION 'ciclo de tópicos não permitido' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS topics_cycle_guard ON mentor_concursos.topics;
CREATE TRIGGER topics_cycle_guard
BEFORE INSERT OR UPDATE OF parent_topic_id, subject_id ON mentor_concursos.topics
FOR EACH ROW EXECUTE FUNCTION mentor_concursos.prevent_topic_cycle();
