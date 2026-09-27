from __future__ import annotations

from typing import Protocol, Sequence

from .models import EvidencePackage


class EmbeddingProvider(Protocol):
    model: str
    def probe(self) -> int: ...
    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


class RagService(Protocol):
    def retrieve(self, query: str, *, filters: dict | None = None, top_k: int = 6) -> EvidencePackage: ...
    def fetch(self, doc_id: str, *, chapter: str | None = None): ...
