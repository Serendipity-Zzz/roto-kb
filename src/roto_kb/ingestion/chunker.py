from __future__ import annotations

import re

from ..domain.models import ChunkRecord, DocumentRecord, stable_id


HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def chunk_document(document: DocumentRecord, *, target_chars: int = 1800, overlap_chars: int = 250, min_chars: int = 80, pipeline_version: str = "rag.v1") -> list[ChunkRecord]:
    """Split text at headings/paragraphs while keeping deterministic IDs."""
    lines = document.content.replace("\r\n", "\n").splitlines()
    sections: list[tuple[str, list[str]]] = []
    path: list[str] = []
    buf: list[str] = []
    for line in lines:
        match = HEADING.match(line)
        if match:
            if buf:
                sections.append((" / ".join(path), buf)); buf = []
            level = len(match.group(1))
            path = path[: level - 1] + [match.group(2).strip()]
        else:
            buf.append(line)
    if buf:
        sections.append((" / ".join(path), buf))
    if not sections and document.content:
        sections = [("", document.content.splitlines())]
    result: list[ChunkRecord] = []
    ordinal = 0
    for chapter, section_lines in sections:
        text = "\n".join(section_lines).strip()
        if not text:
            continue
        parts = [text[i:i + target_chars] for i in range(0, len(text), max(1, target_chars - overlap_chars))]
        for part in parts:
            if len(part.strip()) < min_chars and result:
                result[-1] = result[-1].model_copy(update={"content": result[-1].content + "\n" + part.strip()})
                continue
            retrieval = " ".join(x for x in (document.title, document.domain, chapter, part) if x)
            cid = stable_id("chk", document.document_id, document.document_version, ordinal, part, pipeline_version)
            result.append(ChunkRecord(chunk_id=cid, document_id=document.document_id, document_version=document.document_version,
                ordinal=ordinal, chapter_path=chapter, content=part.strip(), retrieval_text=retrieval,
                source_uri=document.source_uri, source_hash=document.source_hash, domain=document.domain,
                security_scope=document.security_scope))
            ordinal += 1
    return result
