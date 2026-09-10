"""Avaliação estratificada da recuperação da fonte piloto em quarentena."""

# ruff: noqa: E501
from __future__ import annotations

import hashlib
import json
import os
import re
import statistics
import urllib.request
from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg.rows import dict_row

VERSION = "1eccd249-b219-4d96-8e36-5dba1535159e"
MODEL = "intfloat/multilingual-e5-small"
REVISION = "fd1525a9fd15316a2d503bf26ab031a61d056e98"


@dataclass(frozen=True)
class Case:
    query: str
    expected: str | None
    kind: str


CASES = [
    Case("qual é a finalidade básica do processo administrativo", "Art. 1º", "literal"), Case("princípios que a Administração deve observar", "Art. 2º", "literal"), Case("garantias do administrado perante a Administração", "Art. 3º", "paraphrase"), Case("quem pode iniciar o processo administrativo", "Art. 5º", "competence"), Case("requisitos da comunicação dos atos", "Art. 26", "literal"), Case("prazo para decidir depois de concluída a instrução", "Art. 49", "deadline"), Case("a Administração tem dever de decidir", "Art. 48", "paraphrase"), Case("impedimento da autoridade ou servidor", "Art. 18", "literal"), Case("suspeição por amizade íntima ou inimizade", "Art. 20", "literal"), Case("interessados têm direito à vista dos autos", "Art. 3º", "literal"), Case("dever de expor os fatos conforme a verdade", "Art. 4º", "literal"), Case("instrução que não envolva os interessados", "Art. 29", "paraphrase"), Case("provas ilícitas são inadmissíveis", "Art. 30", "negation"), Case("ônus da prova cabe ao interessado", "Art. 36", "literal"), Case("consulta e audiência pública", "Art. 31", "literal"), Case("parecer obrigatório e vinculante", "Art. 42", "literal"), Case("desistência do processo pelo interessado", "Art. 51", "literal"), Case("não prejudica o prosseguimento se houver interesse público", "Art. 51", "exception"), Case("anulação de atos administrativos ilegais", "Art. 53", "literal"), Case("revogação por conveniência ou oportunidade", "Art. 53", "literal"), Case("decisão coordenada entre órgãos", "Art. 49-A", "literal"), Case("participação de autoridades na decisão coordenada", "Art. 49-B", "literal"), Case("conclusão da decisão coordenada", "Art. 49-G", "literal"), Case("recurso administrativo independe de caução", "Art. 56", "negation"), Case("prazo para interpor recurso administrativo", "Art. 59", "deadline"), Case("efeito suspensivo do recurso", "Art. 61", "exception"), Case("revisão de processo sancionador", "Art. 65", "literal"), Case("proibição de agravamento na revisão", "Art. 65", "negation"), Case("prazo para anular atos favoráveis", "Art. 54", "deadline"), Case("aplicação subsidiária aos processos específicos", "Art. 69", "literal"), Case("órgão competente para editar atos normativos", "Art. 69-A", "competence"), Case("artigo 2º inciso primeiro", "Art. 2º", "article"), Case("artigo 49-A parágrafo único", "Art. 49-A", "article"), Case("inciso II do artigo 3º", "Art. 3º", "article"), Case("teletransporte administrativo interestelar", None, "no_answer"), Case("recurso espacial quântico sem previsão", None, "no_answer"), Case("licença para dragões voadores", None, "no_answer"), Case("competência de uma entidade inexistente", None, "no_answer"), Case("prazo de 9999 dias para uma audiência", None, "no_answer"),
]


def connect() -> psycopg.Connection:
    return psycopg.connect(host=os.environ["DATABASE_HOST"], port=int(os.getenv("DATABASE_PORT", "5432")), dbname=os.environ["DATABASE_NAME"], user=os.environ["DATABASE_USER"], password=os.environ["DATABASE_PASSWORD"], row_factory=dict_row)


def embed(query: str) -> list[float]:
    req = urllib.request.Request("http://mentor-concursos-embeddings:8090/embed", data=json.dumps({"texts": [f"query: {query}"], "prefix": "query:"}).encode(), headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read())["vectors"][0]


def explicit_locator(query: str) -> str | None:
    match = re.search(r"\bart(?:igo)?\.?\s*(\d+[ºo]?(?:\s*-\s*[A-Za-z])?)\b", query, re.I)
    return f"Art. {match.group(1).strip()}" if match else None


