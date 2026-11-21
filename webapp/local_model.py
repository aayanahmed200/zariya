"""Ollama inference for local development and hosted Vercel deployments.

Local development uses the Ollama daemon at http://localhost:11434 by default.
Vercel uses Ollama Cloud at https://ollama.com and requires OLLAMA_API_KEY.
Credentials stay server-side and are never returned by an API route.
"""
from __future__ import annotations

import json
import os
import re
import threading
from urllib.parse import urlparse

import requests

HOSTED_MODE = bool(os.environ.get("VERCEL"))
OLLAMA_BASE_URL = (
    os.environ.get("OLLAMA_BASE_URL")
    or os.environ.get("OLLAMA_URL")
    or ("https://ollama.com" if HOSTED_MODE else "http://localhost:11434")
).rstrip("/")
OLLAMA_API_KEY = os.environ.get("OLLAMA_API_KEY", "").strip()
DEFAULT_MODEL = os.environ.get(
    "OLLAMA_MODEL",
    "gemma4:31b" if HOSTED_MODE else "qwen2.5:1.5b",
).strip()

_CLOUD_HOSTS = {"ollama.com", "www.ollama.com"}
_MODE = "cloud" if (urlparse(OLLAMA_BASE_URL).hostname or "").lower() in _CLOUD_HOSTS else (
    "remote" if HOSTED_MODE else "local"
)
_status = "Checking Ollama"
_progress = {"completed": 0, "total": 0}
_last_error = ""
_pull_thread: threading.Thread | None = None
_pull_lock = threading.Lock()
_probe_cache = {"at": 0.0, "available": False, "status": "Not checked"}
_MODEL_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")


class OllamaError(RuntimeError):
    """A safe, user-facing Ollama error without credentials or request headers."""


def current_model() -> str:
    return DEFAULT_MODEL


def mode() -> str:
    return _MODE


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if OLLAMA_API_KEY:
        headers["Authorization"] = f"Bearer {OLLAMA_API_KEY}"
    return headers


def configured() -> bool:
    if HOSTED_MODE:
        # Vercel must use an authenticated endpoint. Direct Ollama Cloud
        # requires an API key; private self-hosted endpoints should too.
        return bool(OLLAMA_API_KEY) and not OLLAMA_BASE_URL.startswith(("http://localhost", "http://127.0.0.1"))
    if _MODE in ("cloud", "remote"):
        return bool(OLLAMA_API_KEY)
    return True


def _friendly_http_error(response: requests.Response) -> str:
    if response.status_code in (401, 403):
        return "Ollama rejected the API key. Check OLLAMA_API_KEY in your deployment settings."
    if response.status_code == 402:
        return "Ollama Cloud needs usage credits for this model. Connect local Ollama in Settings to use a model on this device without cloud charges."
    if response.status_code == 404:
        return "Ollama could not find that model. Choose a model listed in Settings."
    if response.status_code == 429:
        return "Ollama is busy or the current usage limit was reached. Try again shortly."
    if response.status_code >= 500:
        return "Ollama is temporarily unavailable. Try again in a moment."
    return f"Ollama returned HTTP {response.status_code}. Check the endpoint and model settings."


def _request_error(exc: Exception) -> str:
    if isinstance(exc, requests.Timeout):
        return "Ollama took too long to respond. Try again or choose a smaller model."
    if isinstance(exc, requests.ConnectionError):
        return "Could not connect to Ollama. Check the configured Ollama endpoint."
    return "The Ollama request failed. Check the model and endpoint settings."


