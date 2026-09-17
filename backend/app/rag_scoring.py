"""
Pure scoring math for Similar Projects ranking — kept separate from
retrieval (rag_vector_store.py, rag_bm25.py) and business logic
(rag_field_match.py) so it's easy to reason about and test in isolation.
"""

import math


def reciprocal_rank_fusion(rankings: list, k: int = 60) -> dict:
    """rankings: list of ranked project_id lists (best first), one per
    retrieval method (dense, BM25, ...). Returns {project_id: rrf_score},
    higher is better. A project absent from a given ranking simply doesn't
    contribute a term for that ranking — it isn't penalized beyond that."""
    scores = {}
    for ranking in rankings:
        for rank, project_id in enumerate(ranking, start=1):
            scores[project_id] = scores.get(project_id, 0.0) + 1.0 / (k + rank)
    return scores


def normalize(scores: dict) -> dict:
    """Min-max normalize to [0,1]. If every value is equal (including the
    single-value or empty case), returns 1.0 for all — there's no signal to
    distinguish them, so treat them as equally strong rather than zeroing
    them out."""
    if not scores:
        return {}
    values = scores.values()
    lo, hi = min(values), max(values)
    if hi == lo:
        return {key: 1.0 for key in scores}
    return {key: (value - lo) / (hi - lo) for key, value in scores.items()}


def geometric_mean(a: float, b: float) -> float:
    return math.sqrt(max(a, 0.0) * max(b, 0.0))
