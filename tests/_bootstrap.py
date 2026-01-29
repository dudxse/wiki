from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Align direct test execution with pytest defaults.
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
os.environ.setdefault("OPENAI_MODEL", "test-model")
os.environ.setdefault("LOG_LEVEL", "INFO")
os.environ.setdefault("HTTP_TIMEOUT_SECONDS", "10")
os.environ.setdefault("LLM_TIMEOUT_SECONDS", "30")
os.environ.setdefault("WIKIPEDIA_USER_AGENT", "wiki-summarizer-test/1.0")
os.environ.setdefault("WIKIPEDIA_MIN_ARTICLE_WORDS", "50")
os.environ.setdefault("WIKIPEDIA_MAX_CONTENT_BYTES", "2000000")
os.environ.setdefault("WIKIPEDIA_MAX_REDIRECTS", "5")
os.environ.setdefault("SUMMARY_WORD_COUNT_MAX", "500")
os.environ.setdefault("ENABLE_PORTUGUESE_TRANSLATION", "true")

os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("RATE_LIMIT_REDIS_URL", "memory://")
os.environ.setdefault("RATE_LIMIT_TRUST_PROXY_HEADERS", "false")
os.environ.setdefault("RATE_LIMIT_DEFAULT", "1000/minute")
os.environ.setdefault("RATE_LIMIT_POST_SUMMARIES", "1000/minute")
os.environ.setdefault("RATE_LIMIT_GET_SUMMARIES", "1000/minute")
