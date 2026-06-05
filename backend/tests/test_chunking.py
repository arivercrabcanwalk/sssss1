from app.models import DocPage
from app.rag.chunking import chunk_pages, extract_keywords


def test_chunk_pages_preserves_doc_evidence() -> None:
    page = DocPage(
        id="p1",
        title="Cards",
        url="https://docs.4gaboards.com/docs/card/",
        headings=["Cards"],
        content="Cards manage tasks.\n\nUsers can create card titles and descriptions.\n\nCards support labels.",
    )

    chunks = chunk_pages([page], max_chars=80, overlap=10)

    assert chunks
    assert chunks[0].page_id == "p1"
    assert chunks[0].url == page.url
    assert "card" in " ".join(chunks[0].keywords).lower()


def test_extract_keywords_filters_common_words() -> None:
    keywords = extract_keywords("The user can create project project board card")

    assert "project" in keywords
    assert "the" not in keywords
