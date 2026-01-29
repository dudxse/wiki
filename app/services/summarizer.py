from __future__ import annotations

import logging
import re
from typing import Any, Iterable, Mapping, Sequence

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.config import get_settings
from app.llm.client import build_llm
from app.llm.prompt_loader import load_prompt

logger = logging.getLogger(__name__)

SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")
WHITESPACE_PATTERN = re.compile(r"\s+")
PLACEHOLDER_API_KEYS = {"your-openai-api-key"}
PORTUGUESE_WORD_RE = re.compile(r"[a-záàâãéêíóôõúç]+", re.IGNORECASE)
PORTUGUESE_ACCENT_RE = re.compile(r"[áàâãéêíóôõúç]", re.IGNORECASE)
PORTUGUESE_STOPWORDS = {
    "a",
    "o",
    "os",
    "as",
    "um",
    "uma",
    "uns",
    "umas",
    "de",
    "do",
    "da",
    "dos",
    "das",
    "em",
    "no",
    "na",
    "nos",
    "nas",
    "por",
    "para",
    "com",
    "e",
    "que",
    "como",
    "ou",
    "não",
    "mais",
    "menos",
    "já",
    "há",
    "se",
    "sua",
    "seu",
    "suas",
    "seus",
    "entre",
    "ao",
    "à",
    "às",
    "aos",
    "sobre",
    "também",
    "foi",
    "era",
    "ser",
    "são",
    "está",
    "estão",
    "tem",
    "têm",
    "pelo",
    "pela",
    "pelos",
    "pelas",
}
PORTUGUESE_STRONG_STOPWORDS = {word for word in PORTUGUESE_STOPWORDS if len(word) >= 2}

SUMMARY_ORIGIN_LLM = "llm"
SUMMARY_ORIGIN_LLM_FALLBACK = "llm_fallback"
SUMMARY_ORIGIN_FALLBACK = "fallback"
TRANSLATION_ORIGIN_LLM = "llm"
TRANSLATION_ORIGIN_LLM_FALLBACK = "llm_fallback"
TRANSLATION_ORIGIN_SKIPPED = "skipped"
TRANSLATION_ORIGIN_DISABLED = "disabled"
TRANSLATION_ORIGIN_UNAVAILABLE = "unavailable"
TRANSLATION_ORIGIN_ERROR = "error"


class SummarizationError(RuntimeError):
    """Raised when the LLM summarization step fails."""


def _llm_available() -> bool:
    settings = get_settings()
    key = settings.openai_api_key.strip()
    return bool(key) and key not in PLACEHOLDER_API_KEYS


def _normalize_whitespace(text: str) -> str:
    """Collapse repeated whitespace for cleaner outputs."""

    return WHITESPACE_PATTERN.sub(" ", text).strip()


def _looks_like_portuguese(text: str) -> bool:
    """Heuristic language check to skip translation when already in Portuguese."""

    cleaned = _normalize_whitespace(text).lower()
    if len(cleaned) < 40:
        return False

    words = PORTUGUESE_WORD_RE.findall(cleaned)
    if len(words) < 5:
        return False

    stopword_hits = sum(1 for word in words if word in PORTUGUESE_STRONG_STOPWORDS)
    stopword_ratio = stopword_hits / max(1, len(words))

    # Be conservative: only skip translation when we have enough Portuguese stopwords.
    return stopword_hits >= 3 and stopword_ratio >= 0.08


def _content_to_text(content: Any) -> str:
    """Convert LangChain response content into a plain string."""

    if content is None:
        return ""

    if isinstance(content, str):
        return _normalize_whitespace(content)

    if isinstance(content, Sequence):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                text = _normalize_whitespace(item)
                if text:
                    parts.append(text)
                continue
            if isinstance(item, Mapping):
                for key in ("text", "content"):
                    value = item.get(key)
                    if isinstance(value, str):
                        text = _normalize_whitespace(value)
                        if text:
                            parts.append(text)
                        break
        return _normalize_whitespace(" ".join(parts))

    return _normalize_whitespace(str(content))


def _truncate_to_word_limit(text: str, max_words: int) -> str:
    """Trim text to at most max_words, preferring sentence boundaries."""

    words = text.split()
    if len(words) <= max_words:
        return text.strip()

    truncated_words = words[:max_words]
    truncated_text = " ".join(truncated_words).strip()

    sentences = SENTENCE_SPLIT_PATTERN.split(truncated_text)
    if len(sentences) > 1:
        candidate = " ".join(sentences[:-1]).strip()
        if candidate and len(candidate.split()) >= max(1, int(max_words * 0.6)):
            truncated_text = candidate

    truncated_text = truncated_text.rstrip(" ,;:-")
    if not truncated_text.endswith((".", "!", "?")):
        truncated_text = f"{truncated_text}."

    return truncated_text


