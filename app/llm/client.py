from __future__ import annotations

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.core.config import get_settings


def build_llm(model: str | None = None) -> ChatOpenAI:
    settings = get_settings()
    return ChatOpenAI(
        model=model or settings.openai_model,
        temperature=0,
        api_key=SecretStr(settings.openai_api_key),
        timeout=settings.llm_timeout_seconds,
    )
