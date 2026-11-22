"""
Tests for the optional embeddings-based semantic KB fallback (embeddings.py
and kb_engine.semantic_kb_lookup()).

These mock Ollama's /api/embeddings HTTP call (via requests.post) rather than
requiring a live Ollama install -- per the project's rule that this feature's
own tests must never depend on Ollama actually running.

Run with: python -m pytest test_embeddings.py  (from the webapp/ folder)
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

sys.path.insert(0, str(Path(__file__).parent))

import embeddings
import kb_engine


def _mock_response(json_body):
    resp = MagicMock()
    resp.raise_for_status = lambda: None
    resp.json.return_value = json_body
    return resp


@pytest.fixture(autouse=True)
def _isolated_cache_and_reset(tmp_path, monkeypatch):
    """Every test gets its own on-disk cache file (never the real
    server/kb_embeddings_cache.json), and kb_engine's lazy in-memory vector
    cache is reset before and after so one test's mocked embeddings can never
    leak into another."""
    monkeypatch.setattr(embeddings, "CACHE_PATH", tmp_path / "kb_embeddings_cache.json")
    kb_engine._SEMANTIC_KB_VECTORS = None
    yield
    kb_engine._SEMANTIC_KB_VECTORS = None


# ---------------------------------------------------------------------------
# embeddings.py unit tests
# ---------------------------------------------------------------------------
def test_get_embedding_returns_none_on_connection_error():
    with patch("embeddings.requests.post", side_effect=requests.exceptions.ConnectionError("no ollama")):
        assert embeddings.get_embedding("hello") is None


def test_get_embedding_parses_valid_response():
    with patch("embeddings.requests.post", return_value=_mock_response({"embedding": [0.1, 0.2, 0.3]})):
        assert embeddings.get_embedding("hello") == [0.1, 0.2, 0.3]


def test_cosine_similarity_identical_vectors_is_one():
    assert embeddings.cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal_vectors_is_zero():
    assert embeddings.cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_ensure_kb_embeddings_skips_recompute_for_unchanged_entries(tmp_path):
    kb = [{"k": ["alpha phrase"], "a": "Alpha answer."}]
    cache_path = tmp_path / "cache.json"
    call_count = {"n": 0}

    def fake_post(url, json=None, timeout=None):
        call_count["n"] += 1
        return _mock_response({"embedding": [1.0, 0.0]})

    with patch("embeddings.requests.post", side_effect=fake_post):
        vectors = embeddings.ensure_kb_embeddings(kb, cache_path=cache_path)
        assert vectors == {0: [1.0, 0.0]}
        assert call_count["n"] == 1

        # Second call, same entry text (same hash) -> must be served from the
        # on-disk cache, not recomputed via another HTTP call.
        vectors_again = embeddings.ensure_kb_embeddings(kb, cache_path=cache_path)
        assert vectors_again == {0: [1.0, 0.0]}
        assert call_count["n"] == 1


def test_ensure_kb_embeddings_recomputes_only_changed_entries(tmp_path):
    cache_path = tmp_path / "cache.json"
    prompts_seen = []

    def fake_post(url, json=None, timeout=None):
        prompts_seen.append((json or {}).get("prompt"))
        return _mock_response({"embedding": [1.0, 0.0]})

    kb_v1 = [{"k": ["alpha phrase"], "a": "A"}, {"k": ["beta phrase"], "a": "B"}]
    with patch("embeddings.requests.post", side_effect=fake_post):
        embeddings.ensure_kb_embeddings(kb_v1, cache_path=cache_path)
    assert len(prompts_seen) == 2

    # Change only the second entry's text -- only that one hash is new, so
    # only it should trigger a fresh embedding call.
    kb_v2 = [{"k": ["alpha phrase"], "a": "A"}, {"k": ["beta phrase CHANGED"], "a": "B"}]
    prompts_seen.clear()
    with patch("embeddings.requests.post", side_effect=fake_post):
        embeddings.ensure_kb_embeddings(kb_v2, cache_path=cache_path)
    assert prompts_seen == ["beta phrase CHANGED"]


# ---------------------------------------------------------------------------
# kb_engine.semantic_kb_lookup() wiring / fallback-chain tests
# ---------------------------------------------------------------------------
def test_semantic_kb_lookup_falls_back_silently_when_ollama_unavailable():
    """(a) Embeddings raising/unavailable must never surface as an error --
    semantic_kb_lookup() returns None, and the full offline_reply() pipeline
    it sits inside keeps working end-to-end."""
    query = "asdkjh qpwoeiru totally made up gibberish gwerqwer"
    assert kb_engine.knowledge_base_lookup(query) is None  # keyword path finds nothing either

    with patch("embeddings.requests.post", side_effect=requests.exceptions.ConnectionError("no ollama running")):
        assert kb_engine.semantic_kb_lookup(query) is None

    with patch("embeddings.requests.post", side_effect=requests.exceptions.ConnectionError("no ollama running")):
        reply = kb_engine.offline_reply([{"role": "user", "content": query}])
    assert isinstance(reply, str) and reply  # never crashes; still returns *something*


def test_semantic_kb_lookup_used_when_keyword_match_is_empty():
    """(b) When the fast keyword/edit-distance match comes back empty, a
    mocked embedding response that puts the query close to a real KB entry
    (despite sharing no literal keywords with it) should be surfaced as the
    semantic match."""
    query = "how does my academic standing get calculated"
    assert kb_engine.knowledge_base_lookup(query) is None  # no shared keywords -- fast path finds nothing

    target = next(e for e in kb_engine.KB if "what is gpa" in e["k"])
    target_text = embeddings._entry_text(target)

    def fake_post(url, json=None, timeout=None):
        prompt = (json or {}).get("prompt", "")
        if prompt == target_text or prompt == query:
            # Query and target entry point in (nearly) the same direction --
            # simulates Ollama finding them semantically related.
            return _mock_response({"embedding": [1.0, 0.0, 0.0]})
        # Every other KB entry embeds to something clearly dissimilar.
        return _mock_response({"embedding": [0.0, 1.0, 0.0]})

    with patch("embeddings.requests.post", side_effect=fake_post):
        result = kb_engine.semantic_kb_lookup(query)

    assert result == target["a"]
