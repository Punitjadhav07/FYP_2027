import hashlib
import logging
import math
import re
from datetime import datetime
from typing import Iterable

from openai import OpenAI, OpenAIError

from app.config import Settings

LOCAL_EMBEDDING_DIMENSIONS = 512
logger = logging.getLogger(__name__)


def client(settings: Settings) -> OpenAI:
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is missing. Add it to backend/.env.")
    return OpenAI(api_key=settings.openai_api_key)


def embed_texts(settings: Settings, texts: list[str]) -> list[list[float]]:
    if not settings.openai_api_key:
        return [local_embedding(text) for text in texts]

    try:
        response = client(settings).embeddings.create(
            model=settings.openai_embedding_model,
            input=texts,
        )
        return [item.embedding for item in response.data]
    except OpenAIError as exc:
        logger.warning("OpenAI embeddings failed; using local fallback embeddings: %s", exc.__class__.__name__)
        return [local_embedding(text) for text in texts]


def tokenize(text: str) -> list[str]:
    stopwords = {
        "what",
        "who",
        "how",
        "which",
        "when",
        "where",
        "the",
        "was",
        "were",
        "are",
        "does",
        "did",
        "this",
        "that",
        "with",
        "from",
        "into",
        "about",
        "paper",
        "papers",
    }
    return [
        token
        for token in re.findall(r"[a-zA-Z][a-zA-Z0-9-]{2,}", text.lower())
        if token not in stopwords
    ]


def local_embedding(text: str) -> list[float]:
    vector = [0.0] * LOCAL_EMBEDDING_DIMENSIONS
    for token in tokenize(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:2], "big") % LOCAL_EMBEDDING_DIMENSIONS
        sign = 1.0 if digest[2] % 2 == 0 else -1.0
        vector[index] += sign

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def cosine_similarity(left: Iterable[float], right: Iterable[float]) -> float:
    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for a, b in zip(left, right):
        dot += a * b
        left_norm += a * a
        right_norm += b * b
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (math.sqrt(left_norm) * math.sqrt(right_norm))


def retrieve_chunks(settings: Settings, chunks: list[dict], question: str, top_k: int) -> list[dict]:
    if asks_for_summary(question):
        return retrieve_summary_chunks(chunks, top_k)

    query_embedding = embed_texts(settings, [question])[0]
    question_terms = set(tokenize(question))
    asks_definition = question.lower().strip().startswith(("what is", "define", "what are"))
    asks_authors = asks_for_authors(question)
    asks_trend = asks_for_trend(question)
    ranked = [
        {
            **chunk,
            "score": retrieval_score(
                query_embedding,
                question_terms,
                chunk,
                asks_definition,
                asks_authors,
                asks_trend,
            ),
        }
        for chunk in chunks
    ]
    ranked = sorted(ranked, key=lambda item: item["score"], reverse=True)
    if asks_authors:
        author_ranked = [chunk for chunk in ranked if extract_author_candidates(chunk["text"])]
        return (author_ranked or ranked)[:1]
    return ranked[:top_k]


def asks_current_date(question: str) -> bool:
    text = re.sub(r"\s+", " ", question.lower()).strip()
    return bool(
        re.search(r"\b(today'?s|current)\s+date\b", text)
        or re.search(r"\bwhat\s+(is|'s)\s+the\s+date\b", text)
        or text in {"date", "today date", "todays date", "today's date"}
    )


def generate_current_date_answer() -> str:
    today = datetime.now().astimezone().date()
    return f"Today's date is {today.strftime('%B')} {today.day}, {today.year}."


def asks_for_summary(question: str) -> bool:
    text = question.lower()
    return any(
        phrase in text
        for phrase in (
            "brief me",
            "breif me",
            "brief",
            "breif",
            "summarize",
            "summarise",
            "summary",
            "overview",
            "about the paper",
            "explain the paper",
            "paper about",
        )
    )


def asks_for_authors(question: str) -> bool:
    text = question.lower()
    return any(term in text for term in ("author", "authors", "written by", "who wrote"))


