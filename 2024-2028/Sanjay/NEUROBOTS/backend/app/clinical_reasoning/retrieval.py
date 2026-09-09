from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer


EMBEDDING_MODEL = "sklearn-hashing-vectorizer-word-bigram-v1"
EMBEDDING_DIMENSION = 4096
INDEX_VERSION = "clinical-hashing-index-1.0.0"
MAX_QUERY_CHARACTERS = 500
MAX_TOP_K = 5
MAX_SNIPPET_CHARACTERS = 900
MIN_RETRIEVAL_SCORE = 0.08


class ClinicalKnowledgeRetriever:
    """Small offline vector retriever with deterministic local embeddings."""

    def __init__(self, corpus_path: str | Path, index_path: str | Path) -> None:
        self.corpus_path = Path(corpus_path)
        self.index_path = Path(index_path)
        corpus_bytes = self.corpus_path.read_bytes()
        self.corpus_sha256 = sha256(corpus_bytes).hexdigest()
        corpus = json.loads(corpus_bytes)
        self.corpus_version = str(corpus["corpus_version"])
        self.chunks: list[dict[str, Any]] = list(corpus["chunks"])
        self.vectorizer = HashingVectorizer(
            n_features=EMBEDDING_DIMENSION,
            alternate_sign=False,
            norm="l2",
            stop_words="english",
            ngram_range=(1, 2),
        )
        self._matrix = self._load_or_build_index()

    def _embed(self, texts: list[str]) -> np.ndarray:
        return self.vectorizer.transform(texts).astype(np.float32).toarray()

    def _load_or_build_index(self) -> np.ndarray:
        if self.index_path.exists():
            try:
                loaded = np.load(self.index_path, allow_pickle=False)
                metadata = json.loads(str(loaded["metadata"].item()))
                matrix = loaded["matrix"]
                if (
                    metadata["index_version"] == INDEX_VERSION
                    and metadata["corpus_version"] == self.corpus_version
                    and metadata["corpus_sha256"] == self.corpus_sha256
                    and metadata["embedding_model"] == EMBEDDING_MODEL
                    and int(metadata["embedding_dimension"]) == EMBEDDING_DIMENSION
                    and matrix.shape == (len(self.chunks), EMBEDDING_DIMENSION)
                ):
                    return matrix.astype(np.float32)
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                pass
        matrix = self._embed([chunk["content"] for chunk in self.chunks])
        metadata = self.index_metadata
        try:
            self.index_path.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(
                self.index_path,
                matrix=matrix,
                metadata=np.array(json.dumps(metadata, sort_keys=True)),
            )
        except OSError:
            # Read-only deployments still get a fully local in-memory index.
            pass
        return matrix

    @property
    def index_metadata(self) -> dict[str, Any]:
        return {
            "embedding_model": EMBEDDING_MODEL,
            "embedding_dimension": EMBEDDING_DIMENSION,
            "corpus_version": self.corpus_version,
            "corpus_sha256": self.corpus_sha256,
            "index_version": INDEX_VERSION,
            "chunk_count": len(self.chunks),
        }

    def retrieve(self, query: str, *, top_k: int = 3) -> dict[str, Any]:
        timer = perf_counter()
        normalized = " ".join(query.split())[:MAX_QUERY_CHARACTERS]
        limited_top_k = min(max(int(top_k), 1), MAX_TOP_K)
        if not normalized:
            return {
                "status": "NO_RELEVANT_EVIDENCE",
                "query": "",
                "results": [],
                "index_metadata": self.index_metadata,
                "latency_ms": round((perf_counter() - timer) * 1000, 3),
            }
        query_vector = self._embed([normalized])[0]
        scores = self._matrix @ query_vector
        ranked = np.argsort(scores)[::-1][:limited_top_k]
        results: list[dict[str, Any]] = []
        for index in ranked:
            score = float(scores[index])
            if score < MIN_RETRIEVAL_SCORE:
                continue
            chunk = self.chunks[int(index)]
            results.append(
                {
                    "chunk_id": chunk["chunk_id"],
                    "source_id": chunk["source_id"],
                    "source_title": chunk["title"],
                    "organization": chunk["organization"],
                    "section": chunk["section"],
                    "snippet": chunk["content"][:MAX_SNIPPET_CHARACTERS],
                    "retrieval_score": round(score, 6),
                    "metadata": {
                        "source_url": chunk["source_url"],
                        "document_version_date": chunk["document_version_date"],
                        "corpus_version": chunk["corpus_version"],
                    },
                }
            )
        return {
            "status": "SUCCESS" if results else "NO_RELEVANT_EVIDENCE",
            "query": normalized,
            "results": results,
            "index_metadata": self.index_metadata,
            "latency_ms": round((perf_counter() - timer) * 1000, 3),
        }
