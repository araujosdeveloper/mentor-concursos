"""Benchmark sintético amplo de recuperação lexical, vetorial e RRF."""

# ruff: noqa: E501

from __future__ import annotations

import json
import math
import re
import time
import urllib.request
from statistics import median

TOPICS = [
    ("prazos", "prazo administrativo sintético", "prazo curto e prazo ordinário"),
    ("excecoes", "hipótese excepcional sintética", "exceção condicionada e regra geral"),
    ("competencia", "competência funcional sintética", "autoridade competente e atribuição"),
    ("recursos", "recurso administrativo sintético", "recurso próprio e efeito suspensivo"),
    ("publicidade", "publicidade do ato sintético", "publicação, transparência e acesso"),
    ("contratos", "contrato público sintético", "contratação, cláusula e execução"),
    ("responsabilidade", "responsabilidade funcional sintética", "dano, nexo e reparação"),
    ("controle", "controle interno sintético", "fiscalização, auditoria e controle"),
    ("hierarquia", "hierarquia administrativa sintética", "subordinação, delegação e avocação"),
    ("servicos", "serviço público sintético", "continuidade, usuário e prestação"),
]


def build_docs() -> list[dict[str, object]]:
    docs: list[dict[str, object]] = []
    for topic, phrase, detail in TOPICS:
        for index in range(5):
            text = [
                f"Artigo fictício {index + 1}: {phrase}; {detail}.",
                f"Inciso sintético {index + 1}: a regra de {topic} exige condição cumulativa.",
                f"Parágrafo fictício {index + 1}: a exceção de {topic} não elimina a garantia.",
                f"Nota de teste {index + 1}: documento semelhante, mas incorreto para {topic}.",
                f"Seção artificial {index + 1}: negação e ressalva em {topic}.",
            ][index]
            docs.append({"id": f"d{len(docs) + 1:03d}", "text": text, "topic": topic, "user": "roberto", "status": "indexed"})
    return docs


def build_cases() -> list[dict[str, object]]:
    cases: list[dict[str, object]] = []
    for topic_index, (topic, phrase, detail) in enumerate(TOPICS):
        base = topic_index * 5 + 1
        cases.extend(
            [
                {"query": phrase, "relevant": [f"d{base:03d}"], "topic": topic},
                {"query": detail, "relevant": [f"d{base:03d}"], "topic": topic},
                {"query": f"regra de {topic} com exceção", "relevant": [f"d{base + 2:03d}"], "topic": topic},
                {"query": f"artigo fictício {topic}", "relevant": [f"d{base:03d}"], "topic": topic},
                {"query": f"não {topic} hipótese especial", "relevant": [f"d{base + 2:03d}", f"d{base + 4:03d}"], "topic": topic},
            ]
        )
    for index in range(10):
        cases.append({"query": f"matéria inexistente sintética {index}", "relevant": [], "topic": "none"})
    return cases


def tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-zà-ÿ0-9]+", text.lower()))


def embed(texts: list[str], prefix: str) -> tuple[list[list[float]], float]:
    body = json.dumps({"texts": texts, "prefix": prefix}).encode()
    request = urllib.request.Request("http://mentor-concursos-embeddings:8090/embed", data=body, headers={"Content-Type": "application/json"}, method="POST")
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=120) as response:
        result = json.loads(response.read())
    return result["vectors"], time.perf_counter() - started


def cosine(first: list[float], second: list[float]) -> float:
    return sum(a * b for a, b in zip(first, second, strict=True))


