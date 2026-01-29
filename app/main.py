from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI, Request, Response
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.routes.health import router as health_router
from app.api.routes.summaries import router as summaries_router
from app.core.logging import configure_logging, reset_request_id, set_request_id
from app.core.ratelimit import limiter, rate_limit_enabled

configure_logging()

app = FastAPI(
    title="Wikipedia Summarizer API",
    description="API that scrapes Wikipedia articles, summarizes them with an LLM, and caches results in Postgres.",
    version="1.0.0",
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next) -> Response:
    response = await call_next(request)
    content_type = response.headers.get("content-type", "")
    if (
        content_type.startswith("application/json")
        and "charset=" not in content_type.lower()
    ):
        response.headers["Content-Type"] = f"{content_type}; charset=utf-8"
    response.headers.setdefault("Cache-Control", "no-store")
    response.headers.setdefault("Pragma", "no-cache")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response


@app.middleware("http")
async def add_request_context(request: Request, call_next) -> Response:
    request_id = request.headers.get("x-request-id") or uuid4().hex
    token = set_request_id(request_id)
    try:
        response = await call_next(request)
    finally:
        reset_request_id(token)
    response.headers["X-Request-ID"] = request_id
    return response


if rate_limit_enabled:
    app.state.limiter = limiter

    def _rate_limit_handler(request: Request, exc: Exception) -> Response:
        return _rate_limit_exceeded_handler(request, exc)  # type: ignore[arg-type]

    app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)
    app.add_middleware(SlowAPIMiddleware)
else:
    app.state.limiter = None

app.include_router(summaries_router)
app.include_router(health_router)
