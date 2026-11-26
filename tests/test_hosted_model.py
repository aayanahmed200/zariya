"""Tests for Zariya's anonymous free-model inference route."""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "webapp"))
hosted_model = importlib.import_module("hosted_model")


class FakeResponse:
    def __init__(self, status_code=200, payload=None, lines=None):
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self._payload = payload or {}
        self._lines = lines or []

    def json(self):
        return self._payload

    def iter_lines(self, decode_unicode=True):
        return iter(self._lines)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def _answer(text="A clear answer"):
    return {"choices": [{"message": {"content": text}}]}


def test_free_ai_is_available_without_any_api_credential(monkeypatch):
    monkeypatch.delenv("VERCEL_OIDC_TOKEN", raising=False)
    monkeypatch.delenv("AI_GATEWAY_API_KEY", raising=False)
    status = hosted_model.connection_status()
    assert status["available"] is True
    assert status["configured"] is True
    assert status["provider"] == "Kilo AI Gateway"
    assert status["model"] == "kilo-auto/free"


def test_generate_reply_uses_anonymous_kilo_without_authorization(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse(payload=_answer("Kilo answered without a key."))

    monkeypatch.setattr(hosted_model.requests, "post", fake_post)
    monkeypatch.delenv("VERCEL_OIDC_TOKEN", raising=False)
    monkeypatch.delenv("AI_GATEWAY_API_KEY", raising=False)

    reply = hosted_model.generate_reply(
        [{"role": "user", "content": "Explain photosynthesis."}],
        "Answer clearly.",
    )

    assert reply == "Kilo answered without a key."
    assert calls[0][0] == "https://ai-gateway.kilo.ai/api/v1/chat/completions"
    assert calls[0][1]["json"]["model"] == "kilo-auto/free"
    assert "Authorization" not in calls[0][1]["headers"]


def test_stream_uses_only_answer_content_not_reasoning(monkeypatch):
    chunks = [
        'data: {"choices":[{"delta":{"reasoning":"private thought","content":""}}]}',
        'data: {"choices":[{"delta":{"content":"The answer"}}]}',
        'data: {"choices":[{"delta":{"content":" is ready."}}]}',
        "data: [DONE]",
    ]

    def fake_post(_url, **_kwargs):
        return FakeResponse(lines=chunks)

    monkeypatch.setattr(hosted_model.requests, "post", fake_post)
    monkeypatch.delenv("VERCEL_OIDC_TOKEN", raising=False)
    monkeypatch.delenv("AI_GATEWAY_API_KEY", raising=False)

    result = "".join(hosted_model.stream_reply(
        [{"role": "user", "content": "Hi"}],
        "Be concise.",
    ))
    assert result == "The answer is ready."
    assert "private thought" not in result


def test_stream_decodes_utf8_events_instead_of_latin1(monkeypatch):
    chunks = [
        b'data: {"choices":[{"delta":{"content":"it\xe2\x80\x99s"}}]}',
        b'data: {"choices":[{"delta":{"content":" \xd8\xa7\xd8\xb1\xd8\xaf\xd9\x88"}}]}',
        b"data: [DONE]",
    ]

    def fake_post(_url, **_kwargs):
        return FakeResponse(lines=chunks)

    monkeypatch.setattr(hosted_model.requests, "post", fake_post)
    result = "".join(hosted_model.stream_reply(
        [{"role": "user", "content": "Hi"}],
        "Be concise.",
    ))
    assert result == "it\u2019s \u0627\u0631\u062f\u0648"
    assert "\u00e2\u20ac\u2122" not in result


def test_shared_limit_is_returned_as_an_error_not_a_fake_reply(monkeypatch):
    def fake_post(_url, **_kwargs):
        return FakeResponse(status_code=429)

    monkeypatch.setattr(hosted_model.requests, "post", fake_post)
    monkeypatch.delenv("VERCEL_OIDC_TOKEN", raising=False)
    monkeypatch.delenv("AI_GATEWAY_API_KEY", raising=False)

    try:
        hosted_model.generate_reply(
            [{"role": "user", "content": "What is 2 + 2?"}],
            "Answer clearly.",
        )
    except hosted_model.GatewayError as exc:
        assert "shared free-model request limit" in str(exc)
    else:
        raise AssertionError("A rate-limited provider must not return a canned answer.")