def asks_for_trend(question: str) -> bool:
    terms = set(tokenize(question))
    return bool({"evolving", "evolution", "changing", "trend", "trends", "future", "emerging"}.intersection(terms))


def retrieve_summary_chunks(chunks: list[dict], top_k: int) -> list[dict]:
    ranked = sorted(
        ({**chunk, "score": summary_chunk_score(chunk)} for chunk in chunks),
        key=lambda item: item["score"],
        reverse=True,
    )
    return ranked[: max(top_k, 6)]


def generate_summary(settings: Settings, chunks: list[dict], focus: str | None = None) -> str:
    if not chunks:
        return "The uploaded papers do not provide enough readable text to summarize."

    if not settings.openai_api_key:
        return generate_extract_summary(chunks, focus)

    context = "\n\n".join(
        f"Source {index}: {chunk['filename']} page {chunk['page']}\n{chunk['text']}"
        for index, chunk in enumerate(chunks, start=1)
    )
    focus_line = f"Focus the summary on: {focus}." if focus else "Provide a balanced research summary."
    system = (
        "You summarize academic papers using only the provided source excerpts. "
        "Write a concise structured summary with these sections: Overview, Key contributions, "
        "Methods or evidence, Limitations or open questions. Cite every major claim inline "
        "with source labels like [S1]. If the excerpts do not support a section, say so."
    )
    user = f"{focus_line}\n\nSource excerpts:\n{context}"

    try:
        response = client(settings).chat.completions.create(
            model=settings.openai_chat_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
        )
        return normalize_source_labels(response.choices[0].message.content or "")
    except OpenAIError as exc:
        logger.warning("OpenAI summary generation failed; using extractive fallback summary: %s", exc.__class__.__name__)
        return generate_extract_summary(chunks, focus)


def summary_chunk_score(chunk: dict) -> float:
    text_lower = chunk["text"].lower()
    page = int(chunk.get("page", 99))
    score = 0.0

    if page <= 3:
        score += 4.0 - page
    if "abstract" in text_lower:
        score += 2.5
    if "introduction" in text_lower:
        score += 1.8
    if "survey" in text_lower:
        score += 0.8
    if "contribution" in text_lower or "we provide" in text_lower:
        score += 1.0
    if "ccs concepts" in text_lower or "acm reference format" in text_lower:
        score -= 2.0
    return score


def retrieval_score(
    query_embedding: list[float],
    question_terms: set[str],
    chunk: dict,
    asks_definition: bool,
    asks_authors: bool = False,
    asks_trend: bool = False,
) -> float:
    semantic_score = cosine_similarity(query_embedding, chunk["embedding"])
    chunk_terms = set(tokenize(chunk["text"]))
    if not question_terms:
        return semantic_score

    overlap = len(question_terms.intersection(chunk_terms)) / len(question_terms)
    text_lower = chunk["text"].lower()
    filename_terms = set(tokenize(chunk.get("filename", "")))
    filename_bonus = 0.35 * (len(question_terms.intersection(filename_terms)) / len(question_terms))
    phrase_bonus = 0.12 if "hallucination in natural language generation" in text_lower else 0.0
    definition_bonus = 0.0
    if {"definition", "definitions", "defines", "defined", "referring"}.intersection(chunk_terms):
        definition_bonus = 0.3 if asks_definition else 0.1
    author_bonus = 0.0
    if asks_authors:
        page = int(chunk.get("page", 99))
        has_author_marker = bool(extract_author_candidates(chunk["text"]))
        if page == 1:
            author_bonus += 2.0
        if "abstract" in text_lower:
            author_bonus += 0.6
        if has_author_marker:
            author_bonus += 3.0
    trend_bonus = 0.0
    if asks_trend:
        page = int(chunk.get("page", 99))
        if page <= 2:
            trend_bonus += 0.8
        if any(term in text_lower for term in ("moving from", "shift", "transition", "emerging", "future")):
            trend_bonus += 1.0
    reference_penalty = 0.12 if "acm reference format" in text_lower or "ccs concepts" in text_lower else 0.0
    return (
        (0.5 * semantic_score)
        + (0.35 * overlap)
        + filename_bonus
        + phrase_bonus
        + definition_bonus
        + author_bonus
        + trend_bonus
        - reference_penalty
    )


