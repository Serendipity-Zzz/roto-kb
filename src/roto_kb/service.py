from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from .domain.models import ChunkRecord, DocumentDetail, DocumentRecord, EvidencePackage, IndexRelease
from .ingestion.chunker import chunk_document
from .ingestion.parsers import parse_path
from .ingestion.scanner import scan_sources
from .indexes.bm25 import BM25Index
from .indexes.qdrant import EmbeddedQdrantIndex, InMemoryVectorIndex
from .providers.embedding import FakeEmbeddingProvider
from .retrieval import HybridRetriever
from .release import ReleaseRegistry, ReleaseConflict


# Large ontology dumps stay available for offline graph compile; vector/BM25 indexing skips them by default.
DEFAULT_MAX_INDEX_CHARS = 200_000


class KnowledgeService:
    def __init__(self, source_path: str | Path | None = None, *, embedding=None, qdrant_mode: str = "memory", qdrant_path: str | Path = ".roto-kb/qdrant", data_path: str | Path | None = None):
        self.source_path = Path(source_path) if source_path else None
        self.embedding = embedding or FakeEmbeddingProvider()
        self.qdrant_mode, self.qdrant_path = qdrant_mode, Path(qdrant_path)
        self.data_path = Path(data_path) if data_path else None
        self.release = IndexRelease(release_id="rel_empty", status="empty")
        self.documents, self.chunks = {}, {}
        self.bm25 = BM25Index()
        self.vectors = None
        self.retriever = HybridRetriever(self.documents, self.chunks, self.bm25)
        self.registry = ReleaseRegistry()
        self.releases = {self.release.release_id: self.release}
        if self.data_path:
            self.load(self.data_path)

    @property
    def content_status(self): return "ready" if self.documents else "empty"

    def reload(self, *, mode: str = "incremental") -> IndexRelease:
        if not self.source_path or not self.source_path.exists(): return self.release
        docs, chunks = {}, {}
        allowed = self._manifest_paths(self.source_path)
        max_chars = int(os.getenv("ROTO_KB_MAX_INDEX_CHARS", str(DEFAULT_MAX_INDEX_CHARS)))
        for source in scan_sources(self.source_path, allowed_paths=allowed):
            doc = parse_path(source, Path(source.path))
            if len(doc.content) > max_chars:
                # Keep provenance in browse via a short stub; avoid embedding multi-MB ontology dumps.
                stub = doc.content[:2000] + "\n\n[truncated: source exceeds ROTO_KB_MAX_INDEX_CHARS for vector indexing]"
                doc = doc.model_copy(update={"content": stub, "metadata": {**doc.metadata, "indexed": "truncated", "original_chars": len(doc.content)}})
            docs[doc.document_id] = doc
            for chunk in chunk_document(doc):
                chunks[chunk.chunk_id] = chunk
        if not chunks:
            self.documents, self.chunks = docs, chunks; self.bm25 = BM25Index(); self.release = IndexRelease(release_id="rel_empty", status="empty"); return self.release
        release_id = "rel_" + hashlib.sha256("".join(sorted(chunks)).encode()).hexdigest()[:12]
        dimension = self.embedding.probe()
        self.close()
        if self.qdrant_mode == "embedded":
            vectors = EmbeddedQdrantIndex(dimension, release_id, self.qdrant_path / release_id, recreate=True)
        else:
            vectors = InMemoryVectorIndex(dimension)
        chunk_values = list(chunks.values())
        batch_size = int(getattr(self.embedding, "batch_size", 16))
        embeddings = []
        for start in range(0, len(chunk_values), batch_size):
            embeddings.extend(self.embedding.embed_documents([c.retrieval_text for c in chunk_values[start:start + batch_size]]))
        vectors.upsert((c.chunk_id, v, {"chunk_id": c.chunk_id, "content": c.content, "domain": c.domain}) for c,v in zip(chunk_values, embeddings))
        self.documents, self.chunks = docs, chunks; self.bm25 = BM25Index({c.chunk_id:c.retrieval_text for c in chunks.values()}); self.vectors = vectors
        self.release = IndexRelease(release_id=release_id,status="active",embedding_model=getattr(self.embedding,"model",None),embedding_dimension=vectors.dimension,chunk_count=len(chunks),document_count=len(docs),source_hashes=tuple(sorted({d.source_hash for d in docs.values()})))
        self.registry.active = release_id
        self.releases[release_id] = self.release
        self.retriever = HybridRetriever(self.documents,self.chunks,self.bm25,self.vectors,self.embedding)
        if self.data_path:
            self.persist(self.data_path)
        return self.release

    @staticmethod
    def _manifest_paths(root: Path) -> set[Path] | None:
        """Resolve manifest resources and graph allowlist; unlisted ontology files stay out."""
        manifest = root / "manifest.yaml"
        if not manifest.exists():
            return None
        try:
            import yaml  # type: ignore
            data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
            paths = set()
            for resource in data.get("resources", []):
                if resource.get("status") in {"disabled", "reference-only", "quarantined"}: continue
                local = root / str(resource.get("local_path", ""))
                # Ontology directories are governed solely by the graph deployment allowlist.
                if local.parts and "ontologies" in local.parts:
                    continue
                if local.is_file(): paths.add(local.resolve())
                elif local.is_dir(): paths.update(p.resolve() for p in local.rglob("*") if p.is_file())
            graph_manifest = root / "graph" / "deployment-manifest.yaml"
            if graph_manifest.exists():
                graph = yaml.safe_load(graph_manifest.read_text(encoding="utf-8")) or {}
                for item in graph.get("selected", []):
                    for rel in item.get("files", []):
                        candidate = (graph_manifest.parent / rel).resolve()
                        if candidate.is_file(): paths.add(candidate)
            return paths
        except Exception:
            return None

    def search(self, query: str, *, top_k: int = 6, filters: dict | None = None) -> EvidencePackage:
        return self.retriever.search(query, release_id=self.release.release_id, top_k=min(top_k,20), filters=filters)
    def retrieve(self, query: str, *, filters: dict | None = None, top_k: int = 6) -> EvidencePackage:
        return self.search(query, top_k=top_k, filters=filters)
    def browse(self):
        return [{"doc_id": d.document_id, "title": d.title, "domain": d.domain, "source_uri": d.source_uri, "document_version": d.document_version} for d in self.documents.values()]
    def fetch(self, doc_id: str, chapter: str | None = None) -> DocumentDetail:
        if doc_id not in self.documents: raise KeyError(doc_id)
        chunks = [c for c in self.chunks.values() if c.document_id == doc_id and (not chapter or c.chapter_path == chapter)]
        return DocumentDetail(document=self.documents[doc_id], chunks=chunks)

    def list_releases(self):
        return [r.model_dump(mode="json") for r in self.releases.values()]

    def activate(self, release_id: str):
        if release_id not in self.releases: raise KeyError(release_id)
        self.registry.activate(release_id)
        return self.releases[release_id]

    def rollback(self, release_id: str | None = None):
        target = release_id or self.registry.previous
        if not target or target not in self.releases: raise KeyError(target or "")
        self.registry.rollback(target)
        self.release = self.releases[target]
        return self.release

    def persist(self, data_path: str | Path) -> Path:
        """Persist the deterministic local runtime bundle under an ignored data root."""
        root = Path(data_path) / "releases" / self.release.release_id
        root.mkdir(parents=True, exist_ok=True)
        (root / "manifest.json").write_text(self.release.model_dump_json(indent=2), encoding="utf-8")
        self.bm25.dump(root / "bm25.json")
        (root / "chunks.jsonl").write_text("\n".join(c.model_dump_json() for c in self.chunks.values()), encoding="utf-8")
        (root / "documents.jsonl").write_text("\n".join(d.model_dump_json() for d in self.documents.values()), encoding="utf-8")
        (Path(data_path) / "active_release").write_text(self.release.release_id, encoding="utf-8")
        self.data_path = Path(data_path)
        return root

    def load(self, data_path: str | Path) -> IndexRelease | None:
        """Restore the last active release from disk + embedded Qdrant storage."""
        root = Path(data_path)
        active = root / "active_release"
        if not active.exists():
            return None
        release_id = active.read_text(encoding="utf-8").strip()
        bundle = root / "releases" / release_id
        if not bundle.exists():
            return None
        release = IndexRelease.model_validate_json((bundle / "manifest.json").read_text(encoding="utf-8"))
        docs = {}
        docs_path = bundle / "documents.jsonl"
        if docs_path.exists():
            for line in docs_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    doc = DocumentRecord.model_validate_json(line)
                    docs[doc.document_id] = doc
        chunks = {}
        for line in (bundle / "chunks.jsonl").read_text(encoding="utf-8").splitlines():
            if line.strip():
                chunk = ChunkRecord.model_validate_json(line)
                chunks[chunk.chunk_id] = chunk
        bm25 = BM25Index.load(bundle / "bm25.json")
        vectors = None
        if self.qdrant_mode == "embedded" and release.embedding_dimension:
            vectors = EmbeddedQdrantIndex(
                release.embedding_dimension,
                release_id,
                self.qdrant_path / release_id,
                recreate=False,
            )
        self.documents, self.chunks, self.bm25, self.vectors = docs, chunks, bm25, vectors
        self.release = release.model_copy(update={"status": "active"})
        self.registry.active = release_id
        self.releases[release_id] = self.release
        self.retriever = HybridRetriever(self.documents, self.chunks, self.bm25, self.vectors, self.embedding)
        self.data_path = root
        return self.release

    def close(self) -> None:
        if self.vectors is not None and hasattr(self.vectors, "close"):
            self.vectors.close()
