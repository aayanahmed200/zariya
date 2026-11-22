"""Keyless hosted inference through Kilo's anonymous free-model pool.

Kilo supports unauthenticated requests to free models with shared IP-based
rate limits. Vercel AI Gateway remains an optional server-side fallback when
a Vercel OIDC token or server-owned gateway key is available. No visitor
credential is ever required or exposed.
"""
from __future__ import annotations

import base64
import json
import os
from collections.abc import Iterator

import requests

GATEWAY_BASE_URL = "https://ai-gateway.vercel.sh/v1"
KILO_BASE_URL = "https://ai-gateway.kilo.ai/api/v1"
DEFAULT_MODEL = os.environ.get(
    "AI_GATEWAY_MODEL", "nvidia/nemotron-3.5-lightning-free"
).strip()
KILO_MODEL = os.environ.get("KILO_AI_MODEL", "kilo-auto/free").strip() or "kilo-auto/free"
MAX_OUTPUT_TOKENS = 1800


class GatewayError(RuntimeError):
    """Safe, user-facing model gateway error without secrets or raw headers."""


def _token(oidc_token: str | None = None) -> str:
    # Vercel injects its short-lived OIDC token into each function request.
    return (
        (oidc_token or "").strip()
        or os.environ.get("VERCEL_OIDC_TOKEN", "").strip()
        or os.environ.get("AI_GATEWAY_API_KEY", "").strip()
    )


def configured(oidc_token: str | None = None) -> bool:
    # Kilo's free-model pool explicitly supports anonymous requests.
    # No account, app secret, or visitor API key is required.
    return True


def connection_status(oidc_token: str | None = None) -> dict:
    return {
        "configured": True,
        "available": True,
        "status": "Free AI enabled · shared anonymous model pool",
        "model": KILO_MODEL,
        "provider": "Kilo AI Gateway",
    }


def _kilo_headers(accept: str = "application/json") -> dict[str, str]:
    # No Authorization header: anonymous free-model requests are supported.
    return {
        "Content-Type": "application/json",
        "Accept": accept,
        "HTTP-Referer": "https://zariyas.vercel.app/",
        "X-Title": "Zariya",
    }


def _headers(
    accept: str = "application/json",
    oidc_token: str | None = None,
) -> dict[str, str]:
    token = _token(oidc_token)
    if not token:
        raise GatewayError(
            "Hosted AI is not connected on this deployment. Please try again later."
        )
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": accept,
        "HTTP-Referer": "https://zariyas.vercel.app/",
        "X-Title": "Zariya",
    }


def _friendly_http_error(response: requests.Response) -> str:
    detail = ""
    try:
        payload = response.json()
        if isinstance(payload, dict):
            error = payload.get("error", payload)
            if isinstance(error, dict):
                detail = str(error.get("code") or error.get("type") or "")
            elif isinstance(error, str):
                detail = error
    except (ValueError, TypeError):
        pass

    if response.status_code == 401:
        return "The hosted AI service could not authenticate this deployment. Please try again later."
    if response.status_code == 402:
        return "The hosted AI service rejected this request. The free model may be temporarily unavailable."
    if response.status_code == 403:
        return "The hosted AI service requires account verification before it can respond. Please try again later."
    if response.status_code == 404:
        return "The selected hosted model is temporarily unavailable."
    if response.status_code == 429:
        return "The free model is busy or its shared request limit has been reached. Please try again shortly."
    if response.status_code in (502, 503, 504) or response.status_code >= 500:
        return "The hosted model provider is temporarily unavailable. Please try again in a moment."
    if detail:
        return f"The hosted AI request was rejected ({detail}). Please try again."
    return f"The hosted AI request failed (HTTP {response.status_code}). Please try again."


def _request_error(exc: Exception) -> str:
    if isinstance(exc, requests.Timeout):
        return "The hosted model took too long to respond. Please try again."
    if isinstance(exc, requests.ConnectionError):
        return "Could not reach the hosted AI service. Please try again."
    return "The hosted AI request failed. Please try again."