def fetch(cur: psycopg.Cursor[Any], case: Case, depth: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    lexical = cur.execute("""SELECT c.id,c.legal_locator,c.content_sha256,s.id source_id,v.id source_version_id,ts_rank_cd(c.search_vector, websearch_to_tsquery('portuguese', replace(%s, ' ', ' OR '))) score FROM mentor_concursos.knowledge_chunks c JOIN mentor_concursos.knowledge_source_versions v ON v.id=c.source_version_id JOIN mentor_concursos.knowledge_sources s ON s.id=v.source_id WHERE c.source_version_id=%s AND c.status='pending_review' AND v.status='pending_review' AND c.search_vector @@ websearch_to_tsquery('portuguese', replace(%s, ' ', ' OR ')) ORDER BY CASE WHEN regexp_replace(c.legal_locator, '\\.$', '')=%s THEN 0 ELSE 1 END,score DESC,c.id LIMIT %s""", (case.query, VERSION, case.query, explicit_locator(case.query) or "", depth)).fetchall()
    vector = cur.execute("""SELECT c.id,c.legal_locator,c.content_sha256,s.id source_id,v.id source_version_id,1-(e.embedding <=> %s::vector) score FROM mentor_concursos.knowledge_chunks c JOIN mentor_concursos.knowledge_source_versions v ON v.id=c.source_version_id JOIN mentor_concursos.knowledge_sources s ON s.id=v.source_id JOIN mentor_concursos.knowledge_embeddings e ON e.chunk_id=c.id WHERE c.source_version_id=%s AND c.status='pending_review' AND v.status='pending_review' ORDER BY score DESC,c.id LIMIT %s""", ("[" + ",".join(str(float(x)) for x in embed(case.query)) + "]", VERSION, depth)).fetchall()
    return [dict(row) for row in lexical], [dict(row) for row in vector]


def fuse(lexical: list[dict[str, Any]], vector: list[dict[str, Any]], weight: float, k: int, limit: int = 10) -> list[dict[str, Any]]:
    merged: dict[Any, dict[str, Any]] = {}
    for rank, row in enumerate(lexical, 1):
        item = merged.setdefault(row["id"], dict(row))
        item["lexical_rank"] = rank
        item["lexical_score"] = float(row["score"])
    for rank, row in enumerate(vector, 1):
        item = merged.setdefault(row["id"], dict(row))
        item["vector_rank"] = rank
        item["vector_score"] = float(row["score"])
    for item in merged.values():
        item["rrf_score"] = weight / (k + item.get("lexical_rank", 10000)) + 1 / (k + item.get("vector_rank", 10000))
    return sorted(merged.values(), key=lambda x: (-x["rrf_score"], str(x["id"])))[:limit]


def metrics(results: list[list[dict[str, Any]]], cases: list[Case], threshold: float | None = None) -> dict[str, Any]:
    rr: list[float] = []
    recall = {1: [], 3: [], 5: []}
    ndcg: list[float] = []
    no_answer_ok = 0
    for rows, case in zip(results, cases, strict=True):
        locators = [row["legal_locator"].rstrip(".") for row in rows]
        expected = case.expected.rstrip(".") if case.expected else None
        if expected is None:
            if threshold is not None and (not rows or rows[0]["rrf_score"] < threshold):
                no_answer_ok += 1
            continue
        first = next((pos + 1 for pos, locator in enumerate(locators) if locator == expected), None)
        rr.append(1 / first if first else 0.0)
        for k in recall:
            recall[k].append(float(expected in locators[:k]))
        gains = [3 if locator == expected else 0 for locator in locators[:5]]
        dcg = sum(g / __import__("math").log2(pos + 2) for pos, g in enumerate(gains))
        ndcg.append(dcg / 3 if dcg else 0.0)
    return {"answerable": sum(c.expected is not None for c in cases), "recall": {f"@{k}": round(statistics.mean(values), 4) if values else 0 for k, values in recall.items()}, "mrr": round(statistics.mean(rr), 4) if rr else 0, "ndcg5": round(statistics.mean(ndcg), 4) if ndcg else 0, "no_answer_correct": no_answer_ok, "no_answer_total": sum(c.expected is None for c in cases)}


def main() -> None:
    calibration = [case for i, case in enumerate(CASES) if i % 2 == 0]
    validation = [case for i, case in enumerate(CASES) if i % 2 == 1]
    configs = [(w, k) for w in (1.0, 2.0, 3.0, 4.0, 5.0) for k in (20, 40, 60, 80)]
    cache: dict[str, tuple[list[dict[str, Any]], list[dict[str, Any]]]] = {}
    with connect() as conn, conn.cursor() as cur:
        for case in CASES:
            cache[case.query] = fetch(cur, case, 20)
        best = None
        config_scores = []
        for weight, k in configs:
            rows = [fuse(*cache[case.query], weight, k) for case in calibration]
            metric = metrics(rows, calibration)
            score = (metric["ndcg5"], metric["mrr"], metric["recall"]["@5"])
            config_scores.append({"weight": weight, "k": k, "metrics": metric})
            if best is None or score > best[0]:
                best = (score, weight, k)
        assert best is not None
        _, weight, k = best
        cal_rows = [fuse(*cache[case.query], weight, k) for case in calibration]
        val_rows = [fuse(*cache[case.query], weight, k) for case in validation]
        threshold = min((rows[0]["rrf_score"] for rows, case in zip(cal_rows, calibration, strict=True) if case.expected), default=0.0) * 0.5
        all_rows = [fuse(*cache[case.query], weight, k) for case in CASES]
        output = {"model": MODEL, "revision": REVISION, "cases": len(CASES), "calibration": {"cases": len(calibration), "selected": {"lexical_weight": weight, "rrf_k": k, "no_answer_threshold": threshold}, "metrics": metrics(cal_rows, calibration, threshold), "config_scores": sorted(config_scores, key=lambda x: (x["metrics"]["ndcg5"], x["metrics"]["mrr"]), reverse=True)[:8]}, "validation": {"cases": len(validation), "metrics": metrics(val_rows, validation, threshold)}, "all_metrics": metrics(all_rows, CASES, threshold), "queries": [{"query_sha256": hashlib.sha256(case.query.encode()).hexdigest(), "kind": case.kind, "expected": case.expected, "top10": [{"locator": row["legal_locator"], "chunk_id": str(row["id"]), "rrf_score": round(row["rrf_score"], 8), "lexical_score": round(row.get("lexical_score", 0), 6), "vector_score": round(row.get("vector_score", 0), 6), "lexical_rank": row.get("lexical_rank"), "vector_rank": row.get("vector_rank")} for row in rows[:10]]} for case, rows in zip(CASES, all_rows, strict=True)]}
        print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
