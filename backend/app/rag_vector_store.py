"""
Thin wrapper around a local (on-disk, no server) Qdrant instance. Maintains
one collection per equipment type (e.g. "so2_projects", "cl2_projects"), so
each equipment type's RAG index is fully separate.
"""

import hashlib

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct


def collection_name_for(equipment_type: str) -> str:
    return f"{equipment_type.strip().lower()}_projects"


def stable_id(project_id: str) -> int:
    """Derive a stable integer point ID from a project's filename/identifier
    so re-indexing the same file updates (rather than duplicates) its point."""
    digest = hashlib.sha256(project_id.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


class VectorStore:
    def __init__(self, storage_path: str, vector_dim: int):
        self.client = QdrantClient(path=storage_path)
        self.vector_dim = vector_dim

    def ensure_collection(self, equipment_type: str):
        name = collection_name_for(equipment_type)
        if not self.client.collection_exists(name):
            self.client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=self.vector_dim, distance=Distance.COSINE),
            )
        return name

    def upsert_project(self, equipment_type: str, project_id: str, vector: list, payload: dict):
        collection = self.ensure_collection(equipment_type)
        point_id = stable_id(project_id)
        full_payload = {"project_id": project_id, **payload}
        self.client.upsert(
            collection_name=collection,
            points=[PointStruct(id=point_id, vector=vector, payload=full_payload)],
        )

    def search(self, equipment_type: str, query_vector: list, limit: int = 20) -> list:
        collection = collection_name_for(equipment_type)
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

    def count(self, equipment_type: str) -> int:
        collection = collection_name_for(equipment_type)
        if not self.client.collection_exists(collection):
            return 0
        return self.client.count(collection_name=collection).count
