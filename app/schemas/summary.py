from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class SummaryCreate(BaseModel):
    url: str = Field(
        ...,
        description="Wikipedia URL to summarize.",
        examples=["https://en.wikipedia.org/wiki/Artificial_intelligence"],
    )
    word_count: int = Field(
        ...,
        gt=0,
        description="Target maximum number of words in the summary.",
        examples=[200],
    )


class SummaryResponse(BaseModel):
    url: str = Field(..., description="Normalized Wikipedia URL.")
    word_count: int = Field(..., description="Requested word count.")
    actual_word_count: int = Field(..., description="Actual number of words in the summary.")
    summary: str = Field(..., description="Summary in the source language (often English).")
    summary_origin: str = Field(
        ...,
        description="Origin of the summary content (llm, llm_fallback, or fallback).",
    )
    summary_pt: str | None = Field(
        default=None,
        description="Portuguese (pt-BR) translation of the summary.",
    )
    summary_pt_origin: str = Field(
        ...,
        description=(
            "Origin/status of the Portuguese translation "
            "(llm, llm_fallback, skipped, disabled, unavailable, error)."
        ),
    )
    source: Literal["generated", "cache"] = Field(
        ...,
        description="Whether the summary was generated now or served from cache.",
    )
    created_at: datetime = Field(..., description="Creation timestamp in UTC.")

    model_config = {
        "json_schema_extra": {
            "example": {
                "url": "https://en.wikipedia.org/wiki/Artificial_intelligence",
                "word_count": 200,
                "actual_word_count": 182,
                "summary": "Artificial intelligence (AI) is a field of computing focused on building systems that perform tasks requiring human-like intelligence, such as perception, reasoning, learning, and decision-making...",
                "summary_origin": "llm",
                "summary_pt": "Inteligência artificial (IA) é um campo da computação focado em construir sistemas que executam tarefas associadas à inteligência humana, como percepção, raciocínio, aprendizado e tomada de decisão...",
                "summary_pt_origin": "llm",
                "source": "generated",
                "created_at": "2026-01-27T12:00:00Z",
            }
        }
    }