def _fallback_summary(text: str, word_count: int) -> str:
    """Generate a simple extractive summary without the LLM."""

    cleaned = _normalize_whitespace(text)
    if not cleaned:
        raise SummarizationError("No content available to summarize.")

    sentences = SENTENCE_SPLIT_PATTERN.split(cleaned)
    if sentences:
        candidate = " ".join(sentences[: min(len(sentences), 5)])
    else:
        candidate = cleaned

    return _truncate_to_word_limit(candidate, word_count)


def _build_llm(model: str | None = None):
    return build_llm(model=model)


def _get_fallback_model() -> str | None:
    settings = get_settings()
    fallback = settings.openai_fallback_model.strip()
    if not fallback:
        return None
    if fallback == settings.openai_model:
        return None
    return fallback


def _invoke_llm(messages: Iterable[SystemMessage | HumanMessage], model: str | None = None) -> str:
    llm = _build_llm(model=model)
    try:
        response = llm.invoke(list(messages))
    except Exception as exc:  # pragma: no cover - defensive; covered via route tests with mocks.
        logger.exception("LLM invocation failed")
        raise SummarizationError("Failed to summarize content with the LLM.") from exc

    text = _content_to_text(response.content)
    if not text:
        raise SummarizationError("The LLM returned an empty response.")
    return text


def _invoke_with_fallback(
    messages: Iterable[SystemMessage | HumanMessage],
    *,
    primary_origin: str,
    fallback_origin: str,
) -> tuple[str, str]:
    settings = get_settings()
    try:
        return _invoke_llm(messages, model=settings.openai_model), primary_origin
    except SummarizationError:
        fallback_model = _get_fallback_model()
        if not fallback_model:
            raise

        logger.warning("Primary LLM failed; retrying with fallback model '%s'.", fallback_model)
        return _invoke_llm(messages, model=fallback_model), fallback_origin


def summarize_text(text: str, word_count: int) -> tuple[str, str]:
    """Summarize text using LangChain + OpenAI with a deterministic prompt."""

    if not _llm_available():
        logger.warning("OPENAI_API_KEY missing or placeholder; using fallback summarizer.")
        return _fallback_summary(text, word_count), SUMMARY_ORIGIN_FALLBACK

    system_prompt = load_prompt("summary_system.md")
    human_prompt = load_prompt("summary_human.md")

    messages: Iterable[SystemMessage | HumanMessage] = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_prompt.format(word_count=word_count, text=text)),
    ]

    try:
        summary, origin = _invoke_with_fallback(
            messages,
            primary_origin=SUMMARY_ORIGIN_LLM,
            fallback_origin=SUMMARY_ORIGIN_LLM_FALLBACK,
        )
    except SummarizationError:
        logger.exception("LLM summarization failed; using fallback summarizer.")
        return _fallback_summary(text, word_count), SUMMARY_ORIGIN_FALLBACK
    return _truncate_to_word_limit(summary, word_count), origin


def translate_summary_to_portuguese(summary_en: str, word_count: int) -> tuple[str | None, str]:
    """Translate an English summary into Portuguese while keeping facts intact."""

    settings = get_settings()

    if not settings.enable_portuguese_translation:
        logger.info("Portuguese translation disabled by configuration.")
        return None, TRANSLATION_ORIGIN_DISABLED

    if _looks_like_portuguese(summary_en):
        # Preserve the original text so the API keeps a consistent summary payload.
        return summary_en, TRANSLATION_ORIGIN_SKIPPED

    if not _llm_available():
        logger.warning("OPENAI_API_KEY missing or placeholder; skipping translation.")
        return None, TRANSLATION_ORIGIN_UNAVAILABLE

    system_prompt = load_prompt("translation_system.md")
    human_prompt = load_prompt("translation_human.md")

    messages: Iterable[SystemMessage | HumanMessage] = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_prompt.format(word_count=word_count, summary=summary_en)),
    ]

    try:
        translated, origin = _invoke_with_fallback(
            messages,
            primary_origin=TRANSLATION_ORIGIN_LLM,
            fallback_origin=TRANSLATION_ORIGIN_LLM_FALLBACK,
        )
    except SummarizationError as exc:
        logger.exception("LLM translation failed.")
        raise SummarizationError("Failed to translate summary with the LLM.") from exc
    return _truncate_to_word_limit(translated, word_count), origin