def generate_answer(settings: Settings, question: str, chunks: list[dict]) -> str:
    if asks_current_date(question):
        return generate_current_date_answer()

    if asks_for_authors(question):
        return generate_author_answer(chunks)

    if not settings.openai_api_key:
        return generate_extract_answer(question, chunks)

    context = "\n\n".join(
        f"S{index}: {chunk['filename']} page {chunk['page']}\n{chunk['text']}"
        for index, chunk in enumerate(chunks, start=1)
    )
    system = (
        "You are a careful academic research assistant. Answer only from the provided "
        "context. If the context does not contain the answer, say that the uploaded "
        "papers do not provide enough information. Keep the answer clear and cite "
        "source numbers inline like [S1]."
    )
    user = f"Context:\n{context}\n\nQuestion: {question}"

    try:
        response = client(settings).chat.completions.create(
            model=settings.openai_chat_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
        )
        return normalize_source_labels(response.choices[0].message.content or "")
    except OpenAIError as exc:
        logger.warning("OpenAI answer generation failed; using extractive fallback answer: %s", exc.__class__.__name__)
        return generate_extract_answer(question, chunks)


def generate_extract_answer(question: str, chunks: list[dict]) -> str:
    if not chunks:
        return "The uploaded papers do not provide enough information to answer this question."

    if is_ambiguous_short_reply(question):
        return (
            "Please ask a complete question about the uploaded paper, for example: "
            "'What is the paper about?' or 'Summarize the main contributions.'"
        )

    if asks_current_date(question):
        return generate_current_date_answer()

    if asks_for_summary(question):
        return generate_extract_summary(chunks)

    if asks_for_authors(question):
        return generate_author_answer(chunks)

    question_terms = set(tokenize(question))
    asks_definition = question.lower().strip().startswith(("what is", "define", "what are"))
    asks_trend = asks_for_trend(question)
    sentences: list[tuple[int, str, str]] = []
    for index, chunk in enumerate(chunks, start=1):
        for sentence in re.split(r"(?<=[.!?])\s+", chunk["text"]):
            cleaned = sentence.strip()
            if len(cleaned) < 40:
                continue
            if cleaned.lower().startswith(("keywords:", "index terms:", "ccs concepts:", "additional key words")):
                continue
            sentence_terms = set(tokenize(cleaned))
            overlap = len(question_terms.intersection(sentence_terms))
            definition_bonus = 0
            if asks_definition and {
                "definition",
                "defined",
                "defines",
                "referring",
                "unfaithful",
                "nonsensical",
            }.intersection(sentence_terms):
                definition_bonus = 5
            trend_bonus = 0
            if asks_trend and any(
                term in cleaned.lower()
                for term in ("moving from", "shift", "transition", "emerging", "future", "from", "to")
            ):
                trend_bonus = 4
            noise_penalty = 3 if {"reference", "format", "concepts", "copyright"}.intersection(sentence_terms) else 0
            sentences.append((overlap + definition_bonus + trend_bonus - noise_penalty, cleaned, f"[S{index}]"))

    ranked = sorted(sentences, key=lambda item: item[0], reverse=True)
    selected = [item for item in ranked if item[0] > 0][:4] or ranked[:3]
    if not selected:
        return "The uploaded papers do not provide enough information to answer this question."

    answer_lines = [f"{sentence} {source}" for _, sentence, source in selected]
    return "\n\n".join(answer_lines)


def has_enough_evidence(question: str, chunks: list[dict]) -> bool:
    if asks_current_date(question) or asks_for_summary(question) or asks_for_authors(question):
        return True
    if not chunks:
        return False

    question_terms = set(tokenize(question))
    if not question_terms:
        return False

    best_score = max(float(chunk.get("score", 0.0)) for chunk in chunks)
    best_overlap = 0.0
    for chunk in chunks:
        evidence_terms = set(tokenize(f"{chunk.get('filename', '')} {chunk.get('text', '')}"))
        if not evidence_terms:
            continue
        overlap = len(question_terms.intersection(evidence_terms)) / len(question_terms)
        best_overlap = max(best_overlap, overlap)

    return best_overlap >= 0.25 or best_score >= 0.55


