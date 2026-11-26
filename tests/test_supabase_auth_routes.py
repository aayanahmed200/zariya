import os
os.environ.setdefault("VERCEL", "1")
os.environ.setdefault("FLASK_SECRET_KEY", "test-only-zariya-secret-which-is-long-enough")

from types import SimpleNamespace
from unittest.mock import Mock

from webapp import app as webapp_module

# The app imports these modules as top-level names after index.py adds webapp/
# to sys.path. Patch those exact module objects used by the registered routes.
auth_sessions = webapp_module.auth_sessions
security = webapp_module.security


USER_ID = "5c5f5c75-9e2e-4ad5-a18b-0bb85fce6d6b"
STATE = {"sessions": [], "notes": [], "decks": []}


def client():
    security.reset_rate_limits()
    return webapp_module.app.test_client()


class FakeAuth:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.signup_payload = None
        self.login_payload = None
        self.signed_out = False

    def sign_up(self, payload):
        self.signup_payload = payload
        if self.error:
            raise self.error
        return self.result

    def sign_in_with_password(self, payload):
        self.login_payload = payload
        if self.error:
            raise self.error
        return self.result

    def sign_out(self):
        self.signed_out = True


class FakeClient:
    def __init__(self, auth):
        self.auth = auth


def test_signup_uses_supabase_auth_confirmation_and_never_returns_tokens(monkeypatch):
    monkeypatch.setattr(webapp_module, "SUPABASE_AUTH_CONFIGURED", True)
    fake_auth = FakeAuth(result=SimpleNamespace(user=SimpleNamespace(id=USER_ID), session=None))
    monkeypatch.setattr(auth_sessions, "create_auth_client", lambda: FakeClient(fake_auth))
    monkeypatch.setattr(auth_sessions, "store_auth_response", lambda flask_session, response: False)

    response = client().post(
        "/api/auth/signup",
        json={"email": " Student@Example.com ", "password": "a-strong-test-password"},
        headers={"Origin": "http://localhost"},
    )

    assert response.status_code == 201
    assert response.get_json()["confirmationRequired"] is True
    assert fake_auth.signup_payload["email"] == "student@example.com"
    assert fake_auth.signup_payload["options"]["email_redirect_to"].endswith("/auth/confirm")
    body = response.get_data(as_text=True)
    assert "access_token" not in body
    assert "refresh_token" not in body


def test_signin_stores_supabase_session_server_side(monkeypatch):
    monkeypatch.setattr(webapp_module, "SUPABASE_AUTH_CONFIGURED", True)
    fake_auth = FakeAuth(result=SimpleNamespace(user=SimpleNamespace(id=USER_ID), session=object()))
    monkeypatch.setattr(auth_sessions, "create_auth_client", lambda: FakeClient(fake_auth))
    monkeypatch.setattr(auth_sessions, "store_auth_response", lambda flask_session, response: True)

    response = client().post(
        "/api/auth/login",
        json={"email": "student@example.com", "password": "a-strong-test-password"},
        headers={"Origin": "http://localhost"},
    )

    assert response.status_code == 200
    assert response.get_json()["signedIn"] is True
    assert fake_auth.login_payload == {
        "email": "student@example.com",
        "password": "a-strong-test-password",
    }


def test_signin_error_is_generic_and_does_not_leak_provider_details(monkeypatch):
    monkeypatch.setattr(webapp_module, "SUPABASE_AUTH_CONFIGURED", True)
    fake_auth = FakeAuth(error=RuntimeError("secret internal provider response with token"))
    monkeypatch.setattr(auth_sessions, "create_auth_client", lambda: FakeClient(fake_auth))

    response = client().post(
        "/api/auth/login",
        json={"email": "student@example.com", "password": "wrong-password"},
        headers={"Origin": "http://localhost"},
    )

    assert response.status_code == 401
    assert response.get_json()["error"] == "Email or password is incorrect. Check your details and try again."
    assert "token" not in response.get_data(as_text=True)


