from __future__ import annotations

import json
import os
from typing import Any
from urllib import request


BOCHA_SEARCH_URL = "https://api.bochaai.com/v1/web-search"
SEARCH_COUNT = 10
SEARCH_TIMEOUT_SECONDS = 20


def bocha_web_search(query: str) -> list[dict[str, Any]]:
    api_key = os.environ.get("BOCHA_API_KEY")
    if not api_key:
        raise RuntimeError("BOCHA_API_KEY is missing")

    payload = {
        "query": query,
        "summary": True,
        "count": SEARCH_COUNT,
        "freshness": "noLimit",
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        BOCHA_SEARCH_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with request.urlopen(req, timeout=SEARCH_TIMEOUT_SECONDS) as response:
        response_body = response.read()
    data = json.loads(response_body.decode("utf-8"))
    value = data["data"]["webPages"]["value"]
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
