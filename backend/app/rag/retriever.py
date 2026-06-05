from __future__ import annotations

import math
from collections import Counter

import chromadb
from chromadb.utils import embedding_functions

from app.config import get_settings
from app.models import DocRef, KnowledgeChunk
from app.rag.chunking import extract_keywords


class HybridRetriever:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = chromadb.PersistentClient(path=str(self.settings.index_dir / "chroma"))
        self.collection = self.client.get_or_create_collection(
            "docs",
            embedding_function=embedding_functions.DefaultEmbeddingFunction(),
            metadata={"hnsw:space": "cosine"},
        )
        self.chunks: list[KnowledgeChunk] = []

    def build(self, chunks: list[KnowledgeChunk]) -> int:
        self.chunks = chunks
        if self.collection.count():
            ids = self.collection.get().get("ids", [])
            if ids:
                self.collection.delete(ids=ids)
        if not chunks:
            return 0
        self.collection.add(
            ids=[chunk.id for chunk in chunks],
            documents=[chunk.text for chunk in chunks],
            metadatas=[
                {
                    "page_id": chunk.page_id,
                    "title": chunk.title,
                    "url": chunk.url,
                    "heading": chunk.heading or "",
                    "keywords": ",".join(chunk.keywords),
                }
                for chunk in chunks
            ],
        )
        return len(chunks)

    def search(self, query: str, top_k: int = 6) -> list[DocRef]:
        vector_refs = self._vector_search(query, top_k)
        keyword_refs = self._keyword_search(query, top_k)
        merged: dict[str, DocRef] = {}
        for ref in vector_refs + keyword_refs:
            merged.setdefault(ref.id, ref)
        return list(merged.values())[:top_k]

    def _vector_search(self, query: str, top_k: int) -> list[DocRef]:
        try:
            result = self.collection.query(query_texts=[query], n_results=min(top_k, max(1, self.collection.count())))
        except Exception:
            return []
        refs: list[DocRef] = []
        ids = result.get("ids", [[]])[0]
        docs = result.get("documents", [[]])[0]
        metas = result.get("metadatas", [[]])[0]
        for idx, doc, meta in zip(ids, docs, metas):
            refs.append(
                DocRef(
                    id=idx,
                    title=str(meta.get("title", "")),
                    url=str(meta.get("url", "")),
                    heading=str(meta.get("heading") or ""),
                    snippet=doc[:420],
                )
            )
        return refs

    def _keyword_search(self, query: str, top_k: int) -> list[DocRef]:
        query_terms = extract_keywords(query, limit=20)
        if not query_terms or not self.chunks:
            return []
        doc_freq = Counter()
        chunk_terms: list[set[str]] = []
        for chunk in self.chunks:
            terms = set(chunk.keywords + extract_keywords(chunk.text, limit=50))
            chunk_terms.append(terms)
            for term in terms:
                doc_freq[term] += 1
        scored: list[tuple[float, KnowledgeChunk]] = []
        n = len(self.chunks)
        for chunk, terms in zip(self.chunks, chunk_terms):
            score = 0.0
            text = chunk.text.lower()
            for term in query_terms:
                if term in terms or term in text:
                    score += math.log((n + 1) / (doc_freq[term] + 1)) + 1
            if score:
                scored.append((score, chunk))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            DocRef(
                id=chunk.id,
                title=chunk.title,
                url=chunk.url,
                heading=chunk.heading,
                snippet=chunk.text[:420],
            )
            for _, chunk in scored[:top_k]
        ]
