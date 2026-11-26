"""Encrypted Supabase Auth sessions for the server-rendered Flask app.

Only an encrypted access/refresh-token pair is stored in the signed Flask
session cookie. The publishable key is used for Auth; the service-role/secret
key is never used for sign-in and is never sent to the browser.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from typing import Any, MutableMapping

from cryptography.fernet import Fernet, InvalidToken
from supabase import create_client


SESSION_FIELD = "zariya_supabase_auth"
USER_ID_FIELD = "zariya_supabase_user_id"
EMAIL_FIELD = "zariya_supabase_email"
PROVIDER_FIELD = "zariya_auth_provider"


class AuthSessionError(RuntimeError):
    """Raised when a Supabase session cannot be safely established."""


def _url() -> str:
    return (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")


def _publishable_key() -> str:
    return (
        os.environ.get("SUPABASE_PUBLISHABLE_KEY")
        or os.environ.get("SUPABASE_ANON_KEY")
        or ""
    ).strip()


def configured() -> bool:
    secret = (os.environ.get("FLASK_SECRET_KEY") or "").strip()
    key = _publishable_key()
    return (
        _url().startswith("https://")
        and (key.startswith("sb_publishable_") or (key.startswith("eyJ") and key.count(".") == 2))
        and len(secret) >= 32
    )


def create_auth_client() -> Any:
    if not configured():
        raise AuthSessionError("Email sign-in is not configured.")
    # Always create a request-scoped client. Never share AuthClient/session state
    # between Vercel invocations or users.
    return create_client(_url(), _publishable_key())


def _cipher() -> Fernet:
    secret = (os.environ.get("FLASK_SECRET_KEY") or "").strip()
    if len(secret) < 32:
        raise AuthSessionError("A stable Flask session secret is required.")
    derived = hashlib.sha256(b"zariya-supabase-auth-session:" + secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(derived))


def _value(obj: Any, name: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _session_from_response(response: Any) -> Any:
    value = _value(response, "session")
    if value is not None:
        return value
    data = _value(response, "data")
    return _value(data, "session")


def _user_from_response(response: Any) -> Any:
    value = _value(response, "user")
    if value is not None:
        return value
    data = _value(response, "data")
    return _value(data, "user")


def store_session(
    flask_session: MutableMapping[str, Any],
    user: Any,
    auth_session: Any,
) -> None:
    user_id = _value(user, "id")
    email = _value(user, "email")
    access_token = _value(auth_session, "access_token")
    refresh_token = _value(auth_session, "refresh_token")
    if not all(isinstance(v, str) and v for v in (user_id, access_token, refresh_token)):
        raise AuthSessionError("Supabase did not return a complete sign-in session.")

    payload = json.dumps(
        {"access_token": access_token, "refresh_token": refresh_token},
        separators=(",", ":"),
    ).encode("utf-8")
    flask_session[SESSION_FIELD] = _cipher().encrypt(payload).decode("ascii")
    flask_session[USER_ID_FIELD] = user_id
    flask_session[EMAIL_FIELD] = (email or "").strip().lower()
    flask_session[PROVIDER_FIELD] = "supabase"
    flask_session.pop("github_login", None)
    flask_session.permanent = True


def clear_session(flask_session: MutableMapping[str, Any]) -> None:
    for key in (SESSION_FIELD, USER_ID_FIELD, EMAIL_FIELD):
        flask_session.pop(key, None)
    if flask_session.get(PROVIDER_FIELD) == "supabase":
        flask_session.pop(PROVIDER_FIELD, None)


def load_session(flask_session: MutableMapping[str, Any]) -> tuple[Any, Any, Any] | None:
    """Validate/refresh the encrypted session and return (client, user, session).

    The access token is verified against Supabase Auth on each server-side
    restore. set_session refreshes it when necessary; rotated tokens are
    encrypted back into the cookie before they are returned.
    """
    encrypted = flask_session.get(SESSION_FIELD)
    expected_user_id = flask_session.get(USER_ID_FIELD)
    if not isinstance(encrypted, str) or not isinstance(expected_user_id, str):
        return None
    try:
        raw = _cipher().decrypt(encrypted.encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
        access_token = payload.get("access_token")
        refresh_token = payload.get("refresh_token")
        if not isinstance(access_token, str) or not isinstance(refresh_token, str):
            raise AuthSessionError("Invalid session contents.")

        client = create_auth_client()
        refreshed = client.auth.set_session(access_token, refresh_token)
        auth_session = _session_from_response(refreshed)
        if auth_session is None:
            auth_session = client.auth.get_session()
        current_access = _value(auth_session, "access_token") or access_token

        verified = client.auth.get_user(current_access)
        user = _user_from_response(verified)
        if _value(user, "id") != expected_user_id:
            raise AuthSessionError("The account session could not be verified.")

        new_access = _value(auth_session, "access_token")
        new_refresh = _value(auth_session, "refresh_token")
        if new_access and new_refresh and (new_access != access_token or new_refresh != refresh_token):
            store_session(flask_session, user, auth_session)
        return client, user, auth_session
    except (InvalidToken, ValueError, TypeError, AuthSessionError):
        clear_session(flask_session)
        return None
    except Exception:
        # A transient network/Auth outage must not destroy a user's refresh
        # token. The request is treated as unauthenticated until verification
        # succeeds on a later request.
        return None


def establish_session(
    flask_session: MutableMapping[str, Any],
    access_token: str,
    refresh_token: str,
) -> tuple[Any, Any]:
    if not isinstance(access_token, str) or not isinstance(refresh_token, str):
        raise AuthSessionError("The confirmation did not return a complete session.")
    if not (20 <= len(access_token) <= 10000 and 20 <= len(refresh_token) <= 2000):
        raise AuthSessionError("The confirmation session is invalid.")
    client = create_auth_client()
    response = client.auth.set_session(access_token, refresh_token)
    auth_session = _session_from_response(response) or client.auth.get_session()
    verified = client.auth.get_user(_value(auth_session, "access_token") or access_token)
    user = _user_from_response(verified)
    if not user or not _value(user, "id"):
        raise AuthSessionError("The confirmed account could not be verified.")
    store_session(flask_session, user, auth_session)
    return user, auth_session