def _build_messages(
    messages: list[dict], system_prompt: str
) -> list[dict[str, str]]:
    result = [{"role": "system", "content": system_prompt}]
    result.extend(
        {"role": item["role"], "content": item["content"]}
        for item in messages[-24:]
        if item.get("role") in ("user", "assistant")
        and isinstance(item.get("content"), str)
    )
    return result


def _payload(
    messages: list[dict],
    system_prompt: str,
    temperature: float | None,
    stream: bool,
    model: str = DEFAULT_MODEL,
) -> dict:
    payload = {
        "model": model,
        "messages": _build_messages(messages, system_prompt),
        "stream": stream,
        "max_tokens": MAX_OUTPUT_TOKENS,
    }
    if temperature is not None:
        payload["temperature"] = max(0.0, min(1.0, float(temperature)))
    return payload


def _raise_for_status(response: requests.Response) -> None:
    if not response.ok:
        raise GatewayError(_friendly_http_error(response))


def _extract_content(data: dict) -> str | None:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    message = choices[0].get("message", {})
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    if isinstance(content, str):
        return content.strip() or None
    if isinstance(content, list):
        parts = [
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        ]
        joined = "".join(parts).strip()
        return joined or None
    return None


def _kilo_http_error(response: requests.Response) -> str:
    if response.status_code in (401, 403):
        return "The free model gateway temporarily refused anonymous access. Please try again later."
    if response.status_code == 402:
        return "The selected free model is temporarily unavailable. Please try again later."
    if response.status_code == 404:
        return "The free model pool has changed. Please try again later."
    if response.status_code == 429:
        return "The shared free-model request limit has been reached. Wait a little, then try again."
    if response.status_code >= 500:
        return "The free model service is temporarily unavailable. Please try again."
    return f"The free model request failed (HTTP {response.status_code}). Please try again."


def _kilo_payload(
    messages: list[dict],
    system_prompt: str,
    temperature: float | None,
    stream: bool,
) -> dict:
    return _payload(messages, system_prompt, temperature, stream, model=KILO_MODEL)


def _iter_sse_reply(url: str, headers: dict[str, str], payload: dict) -> Iterator[str]:
    with requests.post(
        url,
        headers=headers,
        json=payload,
        stream=True,
        timeout=(12, 75),
    ) as response:
        if not response.ok:
            if url.startswith(KILO_BASE_URL):
                raise GatewayError(_kilo_http_error(response))
            _raise_for_status(response)
        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue
            if isinstance(line, bytes):
                line = line.decode("utf-8", errors="replace")
            line = line.strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                return
            try:
                chunk = json.loads(data)
            except (ValueError, TypeError):
                continue
            if isinstance(chunk, dict) and chunk.get("error"):
                raise GatewayError("The hosted model could not complete this response. Please try again.")
            choices = chunk.get("choices", []) if isinstance(chunk, dict) else []
            if not choices:
                continue
            delta = choices[0].get("delta", {})
            # Never expose separate internal reasoning fields from some models.
            content = delta.get("content") if isinstance(delta, dict) else None
            if isinstance(content, str) and content:
                yield content


def generate_reply(
    messages: list[dict],
    system_prompt: str,
    temperature: float | None = None,
    oidc_token: str | None = None,
) -> str:
    """Generate through anonymous Kilo free models, then optional Vercel fallback."""
    first_error: GatewayError | None = None
    try:
        response = requests.post(
            f"{KILO_BASE_URL}/chat/completions",
            headers=_kilo_headers(),
            json=_kilo_payload(messages, system_prompt, temperature, stream=False),
            timeout=(12, 75),
        )
        if not response.ok:
            raise GatewayError(_kilo_http_error(response))
        answer = _extract_content(response.json())
        if answer:
            return answer
        raise GatewayError("The free model returned an empty response. Please try again.")
    except GatewayError as exc:
        first_error = exc
    except (requests.RequestException, ValueError, TypeError) as exc:
        first_error = GatewayError(_request_error(exc))

    # A server-owned Vercel credential is a secondary route only.
    token = _token(oidc_token)
    if token:
        try:
            response = requests.post(
                f"{GATEWAY_BASE_URL}/chat/completions",
                headers=_headers("application/json", oidc_token),
                json=_payload(messages, system_prompt, temperature, stream=False),
                timeout=(10, 60),
            )
            _raise_for_status(response)
            answer = _extract_content(response.json())
            if answer:
                return answer
        except GatewayError:
            pass
        except (requests.RequestException, ValueError, TypeError):
            pass

    raise first_error or GatewayError("The free model service is temporarily unavailable.")


