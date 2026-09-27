"""Infrastructure-free versioned domain contract for ROTO-KB."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def stable_id(prefix: str, *parts: object) -> str:
    value = "\x1f".join(str(p) for p in parts)
    return f"{prefix}_{hashlib.sha256(value.encode('utf-8')).hexdigest()[:24]}"


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceRecord(ContractModel):
    source_id: str
    source_uri: str
    path: str | None = None
    retrieved_at: datetime = Field(default_factory=utc_now)
    revision: str | None = None
    sha256: str
    license: str
    attribution: str = ""
    domain: str = "general"
    security_scope: str = "public"
    status: Literal["active", "disabled", "quarantined", "reference-only"] = "active"

    @field_validator("sha256")
    @classmethod
    def valid_hash(cls, value: str) -> str:
        if not re.fullmatch(r"[0-9a-fA-F]{64}", value):
            raise ValueError("sha256 must be a 64 character hexadecimal hash")
        return value.lower()


class DocumentRecord(ContractModel):
    document_id: str
    title: str
    source_id: str
    source_uri: str
    source_hash: str
    document_version: str
    domain: str = "general"
    security_scope: str = "public"
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChunkRecord(ContractModel):
    chunk_id: str
    document_id: str
    document_version: str
    ordinal: int = Field(ge=0)
    chapter_path: str = ""
    content: str
    retrieval_text: str
    source_uri: str
    source_hash: str
    domain: str = "general"
    security_scope: str = "public"


class IndexRelease(ContractModel):
    release_id: str
    schema_version: str = "index-release.v1"
    pipeline_version: str = "rag.v1"
    status: Literal["empty", "building", "ready", "active", "previous", "failed", "rejected"] = "empty"
    created_at: datetime = Field(default_factory=utc_now)
    embedding_model: str | None = None
    embedding_dimension: int | None = None
    chunk_count: int = 0
    document_count: int = 0
    source_hashes: tuple[str, ...] = ()
    eval_report: dict[str, Any] = Field(default_factory=dict)


class EvidenceSnippet(ContractModel):
    chunk_id: str
    chapter_path: str = ""
    content: str
    source_uri: str
    source_hash: str
    document_version: str
    security_scope: str


class EvidenceResult(ContractModel):
    doc_id: str
    title: str
    domain: str
    score: float
    match_type: str = "hybrid"
    snippets: list[EvidenceSnippet] = Field(default_factory=list)
    related_hint: list[dict[str, Any]] = Field(default_factory=list)


class EvidencePackage(ContractModel):
    schema_version: str = "evidence-package.v1"
    query: str
    index_release_id: str
    results: list[EvidenceResult] = Field(default_factory=list)
    degraded: bool = False
    degradation_reasons: list[str] = Field(default_factory=list)
    no_match: bool = False


class DocumentDetail(ContractModel):
    document: DocumentRecord
    chunks: list[ChunkRecord] = Field(default_factory=list)


class GraphEntity(ContractModel):
    entity_id: str
    type: str
    labels: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    domain: str = "general"
    external_uri: str | None = None
    source_refs: list[str] = Field(default_factory=list)
    release_id: str


class GraphRelation(ContractModel):
    source_id: str
    predicate: str
    target_id: str
    confidence: float = Field(ge=0, le=1)
    evidence_refs: list[str] = Field(default_factory=list)
    release_id: str


class GraphRule(ContractModel):
    rule_id: str
    body: dict[str, Any] = Field(default_factory=dict)
    requires: list[str] = Field(default_factory=list)
    forbid_when: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    release_id: str
