from __future__ import annotations

import _bootstrap  # noqa: F401
import pytest

from app.core.config import get_settings
from app.services.summarizer import (
    TRANSLATION_ORIGIN_DISABLED,
    TRANSLATION_ORIGIN_LLM,
    TRANSLATION_ORIGIN_SKIPPED,
    TRANSLATION_ORIGIN_UNAVAILABLE,
    SummarizationError,
    translate_summary_to_portuguese,
)


def test_translate_skips_when_summary_is_already_portuguese() -> None:
    summary_pt = (
        "A inteligencia artificial e um campo da computacao que busca criar "
        "sistemas capazes de aprender, raciocinar e tomar decisoes com base em dados."
    )

    translated, origin = translate_summary_to_portuguese(summary_pt, word_count=80)

    assert translated == summary_pt
    assert origin == TRANSLATION_ORIGIN_SKIPPED


def test_translate_returns_disabled_when_flag_off(monkeypatch: pytest.MonkeyPatch) -> None:
    summary_en = "This is an English summary that should not be translated. " * 3
    monkeypatch.setenv("ENABLE_PORTUGUESE_TRANSLATION", "false")
    get_settings.cache_clear()

    try:
        translated, origin = translate_summary_to_portuguese(summary_en, word_count=80)
        assert translated is None
        assert origin == TRANSLATION_ORIGIN_DISABLED
    finally:
        get_settings.cache_clear()


def test_translate_returns_unavailable_when_key_placeholder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    summary_en = "This is an English summary that should not be translated. " * 3
    monkeypatch.setenv("OPENAI_API_KEY", "your-openai-api-key")
    get_settings.cache_clear()

    try:
        translated, origin = translate_summary_to_portuguese(summary_en, word_count=80)
        assert translated is None
        assert origin == TRANSLATION_ORIGIN_UNAVAILABLE
    finally:
        get_settings.cache_clear()


def test_translate_raises_when_llm_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    summary_en = "This is an English summary that triggers an LLM failure. " * 3

    def raise_error(*args: object, **kwargs: object) -> tuple[str, str]:
        raise SummarizationError("boom")

    monkeypatch.setattr("app.services.summarizer._invoke_with_fallback", raise_error)

    with pytest.raises(SummarizationError):
        translate_summary_to_portuguese(summary_en, word_count=80)


def test_translate_does_not_skip_for_english_with_names(monkeypatch: pytest.MonkeyPatch) -> None:
    summary_en = (
        "The congress met in Hanoi and reviewed the previous term, "
        "electing a new committee. Delegates discussed reforms led by Nguyen "
        "Phu Trong and other leaders during the session. The report was read "
        "by members of the presidium and approved by vote."
    )

    def fake_invoke(*args: object, **kwargs: object) -> tuple[str, str]:
        return "Resumo em portugues gerado.", TRANSLATION_ORIGIN_LLM

    monkeypatch.setattr("app.services.summarizer._invoke_with_fallback", fake_invoke)

    translated, origin = translate_summary_to_portuguese(summary_en, word_count=80)

    assert translated is not None
    assert origin == TRANSLATION_ORIGIN_LLM
