from __future__ import annotations

import _bootstrap  # noqa: F401
import httpx
import pytest

from app.core.config import get_settings
from app.services.wikipedia import (
    ScrapingError,
    URLValidationError,
    get_wikipedia_article_text,
    normalize_wikipedia_url,
)


def test_normalize_url_removes_fragment_and_trailing_slash() -> None:
    url = "https://EN.WIKIPEDIA.ORG/wiki/Artificial_intelligence/#History"

    normalized = normalize_wikipedia_url(url)

    assert normalized == "https://en.wikipedia.org/wiki/Artificial_intelligence"


def test_normalize_url_accepts_root_domain() -> None:
    url = "https://wikipedia.org/wiki/Artificial_intelligence"

    normalized = normalize_wikipedia_url(url)

    assert normalized == url


def test_normalize_url_forces_https() -> None:
    url = "http://en.wikipedia.org/wiki/Artificial_intelligence"

    normalized = normalize_wikipedia_url(url)

    assert normalized == "https://en.wikipedia.org/wiki/Artificial_intelligence"


def test_normalize_url_rejects_non_wikipedia() -> None:
    with pytest.raises(URLValidationError):
        normalize_wikipedia_url("https://example.com/wiki/AI")


def test_normalize_url_converts_index_php() -> None:
    url = "https://en.wikipedia.org/w/index.php?title=Artificial_intelligence"

    normalized = normalize_wikipedia_url(url)

    assert normalized == "https://en.wikipedia.org/wiki/Artificial_intelligence"


def test_fetch_rejects_redirect_to_non_wikipedia(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=302,
            headers={"Location": "https://example.com/wiki/AI"},
        )

    transport = httpx.MockTransport(handler)

    original_client = httpx.Client

    def client_factory(*args: object, **kwargs: object) -> httpx.Client:
        kwargs["transport"] = transport
        return original_client(*args, **kwargs)

    monkeypatch.setattr("app.services.wikipedia.httpx.Client", client_factory)

    with pytest.raises(URLValidationError):
        get_wikipedia_article_text("https://en.wikipedia.org/wiki/Artificial_intelligence")


def test_fetch_rejects_oversized_content(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, content=b"x" * 64)

    transport = httpx.MockTransport(handler)

    original_client = httpx.Client

    def client_factory(*args: object, **kwargs: object) -> httpx.Client:
        kwargs["transport"] = transport
        return original_client(*args, **kwargs)

    monkeypatch.setattr("app.services.wikipedia.httpx.Client", client_factory)
    monkeypatch.setenv("WIKIPEDIA_MAX_CONTENT_BYTES", "16")
    get_settings.cache_clear()

    try:
        with pytest.raises(ScrapingError):
            get_wikipedia_article_text("https://en.wikipedia.org/wiki/Artificial_intelligence")
    finally:
        get_settings.cache_clear()
