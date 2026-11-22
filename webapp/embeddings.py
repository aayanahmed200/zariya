"""
Optional semantic-search layer over the offline knowledge base, built on top
of Ollama's local embeddings endpoint.

Why this exists: kb_engine.py's knowledge_base_lookup() is pure keyword /
edit-distance matching -- fast and dependency-free, but it only finds an
entry if the query shares actual words (or near-typos of them) with one of
that entry's curated keyword phrases. A differently-worded question that
means the same thing ("how does school gpa work" vs the KB's "what is gpa")
can miss entirely. This module adds a second-pass fallback: embed the query
and every KB entry with a small local embedding model (served by the same
Ollama install already used for local chat), and pick the closest KB entry by
plain cosine similarity if it clears a similarity threshold.

Fallback chain (see kb_engine.semantic_kb_lookup, which calls into this
module): fast keyword/edit-distance match is always tried first since it's
free and already good for exact-ish matches; only if that comes back empty
does anything here get called at all. Every function below degrades
silently to "not available" (None / empty dict) on any failure -- Ollama not
installed, not running, the embedding model not pulled, a network hiccup,
whatever -- so the offline engine's guarantee of "never crashes, never needs
a network connection to answer something" is unaffected. Nothing in this
module is called at import time, and nothing in kb_engine.py's own import
path requires this module to succeed.

Config (mirrors local_model.py's OLLAMA_URL pattern, but kept independent so
importing this module never triggers local_model's background
Ollama-connection thread):
- OLLAMA_URL        (env var, default http://localhost:11434)
- KB_EMBEDDING_MODEL (env var, default "nomic-embed-text")

No numpy/faiss/etc -- plain Python lists of floats and a manual dot product
are plenty fast at this knowledge base's size (roughly a thousand entries).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from typing import Optional

import requests

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
EMBEDDING_MODEL = os.environ.get("KB_EMBEDDING_MODEL", "nomic-embed-text")

CACHE_PATH = Path(__file__).parent / "server" / "kb_embeddings_cache.json"


def get_embedding(text: str) -> Optional[list[float]]:
    """Asks Ollama's local /api/embeddings endpoint for a vector for `text`.
    Returns None (never raises) if Ollama isn't running, the embedding model
    isn't pulled, or anything else goes wrong -- callers treat None exactly
    like "embeddings aren't available right now"."""
    if not text or not text.strip():
        return None
    try:
        res = requests.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={"model": EMBEDDING_MODEL, "prompt": text},
            timeout=10,
        )
        res.raise_for_status()
        data = res.json()
        vec = data.get("embedding")
        if isinstance(vec, list) and vec:
            return [float(x) for x in vec]
        return None
    except Exception:
        return None


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Plain-Python cosine similarity between two equal-length vectors, in
    [-1, 1] (or 0.0 for degenerate/mismatched input). No numpy needed at this
    knowledge-base's scale."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _entry_text(entry: dict) -> str:
    """The text embedded to represent a KB entry -- its keyword phrases (the
    ways a question about it tends to be phrased), which is what a user's
    query is actually compared against."""
    return " | ".join(entry.get("k", []))


def _entry_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_cache(cache_path: Path) -> dict:
    if cache_path.exists():
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("vectors"), dict):
                return data
        except Exception:
            pass
    return {"model": EMBEDDING_MODEL, "vectors": {}}


def _save_cache(cache: dict, cache_path: Path) -> None:
    """Temp-file-then-rename write so a crash mid-save never leaves the cache
    file truncated/corrupted (same pattern as core/model_downloader.py)."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = cache_path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    tmp_path.replace(cache_path)


def ensure_kb_embeddings(
    kb_entries: list[dict], cache_path: Optional[Path] = None
) -> dict[int, list[float]]:
    """Returns {kb_index: embedding_vector} for as much of `kb_entries` as
    could be embedded, computing lazily and caching to `cache_path` on disk
    (keyed by a hash of each entry's text, so only new/changed entries ever
    get re-embedded on a later call/process).

    If Ollama isn't reachable at all, this returns whatever was already in
    the on-disk cache (an empty dict on a totally fresh install) rather than
    raising -- semantic_kb_lookup() below treats an empty result as "this
    feature isn't available right now" and falls back to keyword-only
    behavior.
    """
    if cache_path is None:
        cache_path = CACHE_PATH  # looked up here (not as a default-arg value) so tests can monkeypatch it
    cache = _load_cache(cache_path)
    if cache.get("model") != EMBEDDING_MODEL:
        # Cached vectors from a different embedding model aren't comparable
        # to ones from this model -- start fresh rather than mixing them.
        cache = {"model": EMBEDDING_MODEL, "vectors": {}}

    vectors_by_index: dict[int, list[float]] = {}
    changed = False
    for idx, entry in enumerate(kb_entries):
        text = _entry_text(entry)
        if not text.strip():
            continue
        h = _entry_hash(text)
        cached_vec = cache["vectors"].get(h)
        if cached_vec is not None:
            vectors_by_index[idx] = cached_vec
            continue
        vec = get_embedding(text)
        if vec is None:
            # Ollama down / embedding model not pulled / request failed --
            # stop trying for the rest of this pass. Whatever was already
            # resolved from cache above is still returned as-is.
            break
        cache["vectors"][h] = vec
        vectors_by_index[idx] = vec
        changed = True

    if changed:
        _save_cache(cache, cache_path)
    return vectors_by_index


def best_match(
    query_vec: list[float], vectors_by_index: dict[int, list[float]]
) -> tuple[Optional[int], float]:
    """Returns (kb_index, similarity) for the closest cached vector to
    `query_vec`, or (None, 0.0) if there's nothing to compare against."""
    best_idx: Optional[int] = None
    best_score = -1.0
    for idx, vec in vectors_by_index.items():
        score = cosine_similarity(query_vec, vec)
        if score > best_score:
            best_idx, best_score = idx, score
    return best_idx, max(best_score, 0.0)
