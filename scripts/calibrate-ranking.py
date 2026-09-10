"""Deterministic calibration and independent validation for synthetic retrieval."""

# ruff: noqa: E501

from __future__ import annotations

import importlib.util
import json
import math
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("benchmark_knowledge", ROOT / "scripts/benchmark-knowledge.py")
_benchmark = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(_benchmark)
build_cases, build_docs = _benchmark.build_cases, _benchmark.build_docs
cosine, embed, tokens = _benchmark.cosine, _benchmark.embed, _benchmark.tokens


def ndcg(ranking: list[str], wanted: list[str], limit: int = 5) -> float:
    positions = {item: index + 1 for index, item in enumerate(ranking)}
    gain = sum(1 / math.log2(positions[item] + 1) for item in wanted if item in positions and positions[item] <= limit)
    ideal = sum(1 / math.log2(index + 2) for index in range(min(len(wanted), limit)))
    return gain / ideal if ideal else 0.0


def score(rankings: list[list[str]], cases: list[dict[str, object]]) -> dict[str, float]:
    answerable = [(ranking, list(map(str, case["relevant"]))) for ranking, case in zip(rankings, cases, strict=True) if case["relevant"]]
    recalls = {limit: sum(bool(set(ranking[:limit]) & set(wanted)) for ranking, wanted in answerable) / len(answerable) for limit in (1, 3, 5)}
    reciprocal = [1 / (ranking.index(wanted[0]) + 1) if wanted[0] in ranking else 0.0 for ranking, wanted in answerable]
    return {"recall_at_5": recalls[5], "mrr": statistics.fmean(reciprocal), "ndcg_at_5": statistics.fmean(ndcg(ranking, wanted) for ranking, wanted in answerable)}


def bootstrap(values: list[float], seed: int = 20260910, iterations: int = 4000) -> tuple[float, float]:
    import random

    rng = random.Random(seed)
    samples = sorted(statistics.fmean(rng.choice(values) for _ in values) for _ in range(iterations))
    return samples[int(iterations * 0.025)], samples[int(iterations * 0.975)]


def rankings(docs, cases, doc_vectors, query_vectors, lexical_depth, vector_depth, lexical_weight, vector_weight, rrf_k):
    output = []
    for index, case in enumerate(cases):
        query_tokens = tokens(str(case["query"]))
        lexical = sorted(docs, key=lambda doc: (-len(query_tokens & tokens(str(doc["text"]))), str(doc["id"])))[:lexical_depth]
        vector = sorted(zip(docs, doc_vectors, strict=True), key=lambda item: (-cosine(query_vectors[index], item[1]), str(item[0]["id"])))[:vector_depth]
        lexical_rank = {str(doc["id"]): rank for rank, doc in enumerate(lexical, 1)}
        vector_rank = {str(doc["id"]): rank for rank, (doc, _) in enumerate(vector, 1)}
        candidates = {str(doc["id"]): doc for doc in lexical + [item[0] for item in vector]}
        ordered = sorted(
            candidates.items(),
            key=lambda item: (
                -(lexical_weight / (rrf_k + lexical_rank.get(item[0], 10**6)) + vector_weight / (rrf_k + vector_rank.get(item[0], 10**6))),
                item[0],
            ),
        )
        output.append([doc_id for doc_id, _ in ordered])
    return output


def main() -> None:
    docs, cases = build_docs(), build_cases()
    # Stratified and frozen: alternating query forms per topic prevent a query
    # template from being exclusive to either split.
    calibration_indices = [topic * 5 + offset for topic in range(10) for offset in (0, 2, 4)] + list(range(50, 55))
    validation_indices = [topic * 5 + offset for topic in range(10) for offset in (1, 3)] + list(range(55, 60))
    doc_vectors = []
    query_vectors = []
    for start in range(0, len(docs), 16):
        doc_vectors.extend(embed([str(doc["text"]) for doc in docs[start : start + 16]], "passage:")[0])
    for start in range(0, len(cases), 16):
        query_vectors.extend(embed([str(case["query"]) for case in cases[start : start + 16]], "query:")[0])
    grid = []
    for lexical_weight in (1.0, 1.5, 2.0, 3.0, 4.0, 5.0):
        for vector_weight in (1.0,):
            for rrf_k in (20, 40, 60, 80):
                for lexical_depth in (10, 20, 50):
                    for vector_depth in (10, 20, 50):
                        ranking = rankings(docs, cases, doc_vectors, query_vectors, lexical_depth, vector_depth, lexical_weight, vector_weight, rrf_k)
                        cal_cases = [cases[i] for i in calibration_indices]
                        cal = score([ranking[i] for i in calibration_indices], cal_cases)
                        grid.append({"lexical_weight": lexical_weight, "vector_weight": vector_weight, "rrf_k": rrf_k, "lexical_depth": lexical_depth, "vector_depth": vector_depth, **cal})
    best = sorted(grid, key=lambda item: (-item["ndcg_at_5"], -item["mrr"], -item["recall_at_5"], item["lexical_depth"] + item["vector_depth"], item["rrf_k"]))[0]
    final_ranking = rankings(docs, cases, doc_vectors, query_vectors, best["lexical_depth"], best["vector_depth"], best["lexical_weight"], best["vector_weight"], best["rrf_k"])
    val_cases = [cases[i] for i in validation_indices]
    validation = score([final_ranking[i] for i in validation_indices], val_cases)
    answerable = [(final_ranking[i], list(map(str, cases[i]["relevant"]))) for i in validation_indices if cases[i]["relevant"]]
    ndcg_values = [ndcg(ranking, wanted) for ranking, wanted in answerable]
    reciprocal_values = [1 / (ranking.index(wanted[0]) + 1) if wanted[0] in ranking else 0.0 for ranking, wanted in answerable]
    failures = []
    for index in validation_indices:
        wanted = list(map(str, cases[index]["relevant"]))
        if wanted and not set(final_ranking[index][:5]).intersection(wanted):
            failures.append({"index": index, "topic": cases[index]["topic"], "query": cases[index]["query"], "relevant": wanted, "top5": final_ranking[index][:5]})
    print(json.dumps({"calibration_size": len(calibration_indices), "validation_size": len(validation_indices), "grid_size": len(grid), "selected": best, "validation": validation, "validation_failures": failures, "bootstrap_95": {"ndcg_at_5": bootstrap(ndcg_values), "mrr": bootstrap(reciprocal_values)}, "split": {"calibration_indices": calibration_indices, "validation_indices": validation_indices}}, sort_keys=True))


if __name__ == "__main__":
    main()
