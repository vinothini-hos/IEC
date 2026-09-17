"""
Thin wrapper around a local (on-disk, no server) Qdrant instance. Maintains
one collection per equipment type (e.g. "so2_projects", "cl2_projects"), so
each equipment type's RAG index is fully separate.
"""

import hashlib

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct


def collection_name_for(equipment_type: str, suffix: str = "") -> str:
    """suffix lets a caller keep a separate pool of points for the same
    equipment type in its own collection — e.g. suffix="sample" gives
    "so2_projects_sample", isolated from the real "so2_projects" history
    that rag_service.py's live Similar Projects search queries."""
    name = f"{equipment_type.strip().lower()}_projects"
    return f"{name}_{suffix}" if suffix else name


def stable_id(project_id: str) -> int:
    """Derive a stable integer point ID from a project's filename/identifier
    so re-indexing the same file updates (rather than duplicates) its point."""
    digest = hashlib.sha256(project_id.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


class VectorStore:
    def __init__(self, storage_path: str, vector_dim: int):
        self.client = QdrantClient(path=storage_path)
        self.vector_dim = vector_dim

    def ensure_collection(self, equipment_type: str, suffix: str = ""):
        name = collection_name_for(equipment_type, suffix)
        if not self.client.collection_exists(name):
            self.client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=self.vector_dim, distance=Distance.COSINE),
            )
        return name

    def upsert_project(
        self, equipment_type: str, project_id: str, vector: list, payload: dict, suffix: str = ""
    ):
        collection = self.ensure_collection(equipment_type, suffix)
        point_id = stable_id(project_id)
        full_payload = {"project_id": project_id, **payload}
        self.client.upsert(
            collection_name=collection,
            points=[PointStruct(id=point_id, vector=vector, payload=full_payload)],
        )

    def search(self, equipment_type: str, query_vector: list, limit: int = 20, suffix: str = "") -> list:
        collection = collection_name_for(equipment_type, suffix)
        if not self.client.collection_exists(collection):
            return []

        results = self.client.query_points(
            collection_name=collection,
            query=query_vector,
            limit=limit,
        ).points

        return [
            {"project_id": r.payload.get("project_id"), "score": r.score, "payload": r.payload}
            for r in results
        ]

    def count(self, equipment_type: str, suffix: str = "") -> int:
        collection = collection_name_for(equipment_type, suffix)
        if not self.client.collection_exists(collection):
            return 0
        return self.client.count(collection_name=collection).count

    def get_all_payloads(self, equipment_type: str, suffix: str = "") -> list:
        """Fetches every point's payload for this equipment type — used to
        build the BM25 corpus, which (unlike the dense search) needs the
        full historical pool rather than just a top-K shortlist."""
        collection = collection_name_for(equipment_type, suffix)
        if not self.client.collection_exists(collection):
            return []

        all_payloads = []
        offset = None
        while True:
            records, offset = self.client.scroll(
                collection_name=collection, limit=200, offset=offset,
                with_payload=True, with_vectors=False,
            )
            all_payloads.extend(r.payload for r in records)
            if offset is None:
                break
        return all_payloads
