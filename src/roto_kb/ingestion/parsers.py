from __future__ import annotations

import hashlib
import html as html_lib
import re
from pathlib import Path

from ..domain.models import DocumentRecord, SourceRecord, stable_id


def _doc(source: SourceRecord, title: str, content: str, metadata: dict | None = None) -> DocumentRecord:
    version = source.sha256[:16]
    return DocumentRecord(
        document_id=stable_id("doc", source.source_id, version), title=title or source.source_uri,
        source_id=source.source_id, source_uri=source.source_uri, source_hash=source.sha256,
        document_version=version, domain=source.domain, security_scope=source.security_scope,
        content=content, metadata=metadata or {},
    )


def parse_text(source: SourceRecord, content: str, *, title: str = "") -> DocumentRecord:
    return _doc(source, title, content)


def _html_to_text(content: str) -> str:
    content = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", "", content, flags=re.I | re.S)
    content = re.sub(r"<h([1-6])[^>]*>(.*?)</h\1>", lambda m: "#" * int(m.group(1)) + " " + re.sub("<[^>]+>", "", m.group(2)) + "\n", content, flags=re.I | re.S)
    content = re.sub(r"<br\s*/?>", "\n", content, flags=re.I)
    return re.sub(r"<[^>]+>", "", html_lib.unescape(content))


def parse_path(source: SourceRecord, path: Path) -> DocumentRecord:
    suffix = path.suffix.lower()
    raw = path.read_bytes()
    if suffix == ".pdf":
        try:
            import fitz  # type: ignore
            content = "\n".join(page.get_text() for page in fitz.open(stream=raw, filetype="pdf"))
            metadata = {"parser": "pymupdf"}
        except Exception:
            content = ""
            metadata = {"parser": "pdf", "warning": "pdf unavailable or scanned; OCR not enabled"}
    else:
        content = raw.decode("utf-8", errors="replace")
        metadata = {"parser": suffix.lstrip(".") or "text"}
        if suffix in {".html", ".htm"}:
            content = _html_to_text(content)
    return _doc(source, path.stem, content, metadata)


def source_from_path(path: Path, *, root: Path, domain: str = "general", license: str = "internal") -> SourceRecord:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    relative = path.resolve().relative_to(root.resolve()).as_posix()
    source_id = stable_id("src", relative, digest)
    return SourceRecord(source_id=source_id, source_uri=f"file:///{relative}", path=str(path), sha256=digest, license=license, domain=domain)
