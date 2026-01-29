from __future__ import annotations

import hashlib
import json
import logging
import random
import re
import time
from typing import Any, Iterable, Mapping, Sequence

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.config import get_settings
from app.llm.client import build_llm
from app.llm.prompt_loader import load_prompt

logger = logging.getLogger(__name__)

SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")
WHITESPACE_PATTERN = re.compile(r"\s+")
JSON_OBJECT_PATTERN = re.compile(r"\{.*\}", re.DOTALL)
PLACEHOLDER_API_KEYS = {"your-openai-api-key"}
PORTUGUESE_WORD_RE = re.compile(r"[a-záàâãéêíóôõúç]+", re.IGNORECASE)
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

MAP_REDUCE_THRESHOLD_WORDS = 1200
MAP_CHUNK_WORDS = 800
MAP_MIN_SUMMARY_WORDS = 60
MAP_MAX_SUMMARY_WORDS = 200

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


def _strip_code_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
        if cleaned.endswith("```"):
            cleaned = cleaned[: -len("```")].strip()
    return cleaned


def _try_parse_json(text: str) -> dict[str, Any] | None:
    cleaned = _strip_code_fences(text)
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    match = JSON_OBJECT_PATTERN.search(cleaned)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        return None
    return None


def _extract_json_field(text: str, field: str) -> str | None:
    data = _try_parse_json(text)
    if not data:
        return None
    value = data.get(field)
    if isinstance(value, str) and value.strip():
        return _normalize_whitespace(value)
    return None


def _format_instructions(field: str) -> str:
    example = json.dumps({field: "..."}, ensure_ascii=False)
    return f'Return only JSON with a single key "{field}". Example: {example}.'


def _prompt_version(system_prompt: str, human_prompt: str, format_instructions: str) -> str:
    payload = "\n".join([system_prompt, human_prompt, format_instructions])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8]


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


def _split_text_into_chunks(text: str, max_words: int) -> list[str]:
    words = text.split()
    if not words:
        return []
    chunks: list[str] = []
    for idx in range(0, len(words), max_words):
        chunk_words = words[idx : idx + max_words]
        if chunk_words:
            chunks.append(" ".join(chunk_words))
    return chunks


def _map_chunk_word_target(final_word_count: int, chunk_count: int) -> int:
    if chunk_count <= 0:
        return final_word_count
    target = int(final_word_count * 1.5 / chunk_count)
    target = max(MAP_MIN_SUMMARY_WORDS, target)
    return min(MAP_MAX_SUMMARY_WORDS, target)


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


def _build_summary_messages(
    *,
    text: str | None,
    summaries: str | None,
    word_count: int,
    mode: str,
    chunk_index: int | None = None,
    total_chunks: int | None = None,
) -> tuple[list[SystemMessage | HumanMessage], str]:
    system_prompt = load_prompt("summary_system.md")
    format_instructions = _format_instructions("summary")

    if mode == "map":
        human_template = load_prompt("summary_map_human.md")
        human_prompt = human_template.format(
            word_count=word_count,
            text=text or "",
            chunk_index=chunk_index or 1,
            total_chunks=total_chunks or 1,
            format_instructions=format_instructions,
        )
    elif mode == "reduce":
        human_template = load_prompt("summary_reduce_human.md")
        human_prompt = human_template.format(
            word_count=word_count,
            summaries=summaries or "",
            format_instructions=format_instructions,
        )
    else:
        human_template = load_prompt("summary_human.md")
        human_prompt = human_template.format(
            word_count=word_count,
            text=text or "",
            format_instructions=format_instructions,
        )

    prompt_version = _prompt_version(system_prompt, human_template, format_instructions)
    messages: list[SystemMessage | HumanMessage] = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_prompt),
    ]
    return messages, prompt_version


def _build_translation_messages(
    *,
    summary: str,
    word_count: int,
) -> tuple[list[SystemMessage | HumanMessage], str]:
    system_prompt = load_prompt("translation_system.md")
    human_template = load_prompt("translation_human.md")
    format_instructions = _format_instructions("translation")
    human_prompt = human_template.format(
        word_count=word_count,
        summary=summary,
        format_instructions=format_instructions,
    )
    prompt_version = _prompt_version(system_prompt, human_template, format_instructions)
    messages: list[SystemMessage | HumanMessage] = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_prompt),
    ]
    return messages, prompt_version


def _extract_structured_text(raw_text: str, field: str, *, purpose: str) -> str:
    extracted = _extract_json_field(raw_text, field)
    if extracted is not None:
        return extracted
    logger.warning(
        "LLM output missing JSON field '%s' (purpose=%s); using raw text.",
        field,
        purpose,
    )
    return _normalize_whitespace(raw_text)


def _invoke_llm(
    messages: Iterable[SystemMessage | HumanMessage],
    *,
    model: str | None,
    purpose: str,
    prompt_version: str,
) -> str:
    settings = get_settings()
    model_name = model or settings.openai_model
    max_retries = max(0, settings.llm_max_retries)
    max_attempts = max(1, max_retries + 1)
    backoff_base = max(0.0, settings.llm_retry_backoff_seconds)
    llm = _build_llm(model=model_name)

    for attempt in range(1, max_attempts + 1):
        start = time.perf_counter()
        try:
            response = llm.invoke(list(messages))
            duration = time.perf_counter() - start
            logger.info(
                "LLM call succeeded (purpose=%s model=%s attempt=%s duration=%.2fs prompt=%s)",
                purpose,
                model_name,
                attempt,
                duration,
                prompt_version,
            )
            text = _content_to_text(response.content)
            if not text:
                raise SummarizationError("The LLM returned an empty response.")
            return text
        except (
            Exception
        ) as exc:  # pragma: no cover - defensive; covered via route tests with mocks.
            duration = time.perf_counter() - start
            logger.warning(
                "LLM call failed (purpose=%s model=%s attempt=%s duration=%.2fs prompt=%s). Error: %s",
                purpose,
                model_name,
                attempt,
                duration,
                prompt_version,
                exc,
            )
            if attempt >= max_attempts:
                logger.exception("LLM invocation failed")
                raise SummarizationError("Failed to summarize content with the LLM.") from exc

            if backoff_base > 0:
                jitter = 0.8 + random.random() * 0.4
                time.sleep(backoff_base * (2 ** (attempt - 1)) * jitter)

    raise SummarizationError("LLM invocation failed after retries")


