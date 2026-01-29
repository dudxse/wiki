from __future__ import annotations

import os
import time

import httpx
import pytest

pytestmark = pytest.mark.integration

if not os.getenv("RUN_INTEGRATION_TESTS"):
    pytest.skip(
        "Integration tests disabled. Set RUN_INTEGRATION_TESTS=1 to enable.",
        allow_module_level=True,
    )


BASE_URL = os.getenv("INTEGRATION_BASE_URL", "http://localhost:8080")


def _wait_for_ready(timeout_seconds: int = 30) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    with httpx.Client(timeout=5.0) as client:
        while time.time() < deadline:
            try:
                response = client.get(f"{BASE_URL}/health/ready")
                if response.status_code == 200:
                    return
            except Exception as exc:  # pragma: no cover - best-effort wait loop
                last_error = exc
            time.sleep(1)
    raise AssertionError("API did not become ready in time.") from last_error


def test_health_ready() -> None:
    _wait_for_ready()
    response = httpx.get(f"{BASE_URL}/health/ready", timeout=10.0)
    assert response.status_code == 200
    assert response.json().get("status") == "ok"


def test_summaries_happy_path() -> None:
    if not os.getenv("RUN_SUMMARIES_INTEGRATION"):
        pytest.skip("Skipping summaries integration test; set RUN_SUMMARIES_INTEGRATION=1.")

    _wait_for_ready()
    payload = {
        "url": "https://en.wikipedia.org/wiki/Artificial_intelligence",
        "word_count": 80,
    }
    response = httpx.post(f"{BASE_URL}/summaries", json=payload, timeout=30.0)
    assert response.status_code == 200
    data = response.json()
    assert data["url"].endswith("/wiki/Artificial_intelligence")
    assert data["word_count"] == 80
    assert data["summary"]
