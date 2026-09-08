"""
Similar Projects (RAG). For a thread's extracted equipment item, finds the
most relevant past projects of the same equipment type:

  1. Embed the item's spec text locally (BGE-M3, no API key).
  2. Vector search that equipment type's Qdrant collection for the top N
     candidates (fast, cheap, approximate).
  3. Send the item + those candidates to Claude for field-by-field
     reranking — a refined 0-100 relevance score + justification each.
  4. Sort by the refined score, return the top K.

Each equipment type (SO2, CL2, ...) has its own fully separate Qdrant
collection — see rag_vector_store.py.
"""

import json
from pathlib import Path

from . import rag_embedder, rag_reranker, rag_text_representation
from .config import settings
from .rag_vector_store import VectorStore
from .template_consolidation import get_template_fields


def _flatten_fields(fields: dict) -> dict:
    """Our stored shape is {key: {label, value, status, source}} — the RAG
    text representation (shared with the historical project files) wants the
    simpler {key: value_or_None} shape."""
    return {key: entry.get("value") for key, entry in (fields or {}).items()}


def find_similar_projects(equipment_item: dict, top_k: int = 10, candidates: int = 20) -> dict:
    type_label = equipment_item.get("type_label")
    equipment_name = equipment_item.get("equipment_name", "")

    field_defs, _ = get_template_fields(equipment_name)
    field_labels = dict(field_defs) if field_defs else {}

    new_project_text = rag_text_representation.build_source_text(
        {"fields": _flatten_fields(equipment_item.get("fields")), "key_points": []},
        field_labels,
    )

    query_vector = rag_embedder.embed_text(new_project_text)

    store = VectorStore(settings.rag_index_dir, vector_dim=rag_embedder.EMBEDDING_DIM)
    shortlist = store.search(type_label, query_vector, limit=candidates)

    if not shortlist:
        return {
            "equipment_type": type_label,
            "total_candidates_considered": 0,
            "results": [],
            "message": f"No indexed history for equipment type '{type_label}' yet.",
        }

    candidates_for_rerank = [
        {"project_id": c["project_id"], "source_text": c["payload"].get("source_text", "")}
        for c in shortlist
    ]
    reranked = rag_reranker.rerank_candidates(new_project_text, candidates_for_rerank)

    vector_score_by_id = {c["project_id"]: c["score"] for c in shortlist}
    payload_by_id = {c["project_id"]: c["payload"] for c in shortlist}

    results = []
    for r in reranked:
        pid = r.get("project_id")
        payload = payload_by_id.get(pid, {})
        raw_fields = payload.get("fields", {})
        results.append({
            "project_id": pid,
            "relevance_score": r.get("relevance_score"),
            "justification": r.get("justification"),
            "vector_similarity": round(vector_score_by_id.get(pid, 0.0), 4),
            "fields": {
                key: {"label": field_labels.get(key, key), "value": value}
                for key, value in raw_fields.items()
                if value is not None
            },
            "key_points": payload.get("key_points", []),
            "source_text": payload.get("source_text", ""),
            "customer_details": payload.get("customer_details"),
            "boq": payload.get("boq", []),
        })

    results.sort(key=lambda r: r.get("relevance_score") or 0, reverse=True)

    return {
        "equipment_type": type_label,
        "total_candidates_considered": len(shortlist),
        "results": results[:top_k],
    }


def save_similar_projects_result(thread_id, equipment_index: int, result: dict) -> str:
    out_dir = Path(settings.similar_projects_storage_dir) / str(thread_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{equipment_index}_{result.get('equipment_type') or 'unknown'}.json"
    out_path.write_text(json.dumps(result, indent=2))
    return str(out_path)