def _invoke_with_fallback(
    messages: Iterable[SystemMessage | HumanMessage],
    *,
    primary_origin: str,
    fallback_origin: str,
    purpose: str,
    prompt_version: str,
) -> tuple[str, str]:
    settings = get_settings()
    try:
        return (
            _invoke_llm(
                messages,
                model=settings.openai_model,
                purpose=purpose,
                prompt_version=prompt_version,
            ),
            primary_origin,
        )
    except SummarizationError:
        fallback_model = _get_fallback_model()
        if not fallback_model:
            raise

        logger.warning("Primary LLM failed; retrying with fallback model '%s'.", fallback_model)
        return (
            _invoke_llm(
                messages,
                model=fallback_model,
                purpose=purpose,
                prompt_version=prompt_version,
            ),
            fallback_origin,
        )


def _summarize_single_pass(text: str, word_count: int) -> tuple[str, str]:
    messages, prompt_version = _build_summary_messages(
        text=text,
        summaries=None,
        word_count=word_count,
        mode="single",
    )
    raw_summary, origin = _invoke_with_fallback(
        messages,
        primary_origin=SUMMARY_ORIGIN_LLM,
        fallback_origin=SUMMARY_ORIGIN_LLM_FALLBACK,
        purpose="summary",
        prompt_version=prompt_version,
    )
    summary = _extract_structured_text(raw_summary, "summary", purpose="summary")
    return _truncate_to_word_limit(summary, word_count), origin


def _summarize_map_reduce(text: str, word_count: int) -> tuple[str, str]:
    cleaned = _normalize_whitespace(text)
    chunks = _split_text_into_chunks(cleaned, MAP_CHUNK_WORDS)
    if len(chunks) <= 1:
        return _summarize_single_pass(cleaned, word_count)

    chunk_target = _map_chunk_word_target(word_count, len(chunks))
    partials: list[str] = []
    origins: list[str] = []

    for idx, chunk in enumerate(chunks, start=1):
        messages, prompt_version = _build_summary_messages(
            text=chunk,
            summaries=None,
            word_count=chunk_target,
            mode="map",
            chunk_index=idx,
            total_chunks=len(chunks),
        )
        raw_summary, origin = _invoke_with_fallback(
            messages,
            primary_origin=SUMMARY_ORIGIN_LLM,
            fallback_origin=SUMMARY_ORIGIN_LLM_FALLBACK,
            purpose="summary-map",
            prompt_version=prompt_version,
        )
        summary = _extract_structured_text(raw_summary, "summary", purpose="summary-map")
        partials.append(_truncate_to_word_limit(summary, chunk_target))
        origins.append(origin)

    combined = "\n\n".join(partials)
    messages, prompt_version = _build_summary_messages(
        text=None,
        summaries=combined,
        word_count=word_count,
        mode="reduce",
    )
    raw_summary, origin = _invoke_with_fallback(
        messages,
        primary_origin=SUMMARY_ORIGIN_LLM,
        fallback_origin=SUMMARY_ORIGIN_LLM_FALLBACK,
        purpose="summary-reduce",
        prompt_version=prompt_version,
    )
    summary = _extract_structured_text(raw_summary, "summary", purpose="summary-reduce")

    if any(step_origin == SUMMARY_ORIGIN_LLM_FALLBACK for step_origin in origins + [origin]):
        final_origin = SUMMARY_ORIGIN_LLM_FALLBACK
    else:
        final_origin = SUMMARY_ORIGIN_LLM

    return _truncate_to_word_limit(summary, word_count), final_origin


def summarize_text(text: str, word_count: int) -> tuple[str, str]:
    """Summarize text using LangChain + OpenAI with a deterministic prompt."""

    if not _llm_available():
        logger.warning("OPENAI_API_KEY missing or placeholder; using fallback summarizer.")
        return _fallback_summary(text, word_count), SUMMARY_ORIGIN_FALLBACK

    try:
        cleaned = _normalize_whitespace(text)
        if len(cleaned.split()) >= MAP_REDUCE_THRESHOLD_WORDS:
            summary, origin = _summarize_map_reduce(cleaned, word_count)
        else:
            summary, origin = _summarize_single_pass(cleaned, word_count)
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

    try:
        messages, prompt_version = _build_translation_messages(
            summary=summary_en,
            word_count=word_count,
        )
        raw_translation, origin = _invoke_with_fallback(
            messages,
            primary_origin=TRANSLATION_ORIGIN_LLM,
            fallback_origin=TRANSLATION_ORIGIN_LLM_FALLBACK,
            purpose="translation",
            prompt_version=prompt_version,
        )
    except SummarizationError as exc:
        logger.exception("LLM translation failed.")
        raise SummarizationError("Failed to translate summary with the LLM.") from exc
    translated = _extract_structured_text(raw_translation, "translation", purpose="translation")
    return _truncate_to_word_limit(translated, word_count), origin
