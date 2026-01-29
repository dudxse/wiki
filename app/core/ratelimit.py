from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TypeVar

from fastapi import Request
from slowapi import Limiter

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


def _get_client_ip(request: Request) -> str:
    """Resolve client IP with optional proxy header trust."""

    if settings.rate_limit_trust_proxy_headers:
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            candidate = forwarded_for.split(",")[0].strip()
            if candidate:
                return candidate

        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            candidate = real_ip.strip()
            if candidate:
                return candidate

    if request.client:
        return request.client.host
    return "unknown"


rate_limit_enabled = settings.rate_limit_enabled
limiter: Limiter | None = None

if rate_limit_enabled:
    try:
        limiter = Limiter(
            key_func=_get_client_ip,
            storage_uri=settings.rate_limit_redis_url,
            default_limits=[settings.rate_limit_default],
        )
    except Exception as exc:  # pragma: no cover - defensive fallback
        # If Redis dependencies aren't available, fall back to in-memory storage.
        logger.warning(
            "Rate limiter storage unavailable; falling back to in-memory. Error: %s",
            exc,
        )
        limiter = Limiter(
            key_func=_get_client_ip,
            storage_uri="memory://",
            default_limits=[settings.rate_limit_default],
        )

F = TypeVar("F", bound=Callable[..., object])


def limit(limit_value: str) -> Callable[[F], F]:
    """Return a limiter decorator when enabled, otherwise a no-op."""

    if not rate_limit_enabled or limiter is None:

        def decorator(func: F) -> F:
            return func

        return decorator

    return limiter.limit(limit_value)
