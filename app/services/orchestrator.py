from __future__ import annotations

import logging
from typing import Literal, cast

from sqlalchemy.orm import Session

from app.db.models import Summary
from app.repositories import summaries as summaries_repo
from app.services.summarizer import (
    TRANSLATION_ORIGIN_ERROR,
    SummarizationError,
    summarize_text,
    translate_summary_to_portuguese,
)
from app.services.wikipedia import (
    ScrapingError,
    URLValidationError,
    get_wikipedia_article_text,
    normalize_wikipedia_url,
)

logger = logging.getLogger(__name__)

SourceLiteral = Literal["generated", "cache"]


class OrchestratorError(RuntimeError):
    """Base error for orchestrator failures."""


class InvalidInputError(OrchestratorError):
    """Raised when input validation fails (URL, word count)."""


class UpstreamServiceError(OrchestratorError):
    """Raised when dependent services (Wikipedia, LLM) fail."""


class SummaryOrchestrator:
    """Orchestrates the flow of creating and retrieving summaries."""

    def __init__(self, session: Session):
        self.session = session

    def _normalize_url(self, url: str) -> str:
        try:
            return normalize_wikipedia_url(url)
        except URLValidationError as exc:
            raise InvalidInputError(str(exc)) from exc

    def get_summary_by_url(self, url: str, word_count: int | None = None) -> Summary | None:
        """Retrieve a cached summary."""
        normalized = self._normalize_url(url)

        if word_count is None:
            return cast(
                Summary | None,
                summaries_repo.get_latest_by_url(self.session, normalized),
            )

        return cast(
            Summary | None,
            summaries_repo.get_by_url_and_word_count(self.session, normalized, word_count),
        )

    def get_or_create_summary(self, url: str, word_count: int) -> tuple[Summary, SourceLiteral]:
        """Get existing summary or generate a new one."""
        normalized_url = self._normalize_url(url)

        # 1. Check Cache
        existing = summaries_repo.get_by_url_and_word_count(
            self.session, normalized_url, word_count
        )
        if existing is not None:
            logger.info("Orchestrator: Returning cached summary for %s", normalized_url)
            return cast(Summary, existing), "cache"

        # 2. Scrape Wikipedia
        try:
            article_text = get_wikipedia_article_text(normalized_url)
        except URLValidationError as exc:
            raise InvalidInputError(str(exc)) from exc
        except ScrapingError as exc:
            raise UpstreamServiceError(f"Wikipedia scraping failed: {exc}") from exc

        # 3. Summarize
        try:
            summary_text, origin = summarize_text(article_text, word_count)
        except SummarizationError as exc:
            raise UpstreamServiceError(f"LLM processing failed: {exc}") from exc

        # 4. Translate (best-effort)
        try:
            summary_pt, pt_origin = translate_summary_to_portuguese(summary_text, word_count)
        except SummarizationError:
            logger.warning(
                "Portuguese translation failed; returning summary without translation.",
                exc_info=True,
            )
            summary_pt = None
            pt_origin = TRANSLATION_ORIGIN_ERROR

        # 5. Save to Repo
        summary_obj, created_new = summaries_repo.create_summary(
            self.session,
            url=normalized_url,
            summary_text=summary_text,
            summary_pt=summary_pt,
            word_count=word_count,
            summary_origin=origin,
            summary_pt_origin=pt_origin,
        )

        source: SourceLiteral = "generated" if created_new else "cache"
        logger.info("Orchestrator: %s summary for %s", source.capitalize(), normalized_url)

        return cast(Summary, summary_obj), source
