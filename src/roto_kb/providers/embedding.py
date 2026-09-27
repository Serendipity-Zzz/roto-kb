from __future__ import annotations

import hashlib
import math
import re
import time
from typing import Sequence

import httpx


class EmbeddingError(RuntimeError):
    pass


class FakeEmbeddingProvider:
    def __init__(self, dimension: int = 32, model: str = "fake-embedding", batch_size: int = 16):
        self.dimension, self.model, self.batch_size = dimension, model, batch_size

    def _embed(self, text: str) -> list[float]:
        values = [0.0] * self.dimension
        terms = re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]", text.lower())
        for term in terms:
            digest = hashlib.sha256(term.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "big") % self.dimension
            values[idx] += 1.0 if digest[4] & 1 else -1.0
        if not any(values):
            values[0] = 1.0
        norm = math.sqrt(sum(v * v for v in values)) or 1
        return [v / norm for v in values]

    def probe(self) -> int: return self.dimension
    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: return [self._embed(t) for t in texts]
    def embed_query(self, text: str) -> list[float]: return self._embed(text)


def build_embedding_provider(settings) -> FakeEmbeddingProvider | DashScopeEmbeddingProvider:
    """Prefer DashScope when an API key is present; otherwise keep the deterministic fake provider."""
    import os

    api_key = os.getenv("DASHSCOPE_API_KEY")
    if api_key:
        return DashScopeEmbeddingProvider(
            api_key,
            model=settings.embedding_model,
            base_url=settings.dashscope_base_url,
            timeout=settings.embedding_timeout_seconds,
            batch_size=settings.embedding_batch_size,
        )
    return FakeEmbeddingProvider(
        dimension=settings.embedding_dimension or 32,
        model="fake-embedding",
        batch_size=settings.embedding_batch_size,
    )


class DashScopeEmbeddingProvider:
    def __init__(self, api_key: str, *, model: str = "text-embedding-v4", base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1", timeout: float = 30.0, batch_size: int = 16, query_cache_size: int = 256):
        if not api_key:
            raise EmbeddingError("DASHSCOPE_API_KEY is required")
        self.api_key, self.model, self.base_url, self.timeout, self.batch_size = api_key, model, base_url.rstrip("/"), timeout, batch_size
        self._query_cache: dict[str, list[float]] = {}
        self._query_cache_size = max(16, query_cache_size)

    def _request(self, inputs: list[str]) -> list[list[float]]:
        for attempt in range(3):
            try:
                response = httpx.post(f"{self.base_url}/embeddings", headers={"Authorization": f"Bearer {self.api_key}"}, json={"model": self.model, "input": inputs}, timeout=self.timeout)
            except httpx.HTTPError as exc:
                if attempt == 2: raise EmbeddingError("embedding provider unavailable") from exc
                time.sleep(2 ** attempt); continue
            if response.status_code in (401, 403): raise EmbeddingError("embedding provider unauthorized")
            if response.status_code == 429 or response.status_code >= 500:
                if attempt == 2: raise EmbeddingError("embedding provider temporarily unavailable")
                time.sleep(2 ** attempt); continue
            if response.status_code >= 400: raise EmbeddingError("embedding provider rejected request")
            break
        try: data = response.json()["data"]
        except Exception as exc: raise EmbeddingError("invalid embedding response") from exc
        vectors = [item["embedding"] for item in sorted(data, key=lambda x: x.get("index", 0))]
        if len(vectors) != len(inputs) or (vectors and not all(len(v) == len(vectors[0]) for v in vectors)):
            raise EmbeddingError("embedding response count/dimension mismatch")
        return vectors

    def probe(self) -> int: return len(self._request(["roto-kb capability probe"])[0])
    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        # text-embedding-v4 workspaces commonly cap one request at 10 inputs.
        values = list(texts); result = []
        for start in range(0, len(values), min(self.batch_size, 10)):
            result.extend(self._request(values[start:start + min(self.batch_size, 10)]))
        return result

    def embed_query(self, text: str) -> list[float]:
        key = text.strip()
        cached = self._query_cache.get(key)
        if cached is not None:
            return cached
        vector = self._request([text])[0]
        if len(self._query_cache) >= self._query_cache_size:
            # Drop an arbitrary old entry; exact LRU is unnecessary for this hot-path cache.
            self._query_cache.pop(next(iter(self._query_cache)))
        self._query_cache[key] = vector
        return vector