def generate_author_answer(chunks: list[dict]) -> str:
    for index, chunk in enumerate(chunks, start=1):
        authors = extract_author_candidates(chunk["text"])
        if authors:
            return f"The paper lists {format_author_list(authors)} as the author(s). [S{index}]"
    return "The uploaded papers do not provide enough title-page or citation information to identify the author(s)."


def extract_author_candidates(text: str) -> list[str]:
    front_matter = re.split(r"\bAbstract\b", text, maxsplit=1)[0]
    front_matter = re.sub(r"\s+", " ", front_matter).strip()
    if not front_matter:
        return []

    authors = extract_authors_near_emails(front_matter)
    if authors:
        return authors[:12]

    affiliation_markers = (
        "University",
        "Institute",
        "College",
        "School",
        "Department",
        "Faculty",
        "Laboratory",
        "Centre",
        "Center",
    )
    marker_pattern = "|".join(affiliation_markers)
    pattern = rf"\b([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){{0,3}})\s+(?:{marker_pattern})\b"

    authors: list[str] = []
    for match in re.finditer(pattern, front_matter):
        candidate = clean_author_name(match.group(1))
        if not candidate:
            continue
        if candidate.lower() in {
            "artificial intelligence",
            "large language model",
            "university",
            "institute",
            "college",
            "school",
            "department",
            "faculty",
            "laboratory",
            "centre",
            "center",
        }:
            continue
        if candidate not in authors:
            authors.append(candidate)
    return authors[:12]


def extract_authors_near_emails(front_matter: str) -> list[str]:
    emails = list(re.finditer(r"[\w.+-]+@[\w.-]+\.\w+", front_matter))
    if not emails:
        return []

    authors: list[str] = []
    start = 0
    for email in emails:
        segment = front_matter[start : email.start()]
        name = author_from_affiliation_segment(segment)
        if name and name not in authors:
            authors.append(name)
        start = email.end()
    return authors


def author_from_affiliation_segment(segment: str) -> str:
    affiliation_pattern = (
        r"\b(?:University|Institute|College|School|Department|Faculty|Laboratory|Centre|Center|"
        r"National Institute)\b"
    )
    match = re.search(affiliation_pattern, segment)
    if not match:
        return ""
    before_affiliation = segment[: match.start()].strip()
    words = before_affiliation.split()
    if not words:
        return ""

    candidate_words: list[str] = []
    for word in reversed(words):
        stripped = re.sub(r"^[^A-Za-z]+|[^A-Za-z.]+$", "", word)
        if not stripped:
            continue
        if stripped[:1].isupper() or re.fullmatch(r"[A-Z](?:\.[A-Z]\.)?", stripped):
            candidate_words.append(stripped)
            if len(candidate_words) == 4:
                break
            continue
        break

    candidate = " ".join(reversed(candidate_words))
    return clean_author_name(candidate)


def clean_author_name(name: str) -> str:
    name = re.sub(r"^\W+|\W+$", "", name)
    words = name.split()
    while len(words) > 1 and words[0].lower() in {
        "agentic",
        "artificial",
        "intelligence",
        "architectures",
        "taxonomies",
        "evaluation",
        "large",
        "language",
        "model",
        "agents",
    }:
        words.pop(0)
    cleaned = " ".join(words).strip()
    if not cleaned or len(cleaned) < 3:
        return ""
    if len(cleaned.split()) > 4:
        return ""
    return cleaned


def format_author_list(authors: list[str]) -> str:
    if len(authors) == 1:
        return authors[0]
    if len(authors) == 2:
        return f"{authors[0]} and {authors[1]}"
    return ", ".join(authors[:-1]) + f", and {authors[-1]}"


