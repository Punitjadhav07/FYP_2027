import hashlib
import math
import re
from typing import Iterable

from openai import OpenAI

from app.config import Settings

LOCAL_EMBEDDING_DIMENSIONS = 512


def client(settings: Settings) -> OpenAI:
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is missing. Add it to backend/.env.")
    return OpenAI(api_key=settings.openai_api_key)


def embed_texts(settings: Settings, texts: list[str]) -> list[list[float]]:
    if not settings.openai_api_key:
        return [local_embedding(text) for text in texts]

    response = client(settings).embeddings.create(
        model=settings.openai_embedding_model,
        input=texts,
    )
    return [item.embedding for item in response.data]


def tokenize(text: str) -> list[str]:
    stopwords = {
        "what",
        "which",
        "when",
        "where",
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
    ranked = [
        {**chunk, "score": retrieval_score(query_embedding, question_terms, chunk, asks_definition)}
        for chunk in chunks
    ]
    return sorted(ranked, key=lambda item: item["score"], reverse=True)[:top_k]


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


def retrieve_summary_chunks(chunks: list[dict], top_k: int) -> list[dict]:
    ranked = sorted(
        ({**chunk, "score": summary_chunk_score(chunk)} for chunk in chunks),
        key=lambda item: item["score"],
        reverse=True,
    )
    return ranked[: max(top_k, 6)]


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
) -> float:
    semantic_score = cosine_similarity(query_embedding, chunk["embedding"])
    chunk_terms = set(tokenize(chunk["text"]))
    if not question_terms:
        return semantic_score

    overlap = len(question_terms.intersection(chunk_terms)) / len(question_terms)
    text_lower = chunk["text"].lower()
    phrase_bonus = 0.12 if "hallucination in natural language generation" in text_lower else 0.0
    definition_bonus = 0.0
    if {"definition", "definitions", "defines", "defined", "referring"}.intersection(chunk_terms):
        definition_bonus = 0.3 if asks_definition else 0.1
    reference_penalty = 0.12 if "acm reference format" in text_lower or "ccs concepts" in text_lower else 0.0
    return (0.55 * semantic_score) + (0.45 * overlap) + phrase_bonus + definition_bonus - reference_penalty


def generate_answer(settings: Settings, question: str, chunks: list[dict]) -> str:
    if not settings.openai_api_key:
        return generate_extract_answer(question, chunks)

    context = "\n\n".join(
        f"Source {index}: {chunk['filename']} page {chunk['page']}\n{chunk['text']}"
        for index, chunk in enumerate(chunks, start=1)
    )
    system = (
        "You are a careful academic research assistant. Answer only from the provided "
        "context. If the context does not contain the answer, say that the uploaded "
        "papers do not provide enough information. Keep the answer clear and cite "
        "source numbers inline like [Source 1]."
    )
    user = f"Context:\n{context}\n\nQuestion: {question}"

    response = client(settings).chat.completions.create(
        model=settings.openai_chat_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
    )
    return response.choices[0].message.content or ""


def generate_extract_answer(question: str, chunks: list[dict]) -> str:
    if not chunks:
        return "The uploaded papers do not provide enough information to answer this question."

    if is_ambiguous_short_reply(question):
        return (
            "Please ask a complete question about the uploaded paper, for example: "
            "'What is the paper about?' or 'Summarize the main contributions.'"
        )

    if asks_for_summary(question):
        return generate_extract_summary(chunks)

    question_terms = set(tokenize(question))
    asks_definition = question.lower().strip().startswith(("what is", "define", "what are"))
    sentences: list[tuple[int, str, str]] = []
    for index, chunk in enumerate(chunks, start=1):
        for sentence in re.split(r"(?<=[.!?])\s+", chunk["text"]):
            cleaned = sentence.strip()
            if len(cleaned) < 40:
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
            noise_penalty = 3 if {"reference", "format", "concepts", "copyright"}.intersection(sentence_terms) else 0
            sentences.append((overlap + definition_bonus - noise_penalty, cleaned, f"[Source {index}]"))

    ranked = sorted(sentences, key=lambda item: item[0], reverse=True)
    selected = [item for item in ranked if item[0] > 0][:4] or ranked[:3]
    if not selected:
        return "The uploaded papers do not provide enough information to answer this question."

    answer_lines = [f"{sentence} {source}" for _, sentence, source in selected]
    return "\n\n".join(answer_lines)


def generate_extract_summary(chunks: list[dict]) -> str:
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
            sentences.append((score, cleaned, f"[Source {index}]"))

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
    return "Here is a brief overview of the paper:\n\n" + "\n".join(bullets)


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