def _probe(force: bool = False) -> tuple[bool, str]:
    """Check a local/remote Ollama server. Ollama Cloud has no local model
    inventory endpoint, so for Cloud we validate presence of the API key here
    and let the first chat request verify that the key and model are accepted."""
    global _probe_cache, _status
    if not configured():
        if HOSTED_MODE:
            _status = "Add OLLAMA_API_KEY in Vercel Environment Variables to connect Ollama Cloud."
        else:
            _status = "Start Ollama locally, or configure an authenticated remote Ollama endpoint."
        return False, _status

    import time
    now = time.monotonic()
    if _MODE == "cloud":
        status_text = f"Ollama Cloud key set · {DEFAULT_MODEL} (verified on first message)"
        _probe_cache = {"at": now, "available": True, "status": status_text}
        _status = status_text
        return True, status_text

    if not force and now - _probe_cache["at"] < 15:
        return bool(_probe_cache["available"]), str(_probe_cache["status"])

    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", headers=_headers(), timeout=6)
        if not response.ok:
            status_text = _friendly_http_error(response)
            available = False
        else:
            available = True
            status_text = f"Ollama server connected · {DEFAULT_MODEL}"
    except requests.RequestException as exc:
        available = False
        status_text = _request_error(exc)

    _probe_cache = {"at": now, "available": available, "status": status_text}
    _status = status_text
    return available, status_text


def connection_status() -> dict:
    available, status_text = _probe()
    return {
        "configured": configured(),
        "available": available,
        "mode": _MODE,
        "status": status_text,
        "model": DEFAULT_MODEL,
    }


def is_available() -> bool:
    return _probe()[0]


def load_status() -> str:
    return _probe()[1]


def load_progress() -> dict:
    return dict(_progress)


def last_error() -> str:
    return _last_error


def list_models() -> list[dict]:
    """List locally available models, or show the configured Cloud model.

    Ollama Cloud's direct API exposes chat/inference endpoints rather than the
    local daemon's /api/tags inventory, so cloud users can switch model names
    manually in Settings.
    """
    if not configured():
        return []
    if _MODE == "cloud":
        return [{"name": DEFAULT_MODEL, "size": 0}]
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", headers=_headers(), timeout=8)
        response.raise_for_status()
        data = response.json()
        models = data.get("models", []) if isinstance(data, dict) else []
        return [
            {"name": str(item.get("name", "")), "size": int(item.get("size") or 0)}
            for item in models
            if isinstance(item, dict) and item.get("name")
        ]
    except (requests.RequestException, ValueError, TypeError):
        return []


def _valid_model_name(name: str) -> bool:
    return bool(_MODEL_NAME_RE.fullmatch(name.strip()))


def set_active_model(name: str) -> dict:
    """Select a model from the configured endpoint.

    Hosted mode only changes the selected model; the cloud endpoint owns model
    availability and downloads. Local mode may pull a missing model.
    """
    global DEFAULT_MODEL, _status, _probe_cache
    name = (name or "").strip()
    if not _valid_model_name(name):
        return {"ok": False, "error": "Enter a valid Ollama model name, such as gemma4:31b."}
    if HOSTED_MODE:
        if not configured():
            return {"ok": False, "error": "Add OLLAMA_API_KEY in Vercel before selecting an Ollama Cloud model."}
        DEFAULT_MODEL = name
        _status = f"Selected {name}"
        _probe_cache = {"at": 0.0, "available": False, "status": "Model selection changed"}
        return {"ok": True, "model": DEFAULT_MODEL, "pulling": False}

    available, _ = _probe(force=True)
    if not available:
        return {"ok": False, "error": _status}
    names = {item["name"] for item in list_models()}
    if name in names or (":" not in name and any(item.startswith(name + ":") for item in names)):
        DEFAULT_MODEL = name
        _status = f"Ollama connected · {DEFAULT_MODEL}"
        return {"ok": True, "model": DEFAULT_MODEL, "pulling": False}

    if _MODE != "local":
        return {"ok": False, "error": "The selected model is not available on this Ollama endpoint."}
    result = _start_pull(name)
    return result


def _start_pull(model: str) -> dict:
    global _pull_thread
    if HOSTED_MODE or _MODE != "local":
        return {"ok": False, "error": "Model downloads are only supported by a local Ollama server."}
    with _pull_lock:
        if _pull_thread and _pull_thread.is_alive():
            return {"ok": False, "error": "An Ollama model download is already running."}
        _pull_thread = threading.Thread(target=_pull_and_activate, args=(model,), daemon=True)
        _pull_thread.start()
    return {"ok": True, "model": model, "pulling": True, "status": f"Downloading {model} from Ollama…"}


