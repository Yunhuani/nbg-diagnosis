from io import BytesIO
from urllib import error

import pytest

from analysis import llm_client


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return self._payload


def test_call_deepseek_json_retries_recoverable_network_error(monkeypatch):
    attempts = 0

    def fake_urlopen(request, timeout):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise error.URLError("temporary TLS failure")
        return _Response(
            b'{"choices":[{"message":{"content":"{\\"ok\\": true}"}}]}'
        )

    monkeypatch.setattr(llm_client.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    result = llm_client.call_deepseek_json(
        "system",
        "user",
        max_attempts=3,
        retry_backoff_seconds=0,
    )

    assert result == {"ok": True}
    assert attempts == 3


def test_call_deepseek_json_does_not_retry_http_4xx(monkeypatch):
    attempts = 0

    def fake_urlopen(request, timeout):
        nonlocal attempts
        attempts += 1
        raise error.HTTPError(
            request.full_url,
            400,
            "bad request",
            {},
            BytesIO(b"bad request"),
        )

    monkeypatch.setattr(llm_client.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    with pytest.raises(error.HTTPError):
        llm_client.call_deepseek_json(
            "system",
            "user",
            max_attempts=3,
            retry_backoff_seconds=0,
        )

    assert attempts == 1


def test_call_deepseek_json_retries_http_5xx_then_fails(monkeypatch):
    attempts = 0

    def fake_urlopen(request, timeout):
        nonlocal attempts
        attempts += 1
        raise error.HTTPError(
            request.full_url,
            503,
            "service unavailable",
            {},
            BytesIO(b"service unavailable"),
        )

    monkeypatch.setattr(llm_client.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    with pytest.raises(error.HTTPError):
        llm_client.call_deepseek_json(
            "system",
            "user",
            max_attempts=3,
            retry_backoff_seconds=0,
        )

    assert attempts == 3
