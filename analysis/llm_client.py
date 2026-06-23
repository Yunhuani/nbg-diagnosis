from __future__ import annotations

import json
import logging
import os
import socket
import ssl
import time
from http.client import IncompleteRead
from pathlib import Path
from typing import Any
from urllib import error, request


DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"
logger = logging.getLogger(__name__)


def call_deepseek_json(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str | None = None,
    env_path: str | Path = ".env",
    base_url: str | None = None,
    timeout: int = 60,
    max_attempts: int = 3,
    retry_backoff_seconds: float = 0.5,
) -> dict[str, Any]:
    """Call DeepSeek and return the assistant message parsed as JSON."""
    env = _load_dotenv(env_path)
    api_key = os.environ.get("DEEPSEEK_API_KEY") or env.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is missing")

    selected_model = (
        model
        or os.environ.get("DEEPSEEK_MODEL")
        or env.get("DEEPSEEK_MODEL")
        or DEFAULT_MODEL
    )
    endpoint = (
        base_url
        or os.environ.get("DEEPSEEK_BASE_URL")
        or env.get("DEEPSEEK_BASE_URL")
        or DEFAULT_BASE_URL
    ).rstrip("/")

    payload = {
        "model": selected_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        f"{endpoint}/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    response_body: bytes | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            with request.urlopen(req, timeout=timeout) as response:
                response_body = response.read()
            break
        except error.HTTPError as exc:
            if exc.code < 500 or attempt == max_attempts:
                logger.error(
                    "DeepSeek request failed on attempt %s/%s: HTTP %s",
                    attempt,
                    max_attempts,
                    exc.code,
                )
                raise
            logger.warning(
                "DeepSeek request retry %s/%s after HTTP %s",
                attempt,
                max_attempts,
                exc.code,
            )
        except (
            error.URLError,
            TimeoutError,
            socket.timeout,
            ssl.SSLError,
            ConnectionError,
            IncompleteRead,
        ) as exc:
            if attempt == max_attempts:
                logger.error(
                    "DeepSeek request failed after %s attempts: %s",
                    max_attempts,
                    exc,
                )
                raise
            logger.warning(
                "DeepSeek request retry %s/%s after network error: %s",
                attempt,
                max_attempts,
                exc,
            )

        if retry_backoff_seconds > 0:
            time.sleep(retry_backoff_seconds * attempt)

    assert response_body is not None
    data = json.loads(response_body.decode("utf-8"))

    content = data["choices"][0]["message"]["content"]
    return _parse_json_content(content)


def _load_dotenv(env_path: str | Path) -> dict[str, str]:
    path = Path(env_path)
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def _parse_json_content(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return json.loads(text)
