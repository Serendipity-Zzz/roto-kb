from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path


def tokenize(text: str) -> list[str]:
    words = re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]|[^\W_]+", text.lower(), flags=re.UNICODE)
    return words


class BM25Index:
    def __init__(self, documents: dict[str, str] | None = None):
        self.documents = documents or {}
        self.tokens = {key: tokenize(value) for key, value in self.documents.items()}
        self.avgdl = sum(map(len, self.tokens.values())) / max(1, len(self.tokens))
        self.df = Counter(token for values in self.tokens.values() for token in set(values))

    def search(self, query: str, top_k: int = 20, allowed_ids: set[str] | None = None) -> list[tuple[str, float]]:
        q = tokenize(query); n = len(self.tokens); scores = {}
        for key, terms in self.tokens.items():
            if allowed_ids is not None and key not in allowed_ids: continue
            counts = Counter(terms); score = 0.0
            for term in q:
                if term not in counts: continue
                idf = math.log(1 + (n - self.df.get(term, 0) + .5) / (self.df.get(term, 0) + .5))
                dl = len(terms); score += idf * counts[term] * 2.2 / (counts[term] + 1.2 * (0.25 + 0.75 * dl / max(1, self.avgdl)))
            if score > 0: scores[key] = score
        return sorted(scores.items(), key=lambda x: (-x[1], x[0]))[:top_k]

    def dump(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps({"documents": self.documents}, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "BM25Index":
        data = json.loads(Path(path).read_text(encoding="utf-8")); return cls(data["documents"])