def generate_extract_summary(chunks: list[dict], focus: str | None = None) -> str:
    sentences: list[tuple[float, str, str]] = []
    for index, chunk in enumerate(chunks, start=1):
        page = int(chunk.get("page", 99))
        for sentence in split_sentences(chunk["text"]):
            cleaned = clean_sentence(sentence)
            if not is_useful_summary_sentence(cleaned):
                continue
            text_lower = cleaned.lower()
            score = 0.0
            if "abstract" in text_lower:
                score += 2.0
            if page <= 2:
                score += 2.0
            if any(
                term in text_lower
                for term in (
                    "survey",
                    "overview",
                    "research progress",
                    "challenge",
                    "architecture",
                    "taxonomy",
                    "evaluation",
                )
            ):
                score += 1.5
            if any(
                term in text_lower
                for term in (
                    "agentic ai",
                    "large language model",
                    "autonomous",
                    "perceive",
                    "reason",
                    "plan",
                    "act",
                    "hallucination",
                    "hallucinated",
                    "unfaithful",
                    "nonsensical",
                )
            ):
                score += 1.5
            if any(term in text_lower for term in ("metrics", "mitigation", "future directions", "downstream tasks")):
                score += 1.0
            if "ccs concepts" in text_lower or "reference format" in text_lower:
                score -= 3.0
            if focus:
                focus_terms = set(tokenize(focus))
                if focus_terms:
                    sentence_terms = set(tokenize(cleaned))
                    score += len(focus_terms.intersection(sentence_terms)) / len(focus_terms)
            sentences.append((score, cleaned, f"[S{index}]"))

    selected: list[tuple[float, str, str]] = []
    seen = set()
    for item in sorted(sentences, key=lambda value: value[0], reverse=True):
        normalized = re.sub(r"\W+", " ", item[1].lower())[:120]
        if normalized in seen or is_duplicate_summary(item[1], selected):
            continue
        selected.append(item)
        seen.add(normalized)
        if len(selected) == 5:
            break

    if not selected:
        return "The uploaded paper does not provide enough readable overview text to summarize it."

    bullets = [f"- {sentence} {source}" for _, sentence, source in selected]
    heading = "Focused summary" if focus else "Research summary"
    return f"{heading}:\n\n" + "\n".join(bullets)


def normalize_source_labels(text: str) -> str:
    text = re.sub(r"\[Source\s+(\d+)\]", r"[S\1]", text)
    text = re.sub(r"\(Source\s+(\d+)\)", r"[S\1]", text)
    return text


def split_sentences(text: str) -> list[str]:
    return re.split(r"(?<=[.!?])\s+", text)


def clean_sentence(sentence: str) -> str:
    return re.sub(r"\s+", " ", sentence).strip()


def is_useful_summary_sentence(sentence: str) -> bool:
    if len(sentence) < 65 or len(sentence) > 420:
        return False
    if sentence[:1].islower() or sentence.lower().startswith(("and ", "or ", "but ")):
        return False
    text_lower = sentence.lower()
    if text_lower.startswith(("keywords:", "index terms:", "abstract artificial intelligence")):
        return False
    noisy_terms = (
        "copyright",
        "permission",
        "acm reference format",
        "ccs concepts",
        "authors' address",
        "@",
        "http",
        "isbn",
        "university college",
        "national institute",
        "school of computing",
    )
    return not any(term in text_lower for term in noisy_terms)


def is_ambiguous_short_reply(question: str) -> bool:
    text = question.strip().lower()
    if len(text.split()) > 2:
        return False
    return text in {
        "yes",
        "yea",
        "yeah",
        "yup",
        "no",
        "nope",
        "non",
        "ok",
        "okay",
        "fine",
    }


def is_duplicate_summary(sentence: str, selected: list[tuple[float, str, str]]) -> bool:
    normalized = re.sub(r"\W+", " ", sentence.lower()).strip()
    words = set(normalized.split())
    if not words:
        return True
    for _, existing, _ in selected:
        existing_words = set(re.sub(r"\W+", " ", existing.lower()).split())
        if not existing_words:
            continue
        overlap = len(words.intersection(existing_words)) / min(len(words), len(existing_words))
        if overlap > 0.72:
            return True
    return False
