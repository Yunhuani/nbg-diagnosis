from __future__ import annotations

import os


# Source: analysis/llm_client.py
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-pro"
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", DEFAULT_DEEPSEEK_MODEL)

# Source: analysis/synthesis.py
DEFAULT_DEEPSEEK_SYNTHESIS_MODEL: str | None = None
DEEPSEEK_SYNTHESIS_MODEL = os.getenv(
    "DEEPSEEK_SYNTHESIS_MODEL", DEFAULT_DEEPSEEK_SYNTHESIS_MODEL
)

# Source: analysis/llm_client.py
DEFAULT_MAX_TOKENS = 8192
LLM_TEMPERATURE = 0.2
LLM_TIMEOUT_SECONDS = 60
LLM_MAX_ATTEMPTS = 3

# Source: analysis/search_client.py
DEFAULT_BOCHA_API_KEY: str | None = None
BOCHA_API_KEY = os.getenv("BOCHA_API_KEY", DEFAULT_BOCHA_API_KEY)
BOCHA_SEARCH_COUNT = 10
BOCHA_SEARCH_TIMEOUT_SECONDS = 20

# Source: api_server.py
MAX_DIMENSION_WORKERS = 3
