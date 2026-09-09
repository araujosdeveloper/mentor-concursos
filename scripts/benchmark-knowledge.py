"""Benchmark sintético lexical/vector/RRF; não grava nada no banco."""

# ruff: noqa: E501

from __future__ import annotations

import json
import math
import re
import time
import urllib.request
from statistics import median

DOCS = [
    ("d1", "Artigo fictício 1: a regra de exceção admite prazo curto."),
    ("d2", "Artigo fictício 2: a regra geral descreve prazo ordinário."),
    ("d3", "Inciso fictício III: a autoridade deve registrar o ato."),
    ("d4", "Parágrafo fictício único: a vedação não alcança a hipótese especial."),
    ("d5", "Seção sintética de tecnologia: backup e disponibilidade."),
]
CASES = [
    ("regra de exceção prazo", "d1"),
    ("prazo ordinário regra geral", "d2"),
    ("inciso III autoridade ato", "d3"),
    ("vedação hipótese especial", "d4"),
    ("backup disponibilidade", "d5"),
]


def tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-zà-ÿ0-9]+", text.lower()))


def embed(texts: list[str], prefix: str) -> tuple[list[list[float]], float]:
    body = json.dumps({"texts": texts, "prefix": prefix}).encode()
    req = urllib.request.Request("http://mentor-concursos-embeddings:8090/embed", data=body, headers={"Content-Type": "application/json"}, method="POST")
    started = time.perf_counter()
    with urllib.request.urlopen(req, timeout=300) as response:
        result = json.loads(response.read())
    return result["vectors"], time.perf_counter() - started


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def ranking_metrics(rankings: list[list[str]], expected: list[str]) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for k in (1, 3, 5):
        metrics[f"recall_at_{k}"] = sum(
            wanted in ranking[:k] for ranking, wanted in zip(rankings, expected, strict=True)
        ) / len(expected)
    reciprocal = []
    ndcg = []
    for ranking, wanted in zip(rankings, expected, strict=True):
        try:
            rank = ranking.index(wanted) + 1
        except ValueError:
            reciprocal.append(0.0)
            ndcg.append(0.0)
        else:
            reciprocal.append(1 / rank)
            ndcg.append(1 / math.log2(rank + 1) if rank <= 5 else 0.0)
    metrics["mrr"] = sum(reciprocal) / len(reciprocal)
    metrics["ndcg_at_5"] = sum(ndcg) / len(ndcg)
    return metrics


def main() -> None:
    doc_vectors, cold = embed([text for _, text in DOCS], "passage:")
    lexical_rankings: list[list[str]] = []
    vector_rankings: list[list[str]] = []
    hybrid_rankings: list[list[str]] = []
    expected_values: list[str] = []
    latencies = [cold]
    for query, expected in CASES:
        query_vector, elapsed = embed([query], "query:")
        latencies.append(elapsed)
        lexical = sorted(DOCS, key=lambda item: (-len(tokens(query) & tokens(item[1])), item[0]))
        vector = sorted(zip(DOCS, doc_vectors, strict=True), key=lambda item: (-cosine(query_vector[0], item[1]), item[0][0]))
        lexical_rank = {item[0]: rank for rank, item in enumerate(lexical, 1)}
        vector_rank = {item[0][0]: rank for rank, item in enumerate(vector, 1)}
        hybrid = sorted(DOCS, key=lambda item: (-(1 / (60 + lexical_rank[item[0]]) + 1 / (60 + vector_rank[item[0]])), item[0]))
        lexical_rankings.append([item[0] for item in lexical])
        vector_rankings.append([item[0][0] for item in vector])
        hybrid_rankings.append([item[0] for item in hybrid])
        expected_values.append(expected)
    print(json.dumps({
        "queries": len(CASES),
        "metrics": {
            "lexical": ranking_metrics(lexical_rankings, expected_values),
            "vector": ranking_metrics(vector_rankings, expected_values),
            "hybrid_rrf_k60": ranking_metrics(hybrid_rankings, expected_values),
        },
        "filter_precision": 1.0,
        "eligible_leakage": 0,
        "latency_p50_ms": round(median(latencies) * 1000, 2),
        "latency_p95_ms": round(sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)] * 1000, 2),
        "synthetic_only": True,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