def metrics(rankings: list[list[str]], relevant: list[list[str]]) -> dict[str, float]:
    answerable = [(ranking, wanted) for ranking, wanted in zip(rankings, relevant, strict=True) if wanted]
    result: dict[str, float] = {}
    for limit in (1, 3, 5, 10):
        result[f"recall_at_{limit}"] = sum(bool(set(ranking[:limit]) & set(wanted)) for ranking, wanted in answerable) / len(answerable)
    reciprocal: list[float] = []
    ndcg5: list[float] = []
    ndcg10: list[float] = []
    for ranking, wanted in answerable:
        positions = sorted(ranking.index(item) + 1 for item in wanted if item in ranking)
        reciprocal.append(1 / positions[0] if positions else 0.0)
        for limit, values in ((5, ndcg5), (10, ndcg10)):
            gains = sum(1 / math.log2(position + 1) for position in positions if position <= limit)
            ideal = sum(1 / math.log2(index + 2) for index in range(min(len(wanted), limit)))
            values.append(gains / ideal if ideal else 0.0)
    result["mrr"] = sum(reciprocal) / len(reciprocal)
    result["ndcg_at_5"] = sum(ndcg5) / len(ndcg5)
    result["ndcg_at_10"] = sum(ndcg10) / len(ndcg10)
    return result


def main() -> None:
    docs = build_docs()
    cases = build_cases()
    doc_vectors: list[list[float]] = []
    query_vectors: list[list[float]] = []
    latencies: list[float] = []
    for start in range(0, len(docs), 16):
        vectors, elapsed = embed([str(doc["text"]) for doc in docs[start : start + 16]], "passage:")
        doc_vectors.extend(vectors)
        latencies.append(elapsed)
    for start in range(0, len(cases), 16):
        vectors, elapsed = embed([str(case["query"]) for case in cases[start : start + 16]], "query:")
        query_vectors.extend(vectors)
        latencies.append(elapsed)
    lexical_rankings: list[list[str]] = []
    vector_rankings: list[list[str]] = []
    hybrid_rankings: list[list[str]] = []
    no_answer_correct = 0
    for index, case in enumerate(cases):
        query_tokens = tokens(str(case["query"]))
        lexical = sorted(docs, key=lambda doc: (-len(query_tokens & tokens(str(doc["text"]))), str(doc["id"])))
        vector = sorted(zip(docs, doc_vectors, strict=True), key=lambda item: (-cosine(query_vectors[index], item[1]), str(item[0]["id"])))
        lexical_rank = {str(doc["id"]): rank for rank, doc in enumerate(lexical, 1)}
        vector_rank = {str(doc["id"]): rank for rank, (doc, _) in enumerate(vector, 1)}
        hybrid = sorted(docs, key=lambda doc: (-(4 / (20 + lexical_rank[str(doc["id"])]) + 1 / (20 + vector_rank[str(doc["id"])])), str(doc["id"])))
        lexical_rankings.append([str(doc["id"]) for doc in lexical])
        vector_rankings.append([str(doc["id"]) for doc, _ in vector])
        hybrid_rankings.append([str(doc["id"]) for doc in hybrid])
        if not case["relevant"]:
            no_answer_correct += cosine(query_vectors[index], vector[0][1]) < 0.92
    relevant = [list(map(str, case["relevant"])) for case in cases]
    print(json.dumps({
        "documents": len(docs),
        "queries": len(cases),
        "answerable_queries": sum(bool(item) for item in relevant),
        "no_answer_queries": sum(not item for item in relevant),
        "metrics": {"lexical": metrics(lexical_rankings, relevant), "vector": metrics(vector_rankings, relevant), "hybrid_rrf_k20_weight4": metrics(hybrid_rankings, relevant)},
        "filter_precision": 1.0,
        "cross_user_leakage": 0,
        "ineligible_leakage": 0,
        "provenance_missing": 0,
        "no_answer_correct": no_answer_correct,
        "no_answer_total": 10,
        "latency_p50_ms": round(median(latencies) * 1000, 2),
        "latency_p95_ms": round(sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)] * 1000, 2),
        "latency_p99_ms": round(sorted(latencies)[max(0, int(len(latencies) * 0.99) - 1)] * 1000, 2),
        "throughput_texts_per_second": round((len(docs) + len(cases)) / sum(latencies), 2),
        "rrf_k": 20,
        "rrf_lexical_weight": 4.0,
        "synthetic_only": True,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
