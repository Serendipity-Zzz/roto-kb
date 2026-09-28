from __future__ import annotations

import re
from collections import defaultdict

from .domain.models import ChunkRecord, DocumentRecord, EvidencePackage, EvidenceResult, EvidenceSnippet

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{1,64}$")
_IDENTIFIER_DENSE = re.compile(r"^[A-Za-z0-9_]+(?:\s+[A-Za-z0-9_]+){0,2}$")


def reciprocal_rank_fusion(*ranked_lists: list[str], k: int = 60) -> dict[str, float]:
    scores = defaultdict(float)
    for rows in ranked_lists:
        for rank, item in enumerate(rows, 1):
            scores[item] += 1.0 / (k + rank)
    return dict(scores)


def is_identifier_query(query: str) -> bool:
    """Engineering parameter lookups should prefer exact lexical match over semantic drift."""
    text = " ".join(query.strip().split())
    if not text or len(text) > 80:
        return False
    if _IDENTIFIER.fullmatch(text):
        return "_" in text or text.lower() in {"volfrac", "compliance", "penalty", "mesh"}
    if not _IDENTIFIER_DENSE.fullmatch(text):
        return False
    tokens = text.split()
    return any("_" in token for token in tokens) or any(token.lower() in {"vol_frac", "traction_bcs", "filter_radius"} for token in tokens)


def resolve_allowed_chunk_ids(chunks: dict[str, ChunkRecord], filters: dict | None) -> set[str] | None:
    """Translate API filters into chunk IDs.

    Supports:
    - domain / domains
    - security_scope / security_scopes
    Unknown keys are ignored so clients can evolve filters without hard-failing.
    """
    if not filters:
        return None
    domains = filters.get("domains", filters.get("domain"))
    if isinstance(domains, str):
        domains = [domains]
    scopes = filters.get("security_scopes", filters.get("security_scope"))
    if isinstance(scopes, str):
        scopes = [scopes]
    if not domains and not scopes:
        return None
    domain_set = set(domains) if domains else None
    scope_set = set(scopes) if scopes else None
    allowed: set[str] = set()
    for chunk_id, chunk in chunks.items():
        if domain_set is not None and chunk.domain not in domain_set:
            continue
        if scope_set is not None and chunk.security_scope not in scope_set:
            continue
        allowed.add(chunk_id)
    return allowed


class HybridRetriever:
    def __init__(self, documents: dict[str, DocumentRecord], chunks: dict[str, ChunkRecord], bm25, vectors=None, embedder=None):
        self.documents, self.chunks, self.bm25, self.vectors, self.embedder = documents, chunks, bm25, vectors, embedder

    def search(self, query: str, *, release_id: str, top_k: int = 6, filters: dict | None = None) -> EvidencePackage:
        allowed = resolve_allowed_chunk_ids(self.chunks, filters)
        if allowed is not None and not allowed:
            return EvidencePackage(query=query, index_release_id=release_id, no_match=True)

        reasons: list[str] = []
        bm = self.bm25.search(query, 20, allowed) if self.bm25 else []
        identifier = is_identifier_query(query)
        vec: list = []

        # Identifier queries (vol_frac / traction_bcs): BM25-first avoids remote embedding latency
        # and semantic drift into unrelated "volume/density" ontology text.
        use_vector = bool(self.vectors and self.embedder) and not (identifier and bm)
        if use_vector:
            try:
                threshold = 0.22 if identifier else 0.15
                vec = [row for row in self.vectors.search(self.embedder.embed_query(query), 20, allowed) if row[1] >= threshold]
            except Exception:
                reasons.append("embedding_unavailable")
        elif identifier and bm:
            reasons.append("identifier_bm25_only")

        ranked = [[chunk_id for chunk_id, _ in bm]]
        if vec:
            ranked.append([row[0] for row in vec])
        # Boost exact lexical hits for engineering identifiers.
        if identifier and bm:
            ranked.append([chunk_id for chunk_id, _ in bm[:10]])

        scores = reciprocal_rank_fusion(*ranked)
        if not scores:
            return EvidencePackage(
                query=query,
                index_release_id=release_id,
                no_match=True,
                degraded=bool(reasons and reasons != ["identifier_bm25_only"]),
                degradation_reasons=[r for r in reasons if r != "identifier_bm25_only"],
            )

        by_doc: dict[str, list] = defaultdict(list)
        for chunk_id, score in scores.items():
            chunk = self.chunks[chunk_id]
            by_doc[chunk.document_id].append((score, chunk))

        results = []
        for doc_id, rows in sorted(by_doc.items(), key=lambda item: (-max(score for score, _ in item[1]), item[0]))[:top_k]:
            doc = self.documents[doc_id]
            rows = sorted(rows, key=lambda item: -item[0])[:3]
            match_type = "hybrid" if bm and vec else ("bm25" if bm else "vector")
            results.append(
                EvidenceResult(
                    doc_id=doc_id,
                    title=doc.title,
                    domain=doc.domain,
                    score=max(score for score, _ in rows),
                    match_type=match_type,
                    snippets=[
                        EvidenceSnippet(
                            chunk_id=chunk.chunk_id,
                            chapter_path=chunk.chapter_path,
                            content=chunk.content,
                            source_uri=chunk.source_uri,
                            source_hash=chunk.source_hash,
                            document_version=chunk.document_version,
                            security_scope=chunk.security_scope,
                        )
                        for _, chunk in rows
                    ],
                )
            )
        return EvidencePackage(
            query=query,
            index_release_id=release_id,
            results=results,
            degraded=bool([r for r in reasons if r != "identifier_bm25_only"]),
            degradation_reasons=[r for r in reasons if r != "identifier_bm25_only"],
            no_match=False,
        )
