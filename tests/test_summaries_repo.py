from __future__ import annotations

import _bootstrap  # noqa: F401
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import Summary
from app.repositories import summaries as summaries_repo

TEST_URL = "https://en.wikipedia.org/wiki/Artificial_intelligence"


def test_create_summary_handles_integrity_error() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
        class_=Session,
    )

    Base.metadata.create_all(bind=engine)

    session = TestingSessionLocal()
    try:
        existing = Summary(
            url=TEST_URL,
            summary="Existing summary",
            summary_pt=None,
            word_count=50,
            summary_origin="llm",
            summary_pt_origin="disabled",
        )
        session.add(existing)
        session.commit()

        summary, created = summaries_repo.create_summary(
            session,
            url=TEST_URL,
            summary_text="New summary",
            summary_pt=None,
            word_count=50,
            summary_origin="llm",
            summary_pt_origin="disabled",
        )

        assert created is False
        assert summary.id == existing.id
        assert summary.summary == existing.summary
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