def stream_reply(
    messages: list[dict],
    system_prompt: str,
    temperature: float | None = None,
    oidc_token: str | None = None,
) -> Iterator[str]:
    """Stream anonymous Kilo free-model output, with an optional Vercel fallback."""
    emitted = False
    first_error: GatewayError | None = None
    try:
        for part in _iter_sse_reply(
            f"{KILO_BASE_URL}/chat/completions",
            _kilo_headers("text/event-stream"),
            _kilo_payload(messages, system_prompt, temperature, stream=True),
        ):
            emitted = True
            yield part
        if emitted:
            return
        first_error = GatewayError("The free model returned an empty response. Please try again.")
    except GatewayError as exc:
        if emitted:
            raise GatewayError("The free-model stream stopped before the answer was complete.") from exc
        first_error = exc
    except (requests.RequestException, ValueError, TypeError) as exc:
        if emitted:
            raise GatewayError("The free-model stream stopped before the answer was complete.") from exc
        first_error = GatewayError(_request_error(exc))

    token = _token(oidc_token)
    if token:
        try:
            for part in _iter_sse_reply(
                f"{GATEWAY_BASE_URL}/chat/completions",
                _headers("text/event-stream", oidc_token),
                _payload(messages, system_prompt, temperature, stream=True),
            ):
                emitted = True
                yield part
            if emitted:
                return
        except GatewayError:
            pass
        except (requests.RequestException, ValueError, TypeError):
            pass

    raise first_error or GatewayError("The free model service is temporarily unavailable.")


def transcribe_audio(
    audio_bytes: bytes,
    media_type: str = "audio/wav",
    language: str | None = None,
    oidc_token: str | None = None,
) -> dict:
    """Transcribe a short browser-recorded WAV through Vercel AI Gateway."""
    token = _token(oidc_token)
    if not token:
        raise GatewayError(
            "Hosted transcription is not connected on this deployment. Please try again later."
        )
    if not isinstance(audio_bytes, bytes) or not audio_bytes:
        raise GatewayError("No microphone audio was received. Please record again.")
    if len(audio_bytes) > 2_500_000:
        raise GatewayError("That recording is too large. Keep voice notes under 60 seconds.")
    if media_type != "audio/wav":
        raise GatewayError("The recording format was not supported. Please record again.")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "ai-gateway-protocol-version": "0.0.1",
        "ai-transcription-model-specification-version": "4",
        "ai-model-id": "microsoft/mai-transcribe-2",
        "HTTP-Referer": "https://zariyas.vercel.app/",
        "X-Title": "Zariya",
    }
    payload = {
        "audio": base64.b64encode(audio_bytes).decode("ascii"),
        "mediaType": media_type,
    }
    if language in ("en", "ur"):
        payload["providerOptions"] = {"azure": {"language": language}}

    try:
        response = requests.post(
            "https://ai-gateway.vercel.sh/v4/ai/transcription-model",
            headers=headers,
            json=payload,
            timeout=(8, 50),
        )
        _raise_for_status(response)
        data = response.json()
        transcript = data.get("text") if isinstance(data, dict) else None
        if not isinstance(transcript, str) or not transcript.strip():
            raise GatewayError("No clear speech was detected. Try speaking a little closer to the microphone.")
        return {
            "text": transcript.strip(),
            "language": data.get("language"),
            "durationInSeconds": data.get("durationInSeconds"),
        }
    except GatewayError:
        raise
    except (requests.RequestException, ValueError, TypeError) as exc:
        raise GatewayError(_request_error(exc)) from exc