def test_auth_rejects_short_password_before_calling_provider(monkeypatch):
    monkeypatch.setattr(webapp_module, "SUPABASE_AUTH_CONFIGURED", True)
    create_client = Mock()
    monkeypatch.setattr(auth_sessions, "create_auth_client", create_client)

    response = client().post(
        "/api/auth/signup",
        json={"email": "student@example.com", "password": "short"},
        headers={"Origin": "http://localhost"},
    )

    assert response.status_code == 400
    assert "8 and 128" in response.get_json()["error"]
    create_client.assert_not_called()


def test_auth_routes_reject_cross_site_posts(monkeypatch):
    monkeypatch.setattr(webapp_module, "SUPABASE_AUTH_CONFIGURED", True)
    create_client = Mock()
    monkeypatch.setattr(auth_sessions, "create_auth_client", create_client)

    response = client().post(
        "/api/auth/login",
        json={"email": "student@example.com", "password": "a-strong-test-password"},
        headers={"Origin": "https://attacker.example"},
    )

    assert response.status_code == 403
    create_client.assert_not_called()


def test_workspace_reads_and_writes_use_verified_supabase_user_id(monkeypatch):
    fake_client = FakeClient(FakeAuth())
    monkeypatch.setattr(
        webapp_module,
        "_supabase_auth_context",
        lambda: (fake_client, SimpleNamespace(id=USER_ID, email="student@example.com"), object()),
    )
    read_calls = []
    write_calls = []

    def fake_get_state(user_id, auth_client):
        read_calls.append((user_id, auth_client))
        return STATE

    def fake_save_state(user_id, state, auth_client):
        write_calls.append((user_id, state, auth_client))

    monkeypatch.setattr(webapp_module.SUPABASE_USER_WORKSPACE_STORE, "get_state", fake_get_state)
    monkeypatch.setattr(webapp_module.SUPABASE_USER_WORKSPACE_STORE, "save_state", fake_save_state)

    c = client()
    with c.session_transaction() as flask_session:
        flask_session[auth_sessions.SESSION_FIELD] = "opaque-encrypted-cookie-value"
    response = c.get("/api/state")
    assert response.status_code == 200
    assert response.get_json() == STATE
    assert read_calls == [(USER_ID, fake_client)]

    response = c.post(
        "/api/state",
        json={**STATE, "user_id": "somebody-elses-id"},
        headers={"Origin": "http://localhost"},
    )
    assert response.status_code == 200
    assert write_calls[0][0] == USER_ID
    assert write_calls[0][1]["sessions"] == []
    assert "user_id" not in write_calls[0][1]


def test_me_only_reports_supabase_user_after_provider_verification(monkeypatch):
    user = SimpleNamespace(id=USER_ID, email="student@example.com")
    monkeypatch.setattr(webapp_module, "_supabase_auth_context", lambda: (FakeClient(FakeAuth()), user, object()))
    c = client()
    with c.session_transaction() as flask_session:
        flask_session[auth_sessions.SESSION_FIELD] = "opaque-encrypted-cookie-value"

    response = c.get("/api/me")

    assert response.status_code == 200
    assert response.get_json()["signedIn"] is True
    assert response.get_json()["authProvider"] == "supabase"
    assert response.get_json()["login"] == "student@example.com"


def test_logout_revokes_provider_session_and_clears_cookie(monkeypatch):
    fake_auth = FakeAuth()
    fake_client = FakeClient(fake_auth)
    monkeypatch.setattr(webapp_module, "_supabase_auth_context", lambda: (fake_client, SimpleNamespace(id=USER_ID), object()))
    c = client()
    with c.session_transaction() as flask_session:
        flask_session[auth_sessions.SESSION_FIELD] = "opaque-encrypted-cookie-value"
        flask_session[auth_sessions.USER_ID_FIELD] = USER_ID

    response = c.post("/auth/logout", headers={"Origin": "http://localhost"})

    assert response.status_code == 200
    assert fake_auth.signed_out is True
    with c.session_transaction() as flask_session:
        assert auth_sessions.SESSION_FIELD not in flask_session
