"""Request-level protections for the Zariya web app.

Everything here is deliberately dependency-free: the app deploys as a single
Vercel function, so a small in-process limiter is a better fit than pulling in
a Redis client. Limits are per client IP and reset when the function instance
is recycled, which is enough to stop accidental hammering and casual abuse.

Contents:
  * SlidingWindowLimiter -- bounded, thread-safe request counter.
  * rate_limit()        -- per-route decorator (login, AI, writes).
  * require_same_origin -- rejects cross-site writes (CSRF defence).
  * install()           -- security headers, CORS lockdown, JSON error shapes.
"""
from __future__ import annotations

import threading
import time
from functools import wraps
from urllib.parse import urlparse

from flask import jsonify, request
from werkzeug.exceptions import HTTPException

# Largest request body we accept. The workspace sync allows 2 MB of JSON and a
# voice note arrives as base64 audio, so this is a hard ceiling well above both
# but far below anything that could exhaust a function's memory.
MAX_REQUEST_BYTES = 6 * 1024 * 1024


def client_ip() -> str:
    """Best-effort client address, preferring the proxy's forwarding header."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first[:64]
    return (request.remote_addr or "unknown")[:64]


class SlidingWindowLimiter:
    """Counts hits per key inside a rolling window, with a bounded key set."""

    def __init__(self, max_keys: int = 4096):
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()
        self._max_keys = max_keys

    def hit(self, key: str, limit: int, window: float) -> bool:
        """Record a hit. Returns False when the caller is over the limit."""
        now = time.monotonic()
        with self._lock:
            stamps = [stamp for stamp in self._hits.get(key, ()) if now - stamp < window]
            if len(stamps) >= limit:
                self._hits[key] = stamps
                return False
            stamps.append(now)
            self._hits[key] = stamps
            if len(self._hits) > self._max_keys:
                # Evict the least recently active key so memory stays bounded.
                oldest = min(self._hits, key=lambda k: self._hits[k][-1])
                self._hits.pop(oldest, None)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


LIMITER = SlidingWindowLimiter()


def reset_rate_limits() -> None:
    LIMITER.reset()


def rate_limit(name: str, limit: int, window: float = 60.0):
    """Allow `limit` requests per `window` seconds per client IP."""

    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if not LIMITER.hit(f"{name}:{client_ip()}", limit, window):
                response = jsonify({"error": "Too many requests. Please wait a moment and try again."})
                response.status_code = 429
                response.headers["Retry-After"] = str(int(window))
                return response
            return view(*args, **kwargs)

        return wrapper

    return decorator


def _origin_matches_host(origin: str) -> bool:
    parsed = urlparse(origin)
    if not parsed.netloc:
        return False
    return parsed.netloc.casefold() == request.host.casefold()


def is_same_origin_request() -> bool:
    """True when the browser told us the request came from this same host.

    Browsers send Origin on cross-site requests and on same-site POSTs; when it
    is absent (older clients, curl, server-to-server) the SameSite=Lax session
    cookie already keeps a foreign site from acting as the user, so we allow it.
    """
    origin = request.headers.get("Origin")
    if origin:
        return _origin_matches_host(origin)
    referer = request.headers.get("Referer")
    if referer:
        return _origin_matches_host(referer)
    return True


def require_same_origin(view):
    """Block cross-site writes before they reach a route that changes data."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        if request.method not in ("GET", "HEAD", "OPTIONS") and not is_same_origin_request():
            return jsonify({"error": "This request was blocked because it came from another site."}), 403
        return view(*args, **kwargs)

    return wrapper


CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "img-src 'self' data: https:; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com data:; "
    "script-src 'self' 'unsafe-inline'; "
    "connect-src 'self'; "
    "media-src 'self' blob:; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)

_PUBLIC_ERRORS = {
    400: "That request could not be understood.",
    401: "Please sign in to continue.",
    403: "That request is not allowed.",
    404: "Not found.",
    405: "That method is not allowed here.",
    413: "That request is too large.",
    429: "Too many requests. Please wait a moment and try again.",
}


def install(app) -> None:
    """Attach headers, error shapes and the request size ceiling to `app`."""
    app.config["MAX_CONTENT_LENGTH"] = MAX_REQUEST_BYTES
    app.config["PROPAGATE_EXCEPTIONS"] = False

    @app.after_request
    def _security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "microphone=(self), camera=(), geolocation=()")
        response.headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        # No cross-origin reads: drop any wildcard CORS header a dependency or
        # future change might add, and keep the app same-origin only.
        response.headers.pop("Access-Control-Allow-Origin", None)
        response.headers.pop("Access-Control-Allow-Credentials", None)
        return response

    @app.errorhandler(HTTPException)
    def _handle_http_error(exc: HTTPException):
        if not request.path.startswith("/api/"):
            return exc
        message = _PUBLIC_ERRORS.get(exc.code or 500, "That request could not be completed.")
        return jsonify({"error": message}), exc.code or 500

    @app.errorhandler(Exception)
    def _handle_unexpected_error(exc: Exception):
        # Log the detail for operators, return none of it to the caller: no
        # stack traces, SQL text, provider responses or filesystem paths.
        app.logger.exception("Unhandled error on %s", request.path)
        if request.path.startswith("/api/"):
            return jsonify({"error": "Something went wrong on our side. Please try again."}), 500
        return "Something went wrong. Please try again.", 500
