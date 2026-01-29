from __future__ import annotations

import logging

import redis  # type: ignore[reportMissingImports]
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_session

router = APIRouter(prefix="/health", tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/live", status_code=status.HTTP_200_OK)
def live() -> dict[str, str]:
    """Basic liveness probe."""

    return {"status": "ok"}


@router.get("/ready", status_code=status.HTTP_200_OK)
def ready(session: Session = Depends(get_session)) -> dict[str, object]:
    """Readiness probe that validates core dependencies."""

    checks: dict[str, str] = {}

    try:
        session.execute(text("SELECT 1"))
        checks["db"] = "ok"
    except Exception as exc:
        logger.exception("Readiness check failed for database.")
        checks["db"] = "error"
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "error", "checks": checks},
        ) from exc

    settings = get_settings()
    if settings.rate_limit_enabled:
        try:
            client = redis.from_url(settings.rate_limit_redis_url)
            client.ping()
            client.close()
            checks["redis"] = "ok"
        except Exception as exc:
            logger.exception("Readiness check failed for Redis.")
            checks["redis"] = "error"
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"status": "error", "checks": checks},
            ) from exc
    else:
        checks["redis"] = "disabled"

    return {"status": "ok", "checks": checks}
