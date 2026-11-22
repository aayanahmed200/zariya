"""
Tests for local_model.py -- Ollama tag matching and reply generation.

Run with: python -m pytest test_local_model.py  (from the webapp/ folder)
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent))

import local_model as lm


def _mock_tags_response(names):
    resp = MagicMock()
    resp.json.return_value = {"models": [{"name": n} for n in names]}
    resp.raise_for_status = lambda: None
    return resp


def test_model_present_rejects_wrong_tag_of_same_base_model():
    # Regression test: _model_present("qwen2.5:1.5b") used to return True even
    # when only a completely different-sized tag ("qwen2.5:7b") was pulled,
    # because it matched on base-name prefix regardless of the requested tag.
    with patch("requests.get", return_value=_mock_tags_response(["qwen2.5:7b"])):
        assert lm._model_present("qwen2.5:1.5b") is False


def test_model_present_exact_tag_match():
    with patch("requests.get", return_value=_mock_tags_response(["qwen2.5:1.5b"])):
        assert lm._model_present("qwen2.5:1.5b") is True


def test_model_present_bare_name_loosely_matches_any_tag():
    # No tag specified in the query -> accept any pulled tag of that base model.
    with patch("requests.get", return_value=_mock_tags_response(["qwen2.5:latest"])):
        assert lm._model_present("qwen2.5") is True


def test_model_present_nothing_pulled():
    with patch("requests.get", return_value=_mock_tags_response([])):
        assert lm._model_present("qwen2.5") is False


def test_model_present_exact_tag_among_several_pulled():
    names = ["qwen2.5:7b", "qwen2.5:1.5b", "llama3:8b"]
    with patch("requests.get", return_value=_mock_tags_response(names)):
        assert lm._model_present("qwen2.5:1.5b") is True


def test_generate_reply_happy_path(monkeypatch):
    monkeypatch.setattr(lm, "_ready", True)
    resp = MagicMock()
    resp.json.return_value = {"message": {"content": "Hello from Ollama"}}
    resp.raise_for_status = lambda: None
    with patch("requests.post", return_value=resp):
        result = lm.generate_reply([{"role": "user", "content": "hi"}], "system prompt")
    assert result == "Hello from Ollama"


def test_generate_reply_returns_none_when_not_ready(monkeypatch):
    monkeypatch.setattr(lm, "_ready", False)
    result = lm.generate_reply([{"role": "user", "content": "hi"}], "sys")
    assert result is None


def test_generate_reply_returns_none_on_network_failure(monkeypatch):
    monkeypatch.setattr(lm, "_ready", True)
    with patch("requests.post", side_effect=Exception("connection refused")):
        result = lm.generate_reply([{"role": "user", "content": "hi"}], "sys")
    assert result is None


class _FakeStreamResp:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def raise_for_status(self):
        pass

    def iter_lines(self):
        import json
        yield json.dumps({"message": {"content": "Hel"}}).encode()
        yield json.dumps({"message": {"content": "lo"}}).encode()
        yield json.dumps({"message": {"content": ""}, "done": True}).encode()


def test_stream_reply_happy_path(monkeypatch):
    monkeypatch.setattr(lm, "_ready", True)
    with patch("requests.post", return_value=_FakeStreamResp()):
        tokens = list(lm.stream_reply([{"role": "user", "content": "hi"}], "sys"))
    assert tokens == ["Hel", "lo"]
