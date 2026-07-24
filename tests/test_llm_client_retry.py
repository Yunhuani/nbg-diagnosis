import json
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


def _completion_payload(
    content,
    *,
    reasoning_content=None,
    finish_reason="stop",
):
    return json.dumps(
        {
            "choices": [
                {
                    "finish_reason": finish_reason,
                    "message": {
                        "content": content,
                        "reasoning_content": reasoning_content,
                    },
                }
            ]
        }
    ).encode("utf-8")


def test_call_deepseek_json_uses_v4_pro_non_thinking_json_payload(
    monkeypatch,
    tmp_path,
):
    captured_payload = None

    def fake_urlopen(request, timeout):
        nonlocal captured_payload
        captured_payload = json.loads(request.data.decode("utf-8"))
        return _Response(_completion_payload('{"ok": true}'))

    monkeypatch.setattr(llm_client.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)

    result = llm_client.call_deepseek_json(
        "system JSON",
        "user",
        env_path=tmp_path / "missing.env",
    )

    assert result == {"ok": True}
    assert captured_payload["model"] == "deepseek-v4-pro"
    assert captured_payload["thinking"] == {"type": "disabled"}
    assert captured_payload["response_format"] == {"type": "json_object"}
    assert captured_payload["max_tokens"] == 8192


def test_call_deepseek_json_ignores_reasoning_content(monkeypatch):
    def fake_urlopen(request, timeout):
        return _Response(
            _completion_payload(
                '{"answer": "final"}',
                reasoning_content="private chain of thought",
            )
        )

    monkeypatch.setattr(llm_client.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    result = llm_client.call_deepseek_json("system JSON", "user")

    assert result == {"answer": "final"}


@pytest.mark.parametrize("empty_content", [None, "   "])
def test_call_deepseek_json_retries_empty_content(
    monkeypatch,
    empty_content,
):
    attempts = 0

    def fake_urlopen(request, timeout):
        nonlocal attempts
        attempts += 1
        content = empty_content if attempts == 1 else '{"ok": true}'
        return _Response(_completion_payload(content))

    monkeypatch.setattr(llm_client.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    result = llm_client.call_deepseek_json(
        "system JSON",
        "user",
        max_attempts=2,
        retry_backoff_seconds=0,
    )

    assert result == {"ok": True}
    assert attempts == 2


def test_call_deepseek_json_retries_invalid_json_content(monkeypatch):
    attempts = 0

    def fake_urlopen(request, timeout):
        nonlocal attempts
        attempts += 1
        content = '{"broken":' if attempts == 1 else '{"ok": true}'
        return _Response(_completion_payload(content))

    monkeypatch.setattr(llm_client.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    result = llm_client.call_deepseek_json(
        "system JSON",
        "user",
        max_attempts=2,
        retry_backoff_seconds=0,
    )

    assert result == {"ok": True}
    assert attempts == 2


def test_call_deepseek_json_retries_truncated_completion(monkeypatch):
    attempts = 0

    def fake_urlopen(request, timeout):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return _Response(
                _completion_payload('{"partial": true}', finish_reason="length")
            )
        return _Response(_completion_payload('{"ok": true}'))

    monkeypatch.setattr(llm_client.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    result = llm_client.call_deepseek_json(
        "system JSON",
        "user",
        max_attempts=2,
        retry_backoff_seconds=0,
    )

    assert result == {"ok": True}
    assert attempts == 2


def test_call_deepseek_json_preserves_environment_model_override(
    monkeypatch,
    tmp_path,
):
    captured_payload = None

    def fake_urlopen(request, timeout):
        nonlocal captured_payload
        captured_payload = json.loads(request.data.decode("utf-8"))
        return _Response(_completion_payload('{"ok": true}'))

    monkeypatch.setattr(llm_client.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-v4-pro")

    llm_client.call_deepseek_json(
        "system JSON",
        "user",
        env_path=tmp_path / "missing.env",
    )

    assert captured_payload["model"] == "deepseek-v4-pro"


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
