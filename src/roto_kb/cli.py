import argparse

from .api.app import create_app
from .config import Settings
from .providers.embedding import FakeEmbeddingProvider, build_embedding_provider
from .service import KnowledgeService


def main() -> None:
    parser = argparse.ArgumentParser(prog="roto-kb", description="ROTO-KB RAG service")
    sub = parser.add_subparsers(dest="command")
    serve = sub.add_parser("serve", help="run the HTTP service")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8710)
    build = sub.add_parser("build", help="build a local release from the configured knowledge directory")
    build.add_argument("--provider", choices=("auto", "fake", "dashscope"), default="auto")
    build.add_argument("--source", default=None)
    args = parser.parse_args()
    if args.command == "serve":
        import uvicorn
        # Import the module-level ASGI app once. create_app() must not run twice:
        # embedded Qdrant takes an exclusive filesystem lock per storage path.
        uvicorn.run("roto_kb.api.app:app", host=args.host, port=args.port)
    elif args.command == "build":
        import os

        settings = Settings.from_env()
        source = args.source or settings.source_path
        if args.provider == "fake":
            provider = FakeEmbeddingProvider(dimension=settings.embedding_dimension or 32, model="fake-embedding", batch_size=settings.embedding_batch_size)
        else:
            if args.provider == "dashscope" and not os.getenv("DASHSCOPE_API_KEY"):
                parser.error("DASHSCOPE_API_KEY is required for --provider dashscope")
            provider = build_embedding_provider(settings)
            if args.provider == "dashscope" and provider.__class__.__name__ != "DashScopeEmbeddingProvider":
                parser.error("DashScope provider was not created; check DASHSCOPE_API_KEY")
            if hasattr(provider, "probe") and settings.embedding_dimension:
                probed_dimension = provider.probe()
                if settings.embedding_dimension != probed_dimension:
                    parser.error(f"EMBEDDING_DIMENSION={settings.embedding_dimension} does not match capability probe {probed_dimension}")
        service = KnowledgeService(
            source,
            embedding=provider,
            qdrant_mode=settings.qdrant_mode,
            qdrant_path=settings.qdrant_path,
            data_path=settings.data_path,
        )
        release = service.reload(mode="full")
        bundle = service.persist(settings.data_path)
        print({"release_id": release.release_id, "status": release.status, "documents": release.document_count, "chunks": release.chunk_count, "embedding_model": release.embedding_model, "embedding_dimension": release.embedding_dimension, "bundle": str(bundle)})
        service.close()
    else:
        parser.print_help()
