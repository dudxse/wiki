from __future__ import annotations

import logging
import re
from urllib.parse import SplitResult, parse_qs, quote, urljoin, urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup
from bs4.element import Tag

from app.core.config import get_settings

logger = logging.getLogger(__name__)

REFERENCE_PATTERN = re.compile(r"\[\d+\]")
WHITESPACE_PATTERN = re.compile(r"\s+")
REMOVAL_SELECTORS: tuple[str, ...] = (
    "table.infobox",
    "table.navbox",
    "table.vertical-navbox",
    "table.sidebar",
    "div.navbox",
    "div.reflist",
    "ol.references",
    "sup.reference",
    "span.reference",
    "style",
    "script",
)


class URLValidationError(ValueError):
    """Raised when a provided URL is not a valid Wikipedia URL."""


class ScrapingError(RuntimeError):
    """Raised when scraping fails or yields insufficient content."""


def _validate_parsed_url(parsed: SplitResult) -> None:
    """Validate scheme and domain for Wikipedia URLs."""

    if parsed.scheme not in {"http", "https"}:
        raise URLValidationError("URL must start with http:// or https://.")

    hostname = parsed.hostname
    if not hostname:
        raise URLValidationError("URL must include a valid hostname.")

    host = hostname.lower()
    is_wikipedia = host == "wikipedia.org" or host.endswith(".wikipedia.org")
    if not is_wikipedia:
        raise URLValidationError("URL must belong to wikipedia.org.")


def normalize_wikipedia_url(url: str) -> str:
    """Validate and normalize a Wikipedia URL to reduce obvious duplicates."""

    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        raise URLValidationError("URL is not valid.") from exc

    _validate_parsed_url(parsed)

    scheme = "https"
    hostname = (parsed.hostname or "").lower()
    port = parsed.port

    netloc = hostname
    if port and port not in {80, 443}:
        netloc = f"{hostname}:{port}"

    path = parsed.path or "/"
    query = parsed.query
    if path != "/" and path.endswith("/"):
        path = path[:-1]

    if path in {"/w/index.php", "/w/index.php/"} or path == "/":
        if query:
            params = parse_qs(query)
            title = params.get("title", [None])[0]
            if title:
                normalized_title = quote(title.replace(" ", "_"), safe="():'")
                path = f"/wiki/{normalized_title}"
                query = ""
        if path == "/" and query:
            raise URLValidationError("URL must point to a Wikipedia article.")

    if not path.startswith("/wiki/"):
        raise URLValidationError("URL must point to a Wikipedia article.")

    # Drop queries to avoid caching alternate views or revisions.
    query = ""

    # Fragments are intentionally dropped to avoid obvious duplicate URLs.
    normalized = urlunsplit((scheme, netloc, path, query, ""))
    return normalized


def _clean_text(text: str) -> str:
    """Remove reference markers and collapse whitespace."""

    text = REFERENCE_PATTERN.sub("", text)
    text = WHITESPACE_PATTERN.sub(" ", text)
    return text.strip()


def _read_response_limited(response: httpx.Response, max_bytes: int) -> str:
    """Read response content with a hard size limit."""

    if max_bytes <= 0:
        raise ScrapingError("Invalid max content size configuration.")

    content = bytearray()
    for chunk in response.iter_bytes():
        content.extend(chunk)
        if len(content) > max_bytes:
            raise ScrapingError("Wikipedia content exceeded the maximum allowed size.")

    encoding = response.encoding or "utf-8"
    return content.decode(encoding, errors="replace")


def _fetch_wikipedia_html(url: str) -> str:
    """Fetch Wikipedia HTML with redirect validation and size limits."""

    settings = get_settings()
    timeout = httpx.Timeout(settings.http_timeout_seconds)

    headers = {
        "User-Agent": settings.wikipedia_user_agent,
    }

    current_url = url
    max_redirects = settings.wikipedia_max_redirects
    if max_redirects < 0:
        raise ScrapingError("Invalid redirect configuration.")

    with httpx.Client(timeout=timeout, follow_redirects=False, headers=headers) as client:
        for _ in range(max_redirects + 1):
            try:
                with client.stream("GET", current_url) as response:
                    if response.is_redirect:
                        location = response.headers.get("Location")
                        if not location:
                            raise ScrapingError("Redirect response missing Location header.")

                        next_url = urljoin(current_url, location)
                        normalized = normalize_wikipedia_url(next_url)
                        current_url = normalized
                        continue

                    response.raise_for_status()
                    return _read_response_limited(response, settings.wikipedia_max_content_bytes)
            except URLValidationError:
                raise
            except httpx.HTTPError as exc:
                logger.exception("Failed to fetch Wikipedia URL: %s", current_url)
                raise ScrapingError("Failed to fetch Wikipedia content.") from exc

    raise ScrapingError("Too many redirects when fetching Wikipedia content.")


def get_wikipedia_article_text(url: str) -> str:
    """Fetch and extract the main article text from a Wikipedia page."""
    settings = get_settings()
    normalized_url = normalize_wikipedia_url(url)
    html = _fetch_wikipedia_html(normalized_url)
    soup = BeautifulSoup(html, "html.parser")

    content = soup.select_one("div#mw-content-text div.mw-parser-output")
    if not isinstance(content, Tag):
        content = soup.find("div", id="mw-content-text")
    if not isinstance(content, Tag):
        raise ScrapingError("Could not locate the main article content.")

    for selector in REMOVAL_SELECTORS:
        for element in content.select(selector):
            element.decompose()

    paragraphs = [
        paragraph.get_text(" ", strip=True)
        for paragraph in content.find_all("p")
        if paragraph.get_text(" ", strip=True)
    ]

    article_text = _clean_text(" ".join(paragraphs))
    article_word_count = len(article_text.split())
    if article_word_count < settings.wikipedia_min_article_words:
        logger.warning("Extracted text too short (%s words) for URL: %s", article_word_count, url)
        raise ScrapingError("Could not extract enough article text to summarize.")

    return article_text
