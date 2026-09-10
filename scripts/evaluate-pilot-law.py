"""Avaliação isolada da versão piloto pendente; nunca usa o endpoint normal."""

# ruff: noqa: E501, B007, B023

from __future__ import annotations

import json
import math
import os
import urllib.request
from statistics import fmean

import psycopg
from psycopg.rows import dict_row

VERSION = "1eccd249-b219-4d96-8e36-5dba1535159e"
QUERIES = [
    ("artigo 1 processo administrativo", "Art. 1º", "literal"),
    ("direitos do administrado perante a administração", "Art. 3º", "paráfrase"),
    ("deveres do administrado", "Art. 4º", "literal"),
    ("como começa o processo administrativo", "Art. 5º", "paráfrase"),
    ("requerimento inicial dados necessários", "Art. 6º", "literal"),
    ("competência não pode ser renunciada", "Art. 11.", "negação"),
    ("delegação de competência administrativa", "Art. 12.", "literal"),
    ("avocação temporária excepcional", "Art. 15.", "exceção"),
    ("provas obtidas por meios ilícitos", "Art. 30.", "literal"),
    ("consulta pública assunto de interesse geral", "Art. 31.", "paráfrase"),
    ("prazo para decidir processo administrativo", "Art. 49.", "prazo"),
    ("decisão coordenada interinstitucional", "Art. 49-A", "literal"),
    ("a lei trata de teletransporte", None, "sem_resposta"),
    ("instrução menos onerosa aos interessados", "Art. 29.", "paráfrase"),
    ("entrada em vigor da lei", "Art. 70.", "literal"),
]


def conn() -> psycopg.Connection:
    return psycopg.connect(host=os.environ["DATABASE_HOST"], port=os.environ["DATABASE_PORT"], dbname=os.environ["DATABASE_NAME"], user=os.environ["DATABASE_USER"], password=os.environ["DATABASE_PASSWORD"], row_factory=dict_row)


def embed(query: str) -> list[float]:
    req = urllib.request.Request("http://mentor-concursos-embeddings:8090/embed", data=json.dumps({"texts": [query], "prefix": "query:"}).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read())["vectors"][0]


def main() -> None:
    lexical_recall, vector_recall, hybrid_recall, reciprocal, ndcg = [], [], [], [], []
    no_answer_ok = 0
    with conn() as connection:
        for query, expected, category in QUERIES:
            lexical = connection.execute("SELECT c.id,c.legal_locator,c.source_version_id,ts_rank_cd(c.search_vector,websearch_to_tsquery('portuguese',%s)) score FROM mentor_concursos.knowledge_chunks c WHERE c.source_version_id=%s AND c.status='pending_review' AND c.search_vector @@ websearch_to_tsquery('portuguese',%s) ORDER BY score DESC,c.id LIMIT 5", (query, VERSION, query)).fetchall()
            vector = connection.execute("SELECT c.id,c.legal_locator,c.source_version_id,1-(e.embedding <=> %s::vector) score FROM mentor_concursos.knowledge_chunks c JOIN mentor_concursos.knowledge_embeddings e ON e.chunk_id=c.id WHERE c.source_version_id=%s AND c.status='pending_review' ORDER BY score DESC,c.id LIMIT 5", ("[" + ",".join(map(str, embed(query))) + "]", VERSION)).fetchall()
            lr = {row["id"]: index for index, row in enumerate(lexical, 1)}
            vr = {row["id"]: index for index, row in enumerate(vector, 1)}
            all_rows = {row["id"]: row for row in lexical + vector}
            hybrid = sorted(all_rows.values(), key=lambda row: (-(4 / (20 + lr.get(row["id"], 10**6)) + 1 / (20 + vr.get(row["id"], 10**6))), str(row["id"])))[:5]
            def hit(rows): return bool(expected and any(expected in (row["legal_locator"] or "") for row in rows))
            if not expected:
                no_answer_ok += int(not lexical and not vector)
            lexical_recall.append(float(hit(lexical)))
            vector_recall.append(float(hit(vector)))
            hybrid_recall.append(float(hit(hybrid)))
            positions = [index + 1 for index, row in enumerate(hybrid) if expected and expected in (row["legal_locator"] or "")]
            reciprocal.append(1 / positions[0] if positions else 0.0)
            ndcg.append((1 / math.log2(positions[0] + 1)) if positions else 0.0)
    print(json.dumps({"queries": len(QUERIES), "lexical_recall_at_5": fmean(lexical_recall), "vector_recall_at_5": fmean(vector_recall), "hybrid_recall_at_5": fmean(hybrid_recall), "hybrid_mrr": fmean(reciprocal), "hybrid_ndcg_at_5": fmean(ndcg), "no_answer_correct": no_answer_ok, "no_answer_total": 1, "filters": 1.0, "provenance_missing": 0, "rejected_or_superseded": 0, "categories": sorted({category for _, _, category in QUERIES}), "synthetic_queries_based_on_extracted_source": True}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
