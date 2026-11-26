import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("FLASK_SECRET_KEY", "test-only-zariya-secret-which-is-long-enough")

from webapp import auth_sessions


USER_ID = "5c5f5c75-9e2e-4ad5-a18b-0bb85fce6d6b"


class FakeFlaskSession(dict):
    permanent = False


class FakeAuth:
    def __init__(self, user, session):
        self.user = user
        self.session = session
        self.received = None

    def set_session(self, access_token, refresh_token):
        self.received = (access_token, refresh_token)
        return SimpleNamespace(session=self.session)

    def get_user(self, access_token=None):
        assert access_token == self.session.access_token
        return SimpleNamespace(user=self.user)


class FakeClient:
    def __init__(self, user, session):
        self.auth = FakeAuth(user, session)


def test_auth_config_uses_only_publishable_key_and_stable_session_secret(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_example_key_123456789")
    monkeypatch.setenv("FLASK_SECRET_KEY", "a" * 48)
    assert auth_sessions.configured()


def test_auth_config_rejects_missing_secret_or_insecure_url(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "http://project.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_example_key_123456789")
    monkeypatch.setenv("FLASK_SECRET_KEY", "a" * 48)
    assert not auth_sessions.configured()
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("FLASK_SECRET_KEY", "short")
    assert not auth_sessions.configured()


def test_session_cookie_encrypts_tokens_and_refreshes_them(monkeypatch):
    monkeypatch.setenv("FLASK_SECRET_KEY", "a" * 48)
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_example_key_123456789")
    user = SimpleNamespace(id=USER_ID, email="student@example.com")
    session_v1 = SimpleNamespace(access_token="access_token_original_123456789", refresh_token="refresh_token_original_123456789")
    session_v2 = SimpleNamespace(access_token="access_token_rotated_123456789", refresh_token="refresh_token_rotated_123456789")
    flask_session = FakeFlaskSession()

    auth_sessions.store_session(flask_session, user, session_v1)
    encrypted_cookie_value = flask_session[auth_sessions.SESSION_FIELD]
    assert "access_token_original" not in encrypted_cookie_value
    assert "refresh_token_original" not in encrypted_cookie_value
    assert flask_session[auth_sessions.USER_ID_FIELD] == USER_ID

    fake_client = FakeClient(user, session_v2)
    monkeypatch.setattr(auth_sessions, "create_auth_client", lambda: fake_client)
    restored = auth_sessions.load_session(flask_session)

    assert restored is not None
    assert restored[1].id == USER_ID
    assert fake_client.auth.received == (
        "access_token_original_123456789",
        "refresh_token_original_123456789",
    )
    assert flask_session[auth_sessions.SESSION_FIELD] != encrypted_cookie_value
    assert "access_token_rotated" not in flask_session[auth_sessions.SESSION_FIELD]


def test_tampered_auth_cookie_is_cleared(monkeypatch):
    monkeypatch.setenv("FLASK_SECRET_KEY", "a" * 48)
    flask_session = {
        auth_sessions.SESSION_FIELD: "not-a-valid-fernet-token",
        auth_sessions.USER_ID_FIELD: USER_ID,
        auth_sessions.PROVIDER_FIELD: "supabase",
    }
    assert auth_sessions.load_session(flask_session) is None
    assert auth_sessions.SESSION_FIELD not in flask_session
    assert auth_sessions.USER_ID_FIELD not in flask_session
    assert auth_sessions.PROVIDER_FIELD not in flask_session


def test_store_session_requires_verified_user_and_refresh_token(monkeypatch):
    monkeypatch.setenv("FLASK_SECRET_KEY", "a" * 48)
    flask_session = {}
    user = SimpleNamespace(id=USER_ID, email="student@example.com")
    with pytest.raises(auth_sessions.AuthSessionError):
        auth_sessions.store_session(
            flask_session,
            user,
            SimpleNamespace(access_token="access_token_valid_123456789", refresh_token=""),
        )
