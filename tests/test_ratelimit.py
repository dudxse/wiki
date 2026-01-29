from __future__ import annotations

import importlib

import _bootstrap  # noqa: F401
import pytest

from app.core.config import get_settings


def test_rate_limit_disabled_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    monkeypatch.setenv("RATE_LIMIT_REDIS_URL", "memory://")
    get_settings.cache_clear()

    import app.core.ratelimit as ratelimit

    importlib.reload(ratelimit)

    def handler() -> str:
        return "ok"

    decorated = ratelimit.limit("1/minute")(handler)

    assert ratelimit.rate_limit_enabled is False
    assert decorated() == "ok"


def test_rate_limit_enabled_builds_limiter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_REDIS_URL", "memory://")
    get_settings.cache_clear()

    import app.core.ratelimit as ratelimit

    importlib.reload(ratelimit)

    try:
        assert ratelimit.rate_limit_enabled is True
        assert ratelimit.limiter is not None
    finally:
        monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
        monkeypatch.setenv("RATE_LIMIT_REDIS_URL", "memory://")
        get_settings.cache_clear()
        importlib.reload(ratelimit)
