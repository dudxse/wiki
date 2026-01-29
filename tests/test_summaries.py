from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timezone
from unittest.mock import Mock

import _bootstrap  # noqa: F401
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import Summary
from app.db.session import get_session
from app.main import app
from app.services.summarizer import SummarizationError
from app.services.wikipedia import ScrapingError

TEST_URL = "https://en.wikipedia.org/wiki/Artificial_intelligence"
TEST_TEXT = " ".join(["Artificial intelligence enables machines to learn."] * 80)
TEST_SUMMARY = "Artificial intelligence is the field of building systems that learn, reason, and act based on data."
TEST_SUMMARY_PT = "Inteligência artificial é o campo de construir sistemas que aprendem, raciocinam e agem com base em dados."
TEST_SUMMARY_WORD_COUNT = len(TEST_SUMMARY.split())
TEST_SUMMARY_ORIGIN = "llm"
TEST_SUMMARY_PT_ORIGIN = "llm"


@pytest.fixture()
def db_session_factory() -> Generator[sessionmaker[Session], None, None]:
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

    def override_get_session() -> Generator[Session, None, None]:
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = override_get_session
    try:
        yield TestingSessionLocal
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def client(db_session_factory: sessionmaker[Session]) -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


def test_post_creates_summary_with_mocks(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock_scrape = Mock(return_value=TEST_TEXT)
    mock_summarize = Mock(return_value=(TEST_SUMMARY, TEST_SUMMARY_ORIGIN))
    mock_translate = Mock(return_value=(TEST_SUMMARY_PT, TEST_SUMMARY_PT_ORIGIN))

    monkeypatch.setattr("app.services.orchestrator.get_wikipedia_article_text", mock_scrape)
    monkeypatch.setattr("app.services.orchestrator.summarize_text", mock_summarize)
    monkeypatch.setattr("app.services.orchestrator.translate_summary_to_portuguese", mock_translate)

    response = client.post("/summaries", json={"url": TEST_URL, "word_count": 50})

    assert response.status_code == 200
    payload = response.json()
    assert payload["url"] == TEST_URL
    assert payload["word_count"] == 50
    assert payload["actual_word_count"] == TEST_SUMMARY_WORD_COUNT
    assert payload["summary_origin"] == TEST_SUMMARY_ORIGIN
    assert payload["summary_pt_origin"] == TEST_SUMMARY_PT_ORIGIN
    assert payload["source"] == "generated"
    assert payload["summary"] == TEST_SUMMARY
    assert payload["summary_pt"] == TEST_SUMMARY_PT

    mock_scrape.assert_called_once()
    mock_summarize.assert_called_once()
    mock_translate.assert_called_once()


def test_post_twice_uses_cache_and_skips_llm(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock_scrape = Mock(return_value=TEST_TEXT)
    mock_summarize = Mock(return_value=(TEST_SUMMARY, TEST_SUMMARY_ORIGIN))
    mock_translate = Mock(return_value=(TEST_SUMMARY_PT, TEST_SUMMARY_PT_ORIGIN))

    monkeypatch.setattr("app.services.orchestrator.get_wikipedia_article_text", mock_scrape)
    monkeypatch.setattr("app.services.orchestrator.summarize_text", mock_summarize)
    monkeypatch.setattr("app.services.orchestrator.translate_summary_to_portuguese", mock_translate)

    first = client.post("/summaries", json={"url": TEST_URL, "word_count": 60})
    second = client.post("/summaries", json={"url": TEST_URL, "word_count": 60})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["source"] == "generated"
    assert second.json()["source"] == "cache"
    assert first.json()["word_count"] == 60
    assert second.json()["word_count"] == 60
    assert first.json()["actual_word_count"] == TEST_SUMMARY_WORD_COUNT
    assert second.json()["actual_word_count"] == TEST_SUMMARY_WORD_COUNT
    assert first.json()["summary_origin"] == TEST_SUMMARY_ORIGIN
    assert second.json()["summary_origin"] == TEST_SUMMARY_ORIGIN
    assert first.json()["summary_pt_origin"] == TEST_SUMMARY_PT_ORIGIN
    assert second.json()["summary_pt_origin"] == TEST_SUMMARY_PT_ORIGIN

    mock_scrape.assert_called_once()
    mock_summarize.assert_called_once()
    mock_translate.assert_called_once()


def test_post_with_different_word_count_generates_new_summary(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_scrape = Mock(return_value=TEST_TEXT)
    mock_summarize = Mock(
        side_effect=[
            (TEST_SUMMARY, TEST_SUMMARY_ORIGIN),
            (f"{TEST_SUMMARY} second", TEST_SUMMARY_ORIGIN),
        ]
    )
    mock_translate = Mock(
        side_effect=[
            (TEST_SUMMARY_PT, TEST_SUMMARY_PT_ORIGIN),
            (f"{TEST_SUMMARY_PT} second", TEST_SUMMARY_PT_ORIGIN),
        ]
    )

    monkeypatch.setattr("app.services.orchestrator.get_wikipedia_article_text", mock_scrape)
    monkeypatch.setattr("app.services.orchestrator.summarize_text", mock_summarize)
    monkeypatch.setattr("app.services.orchestrator.translate_summary_to_portuguese", mock_translate)

    first = client.post("/summaries", json={"url": TEST_URL, "word_count": 40})
    second = client.post("/summaries", json={"url": TEST_URL, "word_count": 80})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["source"] == "generated"
    assert second.json()["source"] == "generated"
    assert first.json()["word_count"] == 40
    assert second.json()["word_count"] == 80
    assert first.json()["summary_origin"] == TEST_SUMMARY_ORIGIN
    assert second.json()["summary_origin"] == TEST_SUMMARY_ORIGIN
    assert first.json()["summary_pt_origin"] == TEST_SUMMARY_PT_ORIGIN
    assert second.json()["summary_pt_origin"] == TEST_SUMMARY_PT_ORIGIN

    assert mock_scrape.call_count == 2
    assert mock_summarize.call_count == 2
    assert mock_translate.call_count == 2


def test_get_returns_existing_summary(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    session = db_session_factory()
    try:
        session.add(
            Summary(
                url=TEST_URL,
                summary=TEST_SUMMARY,
                summary_pt=TEST_SUMMARY_PT,
                word_count=120,
                summary_origin=TEST_SUMMARY_ORIGIN,
                summary_pt_origin=TEST_SUMMARY_PT_ORIGIN,
                created_at=datetime.now(timezone.utc),
            )
        )
        session.commit()
    finally:
        session.close()

    response = client.get("/summaries", params={"url": TEST_URL})

    assert response.status_code == 200
    payload = response.json()
    assert payload["url"] == TEST_URL
    assert payload["summary"] == TEST_SUMMARY
    assert payload["summary_pt"] == TEST_SUMMARY_PT
    assert payload["source"] == "cache"
    assert payload["word_count"] == 120
    assert payload["actual_word_count"] == TEST_SUMMARY_WORD_COUNT
    assert payload["summary_origin"] == TEST_SUMMARY_ORIGIN
    assert payload["summary_pt_origin"] == TEST_SUMMARY_PT_ORIGIN


def test_get_returns_404_when_missing(client: TestClient) -> None:
    response = client.get("/summaries", params={"url": TEST_URL})

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_get_with_word_count_returns_specific_summary(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    session = db_session_factory()
    try:
        session.add_all(
            [
                Summary(
                    url=TEST_URL,
                    summary=TEST_SUMMARY,
                    summary_pt=TEST_SUMMARY_PT,
                    word_count=50,
                    summary_origin=TEST_SUMMARY_ORIGIN,
                    summary_pt_origin=TEST_SUMMARY_PT_ORIGIN,
                    created_at=datetime.now(timezone.utc),
                ),
                Summary(
                    url=TEST_URL,
                    summary=f"{TEST_SUMMARY} v2",
                    summary_pt=f"{TEST_SUMMARY_PT} v2",
                    word_count=100,
                    summary_origin=TEST_SUMMARY_ORIGIN,
                    summary_pt_origin=TEST_SUMMARY_PT_ORIGIN,
                    created_at=datetime.now(timezone.utc),
                ),
            ]
        )
        session.commit()
    finally:
        session.close()

    response = client.get("/summaries", params={"url": TEST_URL, "word_count": 100})

    assert response.status_code == 200
    payload = response.json()
    assert payload["word_count"] == 100
    assert payload["actual_word_count"] == len(payload["summary"].split())
    assert payload["summary_origin"] == TEST_SUMMARY_ORIGIN
    assert payload["summary_pt_origin"] == TEST_SUMMARY_PT_ORIGIN
    assert payload["summary"].endswith("v2")


def test_get_without_word_count_returns_latest_summary(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    session = db_session_factory()
    try:
        session.add_all(
            [
                Summary(
                    url=TEST_URL,
                    summary=TEST_SUMMARY,
                    summary_pt=TEST_SUMMARY_PT,
                    word_count=50,
                    summary_origin=TEST_SUMMARY_ORIGIN,
                    summary_pt_origin=TEST_SUMMARY_PT_ORIGIN,
                    created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
                ),
                Summary(
                    url=TEST_URL,
                    summary=f"{TEST_SUMMARY} newer",
                    summary_pt=f"{TEST_SUMMARY_PT} newer",
                    word_count=75,
                    summary_origin=TEST_SUMMARY_ORIGIN,
                    summary_pt_origin=TEST_SUMMARY_PT_ORIGIN,
                    created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
                ),
            ]
        )
        session.commit()
    finally:
        session.close()

    response = client.get("/summaries", params={"url": TEST_URL})

    assert response.status_code == 200
    payload = response.json()
    assert payload["word_count"] == 75
    assert payload["actual_word_count"] == len(payload["summary"].split())
    assert payload["summary_origin"] == TEST_SUMMARY_ORIGIN
    assert payload["summary_pt_origin"] == TEST_SUMMARY_PT_ORIGIN
    assert payload["summary"].endswith("newer")


def test_rejects_non_wikipedia_url(client: TestClient) -> None:
    response = client.post(
        "/summaries",
        json={"url": "https://example.com/article", "word_count": 50},
    )

    assert response.status_code == 400
    assert "wikipedia.org" in response.json()["detail"].lower()


def test_rejects_word_count_above_max(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.api.routes.summaries.settings.summary_word_count_max", 10)

    response = client.post(
        "/summaries",
        json={"url": TEST_URL, "word_count": 11},
    )

    assert response.status_code == 422
    assert "word_count" in response.json()["detail"].lower()


def test_post_returns_summary_when_translation_fails(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_scrape = Mock(return_value=TEST_TEXT)
    mock_summarize = Mock(return_value=(TEST_SUMMARY, TEST_SUMMARY_ORIGIN))

    def fail_translate(*args: object, **kwargs: object) -> tuple[str, str]:
        raise SummarizationError("translation failed")

    monkeypatch.setattr("app.services.orchestrator.get_wikipedia_article_text", mock_scrape)
    monkeypatch.setattr("app.services.orchestrator.summarize_text", mock_summarize)
    monkeypatch.setattr("app.services.orchestrator.translate_summary_to_portuguese", fail_translate)

    response = client.post("/summaries", json={"url": TEST_URL, "word_count": 50})

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"] == TEST_SUMMARY
    assert payload["summary_pt"] is None
    assert payload["summary_pt_origin"] == "error"
    assert payload["source"] == "generated"


def test_post_returns_502_when_scraping_fails(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_scrape = Mock(side_effect=ScrapingError("boom"))

    monkeypatch.setattr("app.services.orchestrator.get_wikipedia_article_text", mock_scrape)

    response = client.post("/summaries", json={"url": TEST_URL, "word_count": 50})

    assert response.status_code == 502
    assert "wikipedia scraping failed" in response.json()["detail"].lower()
