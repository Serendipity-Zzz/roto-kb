from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel, Field

from ..config import Settings
from ..providers.embedding import build_embedding_provider
from ..service import KnowledgeService


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=10000)
    top_k: int = Field(default=6, ge=1, le=20)
    filters: dict | None = None


def create_app(settings: Settings | None = None, service: KnowledgeService | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.validate()
    if service is None:
        embedding = build_embedding_provider(settings)
        empty = settings.mode == "empty"
        source = None if empty else settings.source_path
        service = KnowledgeService(
            source,
            embedding=embedding,
            qdrant_mode=settings.qdrant_mode,
            qdrant_path=settings.qdrant_path,
            data_path=None if empty else settings.data_path,
        )
    app = FastAPI(title="ROTO-KB", version="0.1.0")

    class PrefixMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            path = request.scope.get("path", "")
            if path == "/roto-kb" or path.startswith("/roto-kb/"):
                request.scope["path"] = path[len("/roto-kb"):] or "/"
            return await call_next(request)
    app.add_middleware(PrefixMiddleware)

    def auth(scope: str):
        async def dependency(authorization: Annotated[str | None, Header()] = None):
            token = authorization[7:] if authorization and authorization.lower().startswith("bearer ") else ""
            expected = settings.read_token if scope == "read" else settings.admin_token
            if not expected or not secrets.compare_digest(token, expected): raise HTTPException(status_code=401 if scope == "read" else 403, detail={"error":{"code":"auth.invalid","message":"authentication required"}})
        return dependency

    @app.get("/health")
    def health():
        return {"status":"ok","content_status":service.content_status,"active_release_id":service.release.release_id,"chunk_count":service.release.chunk_count,"document_count":service.release.document_count}

    @app.get("/browse", dependencies=[Depends(auth("read"))])
    def browse(): return {"items": service.browse(), "count": len(service.documents)}

    @app.post("/search", dependencies=[Depends(auth("read"))])
    def search(request: SearchRequest): return service.search(request.query, top_k=request.top_k, filters=request.filters).model_dump(mode="json")

    @app.get("/fetch/{doc_id}", dependencies=[Depends(auth("read"))])
    def fetch(doc_id: str, chapter: str | None = Query(None)):
        try: return service.fetch(doc_id, chapter).model_dump(mode="json")
        except KeyError: raise HTTPException(status_code=404, detail={"error":{"code":"knowledge.not_found","message":"document not found"}})

    @app.get("/graph/{doc_id}", dependencies=[Depends(auth("read"))])
    def graph(doc_id: str): return {"doc_id":doc_id,"outgoing":[],"incoming":[],"relations":[]}

    @app.post("/reload", dependencies=[Depends(auth("admin"))])
    def reload(mode: str = "incremental"):
        return service.reload(mode=mode).model_dump(mode="json")

    @app.get("/lint", dependencies=[Depends(auth("admin"))])
    def lint(): return {"status":"ok","blocking":[],"warnings":[]}

    @app.get("/releases", dependencies=[Depends(auth("admin"))])
    def releases(): return {"items": service.list_releases()}

    @app.post("/releases/{release_id}/activate", dependencies=[Depends(auth("admin"))])
    def activate(release_id: str):
        try: return service.activate(release_id).model_dump(mode="json")
        except KeyError: raise HTTPException(status_code=404, detail={"error":{"code":"release.not_found","message":"release not found"}})

    @app.post("/releases/{release_id}/rollback", dependencies=[Depends(auth("admin"))])
    def rollback(release_id: str):
        try: return service.rollback(release_id).model_dump(mode="json")
        except KeyError: raise HTTPException(status_code=404, detail={"error":{"code":"release.not_found","message":"release not found"}})

    @app.get("/help")
    def help_route(): return {"schema_version":"evidence-package.v1","api_version":"v1","scopes":{"read":["browse","search","fetch","graph"],"admin":["reload","lint"]},"errors":[401,403,404,422,503]}
    return app


app = create_app()
