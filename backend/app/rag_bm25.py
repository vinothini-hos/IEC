"""
Keyword-ranking half of Similar Projects retrieval — complements the dense
(embedding) search in rag_vector_store.py by finding historical projects
that share literal terms (e.g. "SO2", "steam", "FLP") with the new project,
which cosine similarity on embeddings alone can under-weight.

The historical pool per equipment type is small (tens to low hundreds of
projects), so the BM25 index is just rebuilt in memory on every call from
whatever payloads are currently in Qdrant — no separate on-disk index to
keep in sync.
"""

import re

from rank_bm25 import BM25Okapi

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list:
    return _TOKEN_RE.findall((text or "").lower())


def rank(query_text: str, documents: list) -> list:
    """documents: list of {"project_id", "source_text"}.
    Returns the same project_ids ordered by BM25 score, most relevant
    first — [{"project_id", "bm25_score"}, ...]."""
    if not documents:
        return []

    corpus_tokens = [_tokenize(doc["source_text"]) for doc in documents]
    bm25 = BM25Okapi(corpus_tokens)
    scores = bm25.get_scores(_tokenize(query_text))

    ranked = sorted(
        ({"project_id": doc["project_id"], "bm25_score": float(score)}
         for doc, score in zip(documents, scores)),
        key=lambda d: d["bm25_score"],
        reverse=True,
    )
    return ranked
