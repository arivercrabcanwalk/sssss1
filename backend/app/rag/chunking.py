from __future__ import annotations

import hashlib
import re
from collections import Counter

from app.models import DocPage, KnowledgeChunk


STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "you",
    "your",
    "are",
    "this",
    "that",
    "from",
    "can",
    "using",
    "into",
    "4ga",
    "boards",
}


def stable_id(prefix: str, value: str) -> str:
    return f"{prefix}_{hashlib.sha1(value.encode('utf-8')).hexdigest()[:12]}"


def normalize_text(text: str) -> str:
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_keywords(text: str, limit: int = 12) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}|[\u4e00-\u9fff]{2,}", text.lower())
    counter = Counter(word for word in words if word not in STOPWORDS)
    return [word for word, _ in counter.most_common(limit)]


def chunk_pages(pages: list[DocPage], max_chars: int = 1200, overlap: int = 120) -> list[KnowledgeChunk]:
    chunks: list[KnowledgeChunk] = []
    for page in pages:
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", normalize_text(page.content)) if p.strip()]
        current: list[str] = []
        current_len = 0
        heading = page.headings[0] if page.headings else None
        for paragraph in paragraphs:
            if current and current_len + len(paragraph) > max_chars:
                text = "\n\n".join(current)
                chunks.append(
                    KnowledgeChunk(
                        id=stable_id("chunk", f"{page.url}:{len(chunks)}:{text[:80]}"),
                        page_id=page.id,
                        title=page.title,
                        url=page.url,
                        heading=heading,
                        text=text,
                        keywords=extract_keywords(text),
                    )
                )
                tail = text[-overlap:] if overlap else ""
                current = [tail, paragraph] if tail else [paragraph]
                current_len = len(tail) + len(paragraph)
            else:
                current.append(paragraph)
                current_len += len(paragraph)
        if current:
            text = "\n\n".join(current)
            chunks.append(
                KnowledgeChunk(
                    id=stable_id("chunk", f"{page.url}:{len(chunks)}:{text[:80]}"),
                    page_id=page.id,
                    title=page.title,
                    url=page.url,
                    heading=heading,
                    text=text,
                    keywords=extract_keywords(text),
                )
            )
    return chunks
