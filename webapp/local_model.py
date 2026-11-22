"""
Local-model inference via Ollama, server-side.

Why Ollama instead of embedding llama-cpp-python directly: llama-cpp-python
needs a working C++ build toolchain to install on many machines, which fails
silently or loudly depending on the platform. Ollama (https://ollama.com) is
a free, single-installer application -- prebuilt for Windows/Mac/Linux, no
compiler, no account, no API key -- that runs open-source models locally and
exposes them over a small local HTTP API. This module just talks to that API.

Setup, once, on the machine that runs this server:
1. Install Ollama from https://ollama.com/download (a normal app installer).
2. Make sure it's running (it starts automatically after install on most
   platforms; otherwise run the ollama app / 'ollama serve').
3. That's it. On first request, this module asks Ollama to pull a small
   default model automatically if it isn't already present -- no need to run
   any command yourself.

If Ollama isn't installed or isn't running, this module simply reports
itself as unavailable and app.py falls through to the offline knowledge
engine, so the app is never broken by this being absent.

Override the model with LOCAL_MODEL_NAME in .env (any name from
https://ollama.com/library). Override the Ollama address with OLLAMA_URL if
it's running on a different host/port. Set DISABLE_LOCAL_MODEL=1 to skip
trying to use a local model entirely. The active model can also be switched
at runtime from Settings, without touching .env or restarting -- see
set_active_model() below.
"""
import json
import os
import threading
import time

