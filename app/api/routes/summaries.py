from __future__ import annotations

import logging
from typing import Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.ratelimit import limit
from app.db.models import Summary
from app.db.session import get_session
from app.schemas.summary import SummaryCreate, SummaryResponse
from app.services.orchestrator import (
    InvalidInputError,
    SummaryOrchestrator,
    UpstreamServiceError,
)

router = APIRouter(prefix="/summaries", tags=["summaries"])
logger = logging.getLogger(__name__)
settings = get_settings()

SourceLiteral = Literal["generated", "cache"]


def _build_response(summary_obj: Summary, source: SourceLiteral) -> SummaryResponse:
    return SummaryResponse(
        url=summary_obj.url,
        word_count=summary_obj.word_count,
        actual_word_count=len(summary_obj.summary.split()),
        summary=summary_obj.summary,
        summary_pt=summary_obj.summary_pt,
        summary_origin=summary_obj.summary_origin,
        summary_pt_origin=summary_obj.summary_pt_origin,
        source=source,
        created_at=summary_obj.created_at,
    )


@router.post(
    "",
    response_model=SummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Create or reuse a Wikipedia summary",
)
@limit(settings.rate_limit_post_summaries)
def create_summary(
    request: Request,
    payload: SummaryCreate,
    session: Session = Depends(get_session),
) -> SummaryResponse:
    if payload.word_count > settings.summary_word_count_max:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"word_count must be <= {settings.summary_word_count_max}.",
        )

    orchestrator = SummaryOrchestrator(session)
    try:
        summary_obj, source = orchestrator.get_or_create_summary(payload.url, payload.word_count)
    except InvalidInputError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except UpstreamServiceError as exc:
        # 502 Bad Gateway is appropriate for downstream failures (Wikipedia/OpenAI)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    return _build_response(cast(Summary, summary_obj), source)


@router.get(
    "",
    response_model=SummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a cached Wikipedia summary by URL",
)
@limit(settings.rate_limit_get_summaries)
def get_summary(
    request: Request,
    url: str = Query(
        ...,
        description="Wikipedia URL to retrieve.",
        examples=["https://en.wikipedia.org/wiki/Artificial_intelligence"],
    ),
    word_count: int | None = Query(
        None,
        gt=0,
        description="Requested word count. If omitted, returns the most recent summary for the URL.",
        examples=[200],
    ),
    session: Session = Depends(get_session),
) -> SummaryResponse:
    orchestrator = SummaryOrchestrator(session)
    try:
        existing = orchestrator.get_summary_by_url(url, word_count)
    except InvalidInputError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Summary not found for the provided URL.",
        )

    logger.info("Returning cached summary for URL: %s", existing.url)
    return _build_response(cast(Summary, existing), "cache")
