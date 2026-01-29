from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Summary


def get_by_url_and_word_count(session: Session, url: str, word_count: int) -> Summary | None:
    """Return a summary by URL and requested word count, if it exists."""

    statement = select(Summary).where(Summary.url == url, Summary.word_count == word_count)
    return session.scalar(statement)


def get_latest_by_url(session: Session, url: str) -> Summary | None:
    """Return the most recent summary for a URL."""

    statement = select(Summary).where(Summary.url == url).order_by(desc(Summary.id)).limit(1)
    return session.scalar(statement)


def update_summary_pt(
    session: Session,
    summary_obj: Summary,
    summary_pt: str | None,
    summary_pt_origin: str,
) -> Summary:
    """Persist a Portuguese translation (or status) for an existing summary."""

    summary_obj.summary_pt = summary_pt
    summary_obj.summary_pt_origin = summary_pt_origin
    session.add(summary_obj)
    session.commit()
    session.refresh(summary_obj)
    return summary_obj


def create_summary(
    session: Session,
    url: str,
    summary_text: str,
    summary_pt: str | None,
    word_count: int,
    summary_origin: str,
    summary_pt_origin: str,
) -> tuple[Summary, bool]:
    """Create a new summary, handling concurrent inserts safely.

    Returns a tuple of (summary, created_new).
    """

    summary = Summary(
        url=url,
        summary=summary_text,
        summary_pt=summary_pt,
        word_count=word_count,
        summary_origin=summary_origin,
        summary_pt_origin=summary_pt_origin,
    )
    session.add(summary)

    try:
        session.commit()
        session.refresh(summary)
        return summary, True
    except IntegrityError:
        session.rollback()
        existing = get_by_url_and_word_count(session, url, word_count)
        if existing is None:
            raise
        return existing, False