import requests

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("LOCAL_MODEL_NAME", "qwen2.5:1.5b")
_DISABLED = os.environ.get("DISABLE_LOCAL_MODEL", "").lower() in ("1", "true", "yes")
_ON_VERCEL = bool(os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV"))

_status = "No hosted AI model is configured for this Vercel deployment." if _ON_VERCEL else ("not configured (DISABLE_LOCAL_MODEL is set)" if _DISABLED else "starting")
_ready = False
_pulling = False
_progress = {"completed": 0, "total": 0}
_wake_event = threading.Event()


def is_available() -> bool:
    return _ready


def load_status() -> str:
    return _status


def load_progress() -> dict:
    """Bytes downloaded so far for the current/most recent pull, if known."""
    return dict(_progress)


def current_model() -> str:
    """The Ollama model name currently in use (or being downloaded, if a
    switch to a new model is in progress)."""
    return DEFAULT_MODEL


def retry_now() -> dict:
    """Wakes the background loop up immediately instead of waiting out the
    current backoff delay. Safe to call any time -- a no-op if a pull is
    already in flight or the model is already loaded."""
    if _ON_VERCEL:
        return {"ok": False, "status": _status, "error": _status}
    if _ready:
        return {"ok": True, "status": _status}
    if _pulling:
        return {"ok": False, "status": _status}
    _wake_event.set()
    return {"ok": True, "status": "Retrying now..."}


def _ollama_running() -> bool:
    if _ON_VERCEL:
        return False
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def _model_present(model: str) -> bool:
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        r.raise_for_status()
        names = [m.get("name", "") for m in r.json().get("models", [])]
        if ":" in model:
            # Caller asked for a specific tag (e.g. "qwen2.5:1.5b") -- only an
            # exact match counts. A prefix match here would let a completely
            # different-sized pulled model (e.g. "qwen2.5:7b") silently pass
            # as if the requested one were present.
            return model in names
        # No tag specified -- accept any tag of this base model (e.g. this
        # picks up an already-pulled "qwen2.5:latest" for a bare "qwen2.5").
        return any(n == model or n.startswith(model + ":") for n in names)
    except Exception:
        return False


def list_models() -> list[dict]:
    """Every model Ollama already has pulled on this machine, so Settings can
    offer a dropdown of models that are instantly usable, with no download
    wait, alongside the option to pull a new one by name."""
    if _ON_VERCEL:
        return []
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        r.raise_for_status()
        return [
            {"name": m.get("name", ""), "size": m.get("size", 0)}
            for m in r.json().get("models", [])
            if m.get("name")
        ]
    except Exception:
        return []


def _pull_model(model: str) -> bool:
    """Streams a model pull from Ollama, actually reading each progress line
    instead of discarding it, so a failure reported mid-stream (bad model
    name, disk full, network drop) is caught instead of being silently
    treated as success. Always re-checks with Ollama's own model list
    afterwards before declaring victory, since a pull can end without an
    exception and still not have produced a usable model.
    """
    global _status, _pulling, _progress
    _pulling = True
    _progress = {"completed": 0, "total": 0}
    try:
        _status = f"Downloading '{model}' via Ollama (one-time, may take a few minutes)..."
        with requests.post(
            f"{OLLAMA_URL}/api/pull", json={"name": model}, stream=True, timeout=None
        ) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except (ValueError, TypeError):
                    continue

                if payload.get("error"):
                    _status = f"Failed to pull model '{model}' from Ollama: {payload['error']}"
                    return False

                total = payload.get("total")
                completed = payload.get("completed")
                if isinstance(total, int):
                    _progress["total"] = total
                if isinstance(completed, int):
                    _progress["completed"] = completed
                status_line = payload.get("status")
                if status_line:
                    if _progress["total"]:
                        pct = round(_progress["completed"] / _progress["total"] * 100)
                        _status = f"{status_line} ({pct}%)"
                    else:
                        _status = status_line

        # A 200 response with no explicit "error" line still isn't proof the
        # model is actually usable -- confirm it shows up in Ollama's own
        # model list before telling the rest of the app it's ready.
        if not _model_present(model):
            _status = (
                f"Ollama finished responding but '{model}' still isn't in its model "
                "list -- the pull may have been interrupted. Will retry."
            )
            return False

        return True
    except Exception as e:
        _status = f"Failed to pull model '{model}' from Ollama: {e}"
        return False
    finally:
        _pulling = False


def _init_in_background():
    global _ready, _status
    if _DISABLED:
        _status = "not configured (DISABLE_LOCAL_MODEL is set)"
        return
    delay = 3
    while True:
        if not _ollama_running():
            _status = ("Ollama isn't running yet -- install it from https://ollama.com/download and start it "
                        "(this will retry automatically once it's up)")
        elif not _model_present(DEFAULT_MODEL):
            if _pull_model(DEFAULT_MODEL):
                _status = "loaded"
                _ready = True
                return
            # pull failed -- _pull_model already set a status message; retry after a delay
        else:
            _status = "loaded"
            _ready = True
            return
        _wake_event.wait(delay)
        _wake_event.clear()
        delay = min(delay * 2, 60)


if not _ON_VERCEL and not _DISABLED:
    threading.Thread(target=_init_in_background, daemon=True).start()


def _pull_and_activate(model: str):
    """Background worker for set_active_model() when the requested model
    isn't already pulled: downloads it, and only flips the active model over
    once it's confirmed present, so a failed switch leaves the previous
    (working) model in place instead of pointing the app at nothing."""
    global DEFAULT_MODEL, _ready, _status
    if _pull_model(model):
        DEFAULT_MODEL = model
        _status = "loaded"
        _ready = True


def set_active_model(name: str) -> dict:
    """Switch which Ollama model Zariya talks to, at runtime, from Settings --
    no .env edit or restart required. If the model is already pulled locally
    this takes effect immediately; otherwise it kicks off a background
    download and the frontend can poll /api/config in the meantime, exactly
    like first-run setup does."""
    global DEFAULT_MODEL, _ready, _status
    name = (name or "").strip()
    if _ON_VERCEL:
        return {"ok": False, "error": "Ollama model switching is available on self-hosted installs, not on this Vercel deployment."}
    if not name:
        return {"ok": False, "error": "No model name provided"}
    if _pulling:
        return {"ok": False, "error": "A model download is already in progress -- try again once it finishes"}
    if not _ollama_running():
        return {"ok": False, "error": "Ollama isn't running, so no model can be selected right now"}
    if _model_present(name):
        DEFAULT_MODEL = name
        _status = "loaded"
        _ready = True
        return {"ok": True, "status": _status, "model": DEFAULT_MODEL, "pulling": False}
    threading.Thread(target=_pull_and_activate, args=(name,), daemon=True).start()
    return {"ok": True, "status": f"Downloading '{name}'...", "model": name, "pulling": True}


def generate_reply(messages: list[dict], system_prompt: str, temperature: float | None = None) -> str | None:
    if not _ready:
        return None
    chat_messages = [{"role": "system", "content": system_prompt}]
    chat_messages += [{"role": m["role"], "content": m["content"]} for m in messages[-24:]]
    payload = {"model": DEFAULT_MODEL, "messages": chat_messages, "stream": False}
    if temperature is not None:
        payload["options"] = {"temperature": temperature}
    try:
        res = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=60)
        res.raise_for_status()
        data = res.json()
        return data.get("message", {}).get("content")
    except Exception:
        return None


def stream_reply(messages: list[dict], system_prompt: str, temperature: float | None = None):
    """Yields reply tokens as they arrive from Ollama's streaming chat API,
    for a real-time typing effect in the UI. Yields nothing (an empty
    generator) if the local model isn't ready or the request fails partway --
    callers should treat "no tokens yielded" the same as generate_reply()
    returning None."""
    if not _ready:
        return
    chat_messages = [{"role": "system", "content": system_prompt}]
    chat_messages += [{"role": m["role"], "content": m["content"]} for m in messages[-24:]]
    payload = {"model": DEFAULT_MODEL, "messages": chat_messages, "stream": True}
    if temperature is not None:
        payload["options"] = {"temperature": temperature}
    try:
        with requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=120, stream=True) as res:
            res.raise_for_status()
            for line in res.iter_lines():
                if not line:
                    continue
                try:
                    payload_line = json.loads(line)
                except (ValueError, TypeError):
                    continue
                token = payload_line.get("message", {}).get("content")
                if token:
                    yield token
                if payload_line.get("done"):
                    return
    except Exception:
        return
