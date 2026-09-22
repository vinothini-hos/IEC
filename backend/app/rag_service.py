"""
Similar Projects (RAG). For a thread's extracted equipment item, finds the
most relevant past projects of the same equipment type:

  1. Embed the item's spec text locally (BGE-M3, no API key).
  2. Retrieve two independent rankings of the historical pool:
       - Dense: Qdrant vector search (meaning-level similarity).
       - BM25: keyword search over the same corpus (term-level similarity,
         e.g. "SO2", "steam", "FLP" appearing in both).
  3. Fuse the two rankings with Reciprocal Rank Fusion (RRF).
  4. Score field-by-field similarity, weighted so capacity/heating/location
     matter more than exact temperature/pressure figures.
  5. Combine the (normalized) RRF score and field-match score via geometric
     mean into one final similarity score, and take the top K.
  6. Ask the local LLM to explain (not re-score) why each of those top K
     is a good match.

Each equipment type (SO2, CL2, ...) has its own fully separate Qdrant
collection — see rag_vector_store.py.
"""

import json
from datetime import datetime
from pathlib import Path

from . import rag_bm25, rag_embedder, rag_field_match, rag_justification, rag_scoring, rag_text_representation
from .config import settings
from .rag_vector_store import VectorStore
from .template_consolidation import get_template_fields


def _flatten_fields(fields: dict) -> dict:
    """Our stored shape is {key: {label, value, status, source}} — the RAG
    text representation (shared with the historical project files) wants the
    simpler {key: value_or_None} shape."""
    return {key: entry.get("value") for key, entry in (fields or {}).items()}


def find_similar_projects(equipment_item: dict, top_k: int = 10) -> dict:
    type_label = equipment_item.get("type_label")
    equipment_name = equipment_item.get("equipment_name", "")

    field_defs, _ = get_template_fields(equipment_name)
    field_labels = dict(field_defs) if field_defs else {}
    new_fields = _flatten_fields(equipment_item.get("fields"))

    new_project_text = rag_text_representation.build_source_text(
        {"fields": new_fields, "key_points": []},
        field_labels,
    )

    query_vector = rag_embedder.embed_text(new_project_text)

    index_dir = settings.rag_index_sample_dir if settings.rag_use_sample_index else settings.rag_index_dir
    store = VectorStore(index_dir, vector_dim=rag_embedder.EMBEDDING_DIM)

    all_payloads = store.get_all_payloads(type_label)
    if not all_payloads:
        return {
            "equipment_type": type_label,
            "total_candidates_considered": 0,
            "results": [],
            "message": f"No indexed history for equipment type '{type_label}' yet.",
        }
    payload_by_id = {p["project_id"]: p for p in all_payloads}

    # --- two independent rankings of the same historical pool ---
    dense_hits = store.search(type_label, query_vector, limit=settings.rag_dense_pool_size)
    dense_rank_list = [h["project_id"] for h in dense_hits]
    vector_score_by_id = {h["project_id"]: h["score"] for h in dense_hits}

    bm25_hits = rag_bm25.rank(
        new_project_text,
        [{"project_id": pid, "source_text": p.get("source_text", "")} for pid, p in payload_by_id.items()],
    )[: settings.rag_bm25_pool_size]
    bm25_rank_list = [h["project_id"] for h in bm25_hits]

    candidate_ids = set(dense_rank_list) | set(bm25_rank_list)
    dense_rank_by_id = {pid: i + 1 for i, pid in enumerate(dense_rank_list)}
    bm25_rank_by_id = {pid: i + 1 for i, pid in enumerate(bm25_rank_list)}

    # --- fuse rank position (RRF) and field-level similarity separately ---
    rrf_scores = rag_scoring.reciprocal_rank_fusion(
        [dense_rank_list, bm25_rank_list], k=settings.rag_rrf_k
    )
    field_match_scores = {
        pid: rag_field_match.field_match_score(new_fields, payload_by_id[pid].get("fields", {}))
        for pid in candidate_ids
    }

    rrf_norm = rag_scoring.normalize({pid: rrf_scores.get(pid, 0.0) for pid in candidate_ids})
    field_match_norm = rag_scoring.normalize(field_match_scores)
    final_scores = {
        pid: rag_scoring.geometric_mean(rrf_norm[pid], field_match_norm[pid]) for pid in candidate_ids
    }

    ranked_ids = sorted(candidate_ids, key=lambda pid: final_scores[pid], reverse=True)[:top_k]

    # --- LLM explains the already-decided top K, doesn't re-score them ---
    justifications = rag_justification.generate_justifications(
        new_project_text,
        [{"project_id": pid, "source_text": payload_by_id[pid].get("source_text", "")} for pid in ranked_ids],
    )

    results = []
    for pid in ranked_ids:
        payload = payload_by_id[pid]
        raw_fields = payload.get("fields", {})
        results.append({
            "project_id": pid,
            "relevance_score": round(final_scores[pid] * 100, 2),
            "justification": justifications.get(pid, ""),
            "vector_similarity": round(vector_score_by_id.get(pid, 0.0), 4),
            "dense_rank": dense_rank_by_id.get(pid),
            "bm25_rank": bm25_rank_by_id.get(pid),
            "rrf_score": round(rrf_scores.get(pid, 0.0), 6),
            "field_match_score": round(field_match_scores.get(pid, 0.0), 4),
            "final_score": round(final_scores[pid] * 100, 2),
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

    return {
        "equipment_type": type_label,
        "total_candidates_considered": len(candidate_ids),
        "results": results,
    }


def save_similar_projects_result(thread_id, equipment_index: int, result: dict) -> str:
    """Writes a new timestamped file per run (full history kept) rather than
    overwriting - see routers/specification.py's GET endpoint, which reads
    the most recently written file for this equipment_index back."""
    out_dir = Path(settings.similar_projects_storage_dir) / str(thread_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%d%m%Y_%H%M%S")
    prefix = f"{equipment_index}_{result.get('equipment_type') or 'unknown'}"
    out_path = out_dir / f"{prefix}-{timestamp}-{thread_id}.json"
    out_path.write_text(json.dumps(result, indent=2))
    return str(out_path)
