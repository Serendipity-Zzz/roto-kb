"""Offline, allow-list-only graph compiler for JSONL/RDF-like seed files."""
from __future__ import annotations

import json
from pathlib import Path

from ..domain.models import GraphEntity, GraphRelation, GraphRule
from .relations import RelationIndex


def compile_jsonl(path: str | Path, *, release_id: str, allowed_source_refs: set[str] | None = None) -> RelationIndex:
    """Compile the ROTO domain seed without network access or code execution.

    Only explicit JSON objects with ``entity``, ``relation`` or ``rule`` keys are
    accepted. Unknown records and dangling relation endpoints fail closed.
    """
    index = RelationIndex(); allowed_source_refs = allowed_source_refs or set()
    rows = Path(path).read_text(encoding="utf-8").splitlines()
    for line_no, line in enumerate(rows, 1):
        if not line.strip(): continue
        try: row = json.loads(line)
        except json.JSONDecodeError as exc: raise ValueError(f"invalid graph JSONL at line {line_no}") from exc
        kind = row.get("kind", row.get("type"))
        refs = set(row.get("source_refs", []))
        if allowed_source_refs and not refs.issubset(allowed_source_refs): raise ValueError("graph source_ref is not allow-listed")
        if kind in {"entity", "node", "GraphEntity"}:
            entity_id = row.get("entity_id") or row.get("id")
            if not entity_id: raise ValueError("entity id required")
            index.add_entity(GraphEntity(entity_id=entity_id, type=row.get("entity_type", row.get("class", row.get("type", "Thing"))), labels=row.get("labels", [row.get("label", entity_id)]), aliases=row.get("aliases", []), domain=row.get("domain", "general"), external_uri=row.get("external_uri"), source_refs=list(refs), release_id=release_id))
        elif kind in {"relation", "edge", "GraphRelation"}:
            index.add_relation(GraphRelation(source_id=row.get("source_id", row.get("source")), target_id=row.get("target_id", row.get("target")), predicate=row.get("predicate", row.get("relation", "relatedTo")), confidence=float(row.get("confidence", 1.0) if not isinstance(row.get("confidence"), str) else (1.0 if row["confidence"] == "extracted" else .5)), evidence_refs=row.get("evidence_refs", []), release_id=release_id))
        elif kind in {"rule", "GraphRule"}:
            # Rules are validated data only; they are not executed.
            continue
        else: raise ValueError(f"unsupported graph record at line {line_no}")
    return index
