import re
from dataclasses import dataclass
from pathlib import Path

import fitz


@dataclass
class PageText:
    page: int
    text: str


def extract_pdf_pages(path: Path, max_pages: int | None = None) -> list[PageText]:
    pages: list[PageText] = []
    with fitz.open(path) as document:
        for index, page in enumerate(document, start=1):
            if max_pages is not None and index > max_pages:
                break
            text = normalize_text(page.get_text("text"))
            if text:
                pages.append(PageText(page=index, text=text))
    return pages


def normalize_text(text: str) -> str:
    text = re.sub(r"-\n", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_page_text(page_text: PageText, max_words: int = 220, overlap_words: int = 40) -> list[str]:
    blocks = semantic_blocks(page_text.text)
    chunks: list[str] = []
    current: list[str] = []
    current_words = 0

    for block in blocks:
        block_words = block.split()
        if not block_words:
            continue

        if len(block_words) > max_words:
            if current:
                chunks.append(" ".join(current))
                current = []
                current_words = 0
            chunks.extend(sliding_word_chunks(block_words, max_words, overlap_words))
            continue

        if current and current_words + len(block_words) > max_words:
            chunks.append(" ".join(current))
            overlap = tail_words(current, overlap_words)
            current = [" ".join(overlap)] if overlap else []
            current_words = len(overlap)

        current.append(block)
        current_words += len(block_words)

    if current:
        chunks.append(" ".join(current))

    return [chunk for chunk in chunks if len(chunk.split()) >= 25]


def semantic_blocks(text: str) -> list[str]:
    raw_blocks = [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]
    if len(raw_blocks) <= 1:
        raw_blocks = split_sentences(text)

    blocks: list[str] = []
    pending_heading = ""
    for block in raw_blocks:
        cleaned = re.sub(r"\s+", " ", block).strip()
        if not cleaned:
            continue
        if is_heading(cleaned):
            pending_heading = cleaned
            continue
        if pending_heading:
            cleaned = f"{pending_heading}. {cleaned}"
            pending_heading = ""
        blocks.append(cleaned)

    if pending_heading:
        blocks.append(pending_heading)
    return blocks


def split_sentences(text: str) -> list[str]:
    return [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", text) if sentence.strip()]


def is_heading(text: str) -> bool:
    words = text.split()
    if len(words) > 10:
        return False
    if re.match(r"^\d+(\.\d+)*\s+[A-Z]", text):
        return True
    return text.istitle() and not text.endswith(".")


def sliding_word_chunks(words: list[str], max_words: int, overlap_words: int) -> list[str]:
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


def tail_words(blocks: list[str], overlap_words: int) -> list[str]:
    words = " ".join(blocks).split()
    if not words:
        return []
    return words[-overlap_words:]
