from __future__ import annotations

import hashlib
import re
from collections import deque
from datetime import UTC, datetime
from urllib.parse import urldefrag, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.models import DocPage
from app.rag.chunking import normalize_text


class DocsCrawler:
    def __init__(self, base_url: str, timeout: float = 20) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.netloc = urlparse(self.base_url).netloc
        self.timeout = timeout

    async def crawl(self, max_pages: int = 80) -> list[DocPage]:
        visited: set[str] = set()
        queue: deque[str] = deque([self.base_url])
        pages: list[DocPage] = []
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            while queue and len(pages) < max_pages:
                url = queue.popleft()
                clean_url = urldefrag(url)[0].rstrip("/") + "/"
                if clean_url in visited:
                    continue
                visited.add(clean_url)
                try:
                    response = await client.get(clean_url)
                    response.raise_for_status()
                except Exception:
                    continue
                content_type = response.headers.get("content-type", "")
                if "text/html" not in content_type:
                    continue
                page, links = self._parse_page(clean_url, response.text)
                if page and len(page.content) > 80:
                    pages.append(page)
                for link in links:
                    if link not in visited and self._is_docs_link(link):
                        queue.append(link)
        return pages

    def _parse_page(self, url: str, html: str) -> tuple[DocPage | None, list[str]]:
        soup = BeautifulSoup(html, "html.parser")
        for selector in ["script", "style", "nav", "footer", "header", "noscript"]:
            for tag in soup.select(selector):
                tag.decompose()
        title = self._title(soup, url)
        main = soup.find("main") or soup.find("article") or soup.body
        if not main:
            return None, []
        headings = [normalize_text(h.get_text(" ")) for h in main.find_all(re.compile("^h[1-3]$"))]
        text = normalize_text(main.get_text("\n"))
        links: list[str] = []
        for anchor in soup.find_all("a", href=True):
            href = anchor.get("href")
            if not href:
                continue
            absolute = urldefrag(urljoin(url, href))[0]
            if self._is_docs_link(absolute):
                links.append(absolute.rstrip("/") + "/")
        page_id = "page_" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
        return (
            DocPage(
                id=page_id,
                title=title,
                url=url,
                content=text,
                headings=headings,
                crawled_at=datetime.now(UTC),
            ),
            links,
        )

    def _title(self, soup: BeautifulSoup, url: str) -> str:
        h1 = soup.find("h1")
        if h1:
            return normalize_text(h1.get_text(" "))
        if soup.title and soup.title.string:
            return normalize_text(soup.title.string.replace("| 4ga Boards", ""))
        path = urlparse(url).path.strip("/") or "4ga Boards Docs"
        return path.split("/")[-1].replace("-", " ").title()

    def _is_docs_link(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return False
        if parsed.netloc != self.netloc:
            return False
        if any(part in parsed.path.lower() for part in ["/api/", "/blog/", "/tags/"]):
            return False
        return True
