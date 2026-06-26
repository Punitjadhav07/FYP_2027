import re
from dataclasses import dataclass
from pathlib import Path

import fitz


@dataclass
class PageText:
    page: int
    text: str


def extract_pdf_pages(path: Path) -> list[PageText]:
    pages: list[PageText] = []
    with fitz.open(path) as document:
        for index, page in enumerate(document, start=1):
            text = normalize_text(page.get_text("text"))
            if text:
                pages.append(PageText(page=index, text=text))
    return pages


def normalize_text(text: str) -> str:
    text = re.sub(r"-\n", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def chunk_page_text(page_text: PageText, max_words: int = 220, overlap_words: int = 40) -> list[str]:
    words = page_text.text.split()
    if not words:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(start + max_words, len(words))
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start = max(0, end - overlap_words)
    return chunks
