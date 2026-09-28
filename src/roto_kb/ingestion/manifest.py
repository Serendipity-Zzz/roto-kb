from __future__ import annotations

import hashlib
from pathlib import Path

from .scanner import scan_sources


def source_manifest(root: str | Path) -> list[dict]:
    """Return a deterministic, hash-addressed catalog for incremental builds."""
    rows = []
    for source in scan_sources(root):
        rows.append({"source_id": source.source_id, "source_uri": source.source_uri, "path": source.path, "sha256": source.sha256, "license": source.license, "domain": source.domain, "security_scope": source.security_scope})
    return sorted(rows, key=lambda x: x["source_id"])


def manifest_hash(rows: list[dict]) -> str:
    return hashlib.sha256("\n".join(f"{r['source_id']}:{r['sha256']}" for r in rows).encode()).hexdigest()
