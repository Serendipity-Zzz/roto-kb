from __future__ import annotations

import math
import hashlib
import uuid
from pathlib import Path


class InMemoryVectorIndex:
    def __init__(self, dimension: int): self.dimension, self.points = dimension, {}
    def upsert(self, items):
        for point_id, vector, payload in items:
            if len(vector) != self.dimension: raise ValueError("vector dimension mismatch")
            self.points[point_id] = (vector, payload)
    def search(self, vector, top_k=20, allowed_ids=None):
        if len(vector) != self.dimension: raise ValueError("vector dimension mismatch")
        def cosine(a,b):
            den = math.sqrt(sum(x*x for x in a))*math.sqrt(sum(x*x for x in b)) or 1
            return sum(x*y for x,y in zip(a,b))/den
        rows=[(pid,cosine(vector,v),p) for pid,(v,p) in self.points.items() if allowed_ids is None or pid in allowed_ids]
        return sorted(rows,key=lambda x:(-x[1],x[0]))[:top_k]


class QdrantReleaseAdapter(InMemoryVectorIndex):
    """Safe local adapter; a production Qdrant adapter can implement this port."""
    prefix = "roto_kb_"
    def __init__(self, dimension: int, release_id: str):
        if not release_id or release_id == "rel_empty": raise ValueError("real release id required")
        if not release_id.startswith("rel_"): raise ValueError("invalid release id")
        self.collection = self.prefix + release_id
        super().__init__(dimension)


class EmbeddedQdrantIndex:
    """Local embedded Qdrant persisted under the configured data root.

    Default production mode for this deployment: no Docker port, no public exposure.
    """
    def __init__(self, dimension: int, release_id: str, storage_path: str | Path, *, recreate: bool = True):
        try:
            from qdrant_client import QdrantClient, models
        except ImportError as exc:
            raise RuntimeError("qdrant-client is required for embedded mode") from exc
        if not release_id.startswith("rel_") or release_id == "rel_empty":
            raise ValueError("invalid release id")
        self.dimension = dimension
        self.release_id = release_id
        self.collection = "roto_kb_" + release_id
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._models = models
        self.client = QdrantClient(path=str(self.storage_path))
        exists = self.client.collection_exists(self.collection)
        if recreate or not exists:
            if exists:
                self.client.delete_collection(self.collection)
            self.client.create_collection(
                self.collection,
                vectors_config=models.VectorParams(size=dimension, distance=models.Distance.COSINE),
            )
        else:
            info = self.client.get_collection(self.collection)
            size = info.config.params.vectors.size
            if size != dimension:
                raise ValueError(f"embedded collection dimension {size} != configured {dimension}")

    @staticmethod
    def _point_id(chunk_id: str) -> str:
        return str(uuid.UUID(hashlib.md5(chunk_id.encode("utf-8"), usedforsecurity=False).hexdigest()))

    def upsert(self, items):
        points = []
        for point_id, vector, payload in items:
            if len(vector) != self.dimension: raise ValueError("vector dimension mismatch")
            payload = dict(payload); payload["chunk_id"] = point_id
            points.append(self._models.PointStruct(id=self._point_id(point_id), vector=vector, payload=payload))
        for start in range(0, len(points), 256):
            self.client.upsert(self.collection, points=points[start:start + 256], wait=True)

    def search(self, vector, top_k=20, allowed_ids=None):
        if len(vector) != self.dimension: raise ValueError("vector dimension mismatch")
        result = self.client.query_points(self.collection, query=vector, limit=top_k, with_payload=True).points
        rows = [(p.payload.get("chunk_id", str(p.id)), p.score, p.payload) for p in result]
        if allowed_ids is not None: rows = [r for r in rows if r[0] in allowed_ids]
        return rows

    def close(self):
        self.client.close()