def _pull_and_activate(model: str) -> None:
    global DEFAULT_MODEL, _status, _progress, _probe_cache
    _progress = {"completed": 0, "total": 0}
    try:
        with requests.post(
            f"{OLLAMA_BASE_URL}/api/pull",
            headers=_headers(),
            json={"name": model, "stream": True},
            stream=True,
            timeout=(10, 900),
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except (ValueError, TypeError):
                    continue
                if payload.get("error"):
                    _status = "Ollama could not download that model. Check the model name and available disk space."
                    return
                total = payload.get("total")
                completed = payload.get("completed")
                if isinstance(total, int):
                    _progress["total"] = total
                if isinstance(completed, int):
                    _progress["completed"] = completed
                if payload.get("status"):
                    _status = str(payload["status"])
        DEFAULT_MODEL = model
        _status = f"Model ready · {model}"
        _probe_cache = {"at": 0.0, "available": True, "status": _status}
    except requests.RequestException as exc:
        _status = _request_error(exc)
    finally:
        if _progress["total"] and _progress["completed"] >= _progress["total"]:
            _progress = {"completed": 0, "total": 0}


def retry_now() -> dict:
    if HOSTED_MODE or _MODE != "local":
        return {"ok": False, "status": "Ollama Cloud manages hosted models; local pulls are not available on Vercel."}
    if not configured():
        return {"ok": False, "status": "Start your local Ollama server first."}
    result = _start_pull(DEFAULT_MODEL)
    return {"ok": result.get("ok", False), "status": result.get("status", result.get("error", ""))}


def _normalise_messages(messages: list[dict], system_prompt: str) -> list[dict]:
    result = [{"role": "system", "content": system_prompt}]
    result.extend(
        {"role": item["role"], "content": item["content"]}
        for item in messages[-24:]
        if item.get("role") in ("user", "assistant") and isinstance(item.get("content"), str)
    )
    return result


def _chat_payload(messages: list[dict], system_prompt: str, temperature: float | None, model: str | None) -> dict:
    payload = {
        "model": model.strip() if isinstance(model, str) and _valid_model_name(model.strip()) else DEFAULT_MODEL,
        "messages": _normalise_messages(messages, system_prompt),
        "stream": True,
        "options": {"num_predict": 1200},
    }
    if temperature is not None:
        payload["options"]["temperature"] = max(0.0, min(1.0, float(temperature)))
    return payload


def _raise_response_error(response: requests.Response) -> None:
    if not response.ok:
        raise OllamaError(_friendly_http_error(response))


def generate_reply(
    messages: list[dict],
    system_prompt: str,
    temperature: float | None = None,
    model: str | None = None,
) -> str | None:
    if not is_available():
        return None
    payload = _chat_payload(messages, system_prompt, temperature, model)
    payload["stream"] = False
    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            headers=_headers(),
            json=payload,
            timeout=(10, 55),
        )
        _raise_response_error(response)
        data = response.json()
        answer = data.get("message", {}).get("content")
        return answer if isinstance(answer, str) and answer.strip() else None
    except OllamaError:
        raise
    except (requests.RequestException, ValueError, TypeError) as exc:
        raise OllamaError(_request_error(exc)) from exc


def stream_reply(
    messages: list[dict],
    system_prompt: str,
    temperature: float | None = None,
    model: str | None = None,
):
    """Yield content tokens from Ollama's streaming chat endpoint."""
    if not is_available():
        raise OllamaError(load_status())
    payload = _chat_payload(messages, system_prompt, temperature, model)
    try:
        with requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            headers=_headers(),
            json=payload,
            stream=True,
            timeout=(10, 55),
        ) as response:
            _raise_response_error(response)
            for line in response.iter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except (ValueError, TypeError):
                    continue
                if chunk.get("error"):
                    raise OllamaError("Ollama reported an error while generating the response.")
                token = chunk.get("message", {}).get("content")
                if isinstance(token, str) and token:
                    yield token
                if chunk.get("done"):
                    return
    except OllamaError:
        raise
    except (requests.RequestException, ValueError, TypeError) as exc:
        raise OllamaError(_request_error(exc)) from exc
