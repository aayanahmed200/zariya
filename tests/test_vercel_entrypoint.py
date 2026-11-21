import os
from pathlib import Path
from types import SimpleNamespace

os.environ["VERCEL"] = "1"
os.environ.setdefault("FLASK_SECRET_KEY", "test-only-zariya-secret-which-is-long-enough")

import index  # noqa: E402
from webapp import hosted_model  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def test_homepage_renders_hosted_workspace_and_seo():
    response = index.app.test_client().get("/")
    assert response.status_code == 200
    body = response.data
    assert b"Zariya" in body
    assert b"/static/app.js" in body
    assert b"Hosted AI" in body
    assert b"aiModelStatusText" in body
    assert b'rel="canonical"' in body
    assert b"https://zariyas.vercel.app/" in body
    assert b'application/ld+json' in body
    assert b"Urdu" in body
    assert b"Flashcards" in body
    assert b"localDeviceConnectBtn" not in body
    assert b"ollama pull" not in body


def test_static_seo_assets_exist():
    assert (ROOT / "public" / "favicon.svg").is_file()
    assert (ROOT / "public" / "site.webmanifest").is_file()
    assert (ROOT / "public" / "robots.txt").is_file()
    assert (ROOT / "public" / "sitemap.xml").is_file()


def test_profile_avatar_has_nonempty_fallback_and_public_copy_matches():
    app_source = (ROOT / "webapp" / "static" / "app.js").read_text(encoding="utf-8")
    public_source = (ROOT / "public" / "static" / "app.js").read_text(encoding="utf-8")
    assert "escapeHtml(me.avatar||'/static/logo.png')" in app_source
    assert app_source == public_source


def test_health_endpoint_reports_gateway_mode():
    response = index.app.test_client().get("/api/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert data["mode"] == "hosted"
    assert data["aiProvider"] == "Vercel AI Gateway"
    assert data["knowledgeEntries"] > 0


def test_config_reports_gateway_without_exposing_credentials(monkeypatch):
    monkeypatch.delenv("VERCEL_OIDC_TOKEN", raising=False)
    monkeypatch.delenv("AI_GATEWAY_API_KEY", raising=False)
    response = index.app.test_client().get("/api/config")
    assert response.status_code == 200
    data = response.get_json()
    assert data["hostedMode"] is True
    assert data["aiProvider"] == "Vercel AI Gateway"
    assert data["aiConfigured"] is False
    assert data["aiAvailable"] is False
    assert "VERCEL_OIDC_TOKEN" not in str(data)
    assert "AI_GATEWAY_API_KEY" not in str(data)


def test_gateway_uses_vercel_oidc_without_a_provider_key(monkeypatch):
    monkeypatch.setenv("VERCEL_OIDC_TOKEN", "unit-test-oidc-token")
    monkeypatch.delenv("AI_GATEWAY_API_KEY", raising=False)
    status = hosted_model.connection_status()
    assert status["configured"] is True
    assert status["available"] is True
    assert status["model"] == "nvidia/nemotron-3.5-lightning-free"
    headers = hosted_model._headers()
    assert headers["Authorization"] == "Bearer unit-test-oidc-token"
    assert "AI_GATEWAY_API_KEY" not in headers


def test_ai_gateway_chat_request_uses_oidc_and_free_open_model(monkeypatch):
    monkeypatch.setenv("VERCEL_OIDC_TOKEN", "unit-test-oidc-token")
    monkeypatch.delenv("AI_GATEWAY_API_KEY", raising=False)
    captured = {}

    class FakeResponse:
        ok = True

        def json(self):
            return {"choices": [{"message": {"content": "A sample hosted answer."}}]}

    def fake_post(url, headers, json, timeout, **kwargs):
        captured.update(url=url, headers=headers, payload=json)
        return FakeResponse()

    monkeypatch.setattr(hosted_model.requests, "post", fake_post)
    reply = hosted_model.generate_reply(
        [{"role": "user", "content": "Explain photosynthesis"}],
        "You are Zariya.",
        temperature=0.4,
    )
    assert reply == "A sample hosted answer."
    assert captured["url"] == "https://ai-gateway.vercel.sh/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer unit-test-oidc-token"
    assert captured["payload"]["model"] == "nvidia/nemotron-3.5-lightning-free"
    assert captured["payload"]["stream"] is False
    assert captured["payload"]["messages"][0]["role"] == "system"


def test_ai_gateway_stream_yields_openai_compatible_deltas(monkeypatch):
    monkeypatch.setenv("VERCEL_OIDC_TOKEN", "unit-test-oidc-token")

    class FakeStreamResponse:
        ok = True

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def iter_lines(self, decode_unicode=True):
            yield 'data: {"choices":[{"delta":{"content":"Hello"}}]}'
            yield 'data: {"choices":[{"delta":{"content":" from Zariya"}}]}'
            yield "data: [DONE]"

    monkeypatch.setattr(hosted_model.requests, "post", lambda *args, **kwargs: FakeStreamResponse())
    tokens = list(hosted_model.stream_reply(
        [{"role": "user", "content": "Say hello"}],
        "You are Zariya.",
    ))
    assert "".join(tokens) == "Hello from Zariya"


def test_gateway_friendly_rate_limit_error():
    class FakeResponse:
        status_code = 429

        def json(self):
            return {"error": {"code": "rate_limit_exceeded"}}

    message = hosted_model._friendly_http_error(FakeResponse())
    assert "shared request limit" in message


def test_chat_has_knowledge_fallback_when_gateway_token_is_missing(monkeypatch):
    monkeypatch.delenv("VERCEL_OIDC_TOKEN", raising=False)
    monkeypatch.delenv("AI_GATEWAY_API_KEY", raising=False)
    response = index.app.test_client().post(
        "/api/chat",
        json={"messages": [{"role": "user", "content": "hello"}]},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["reply"]
    assert data["usedModel"] is False
    assert data["provider"] == "knowledge"


def test_stream_endpoint_remains_available_without_gateway_token(monkeypatch):
    monkeypatch.delenv("VERCEL_OIDC_TOKEN", raising=False)
    monkeypatch.delenv("AI_GATEWAY_API_KEY", raising=False)
    response = index.app.test_client().post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": "hello"}]},
        buffered=True,
    )
    assert response.status_code == 200
    assert response.mimetype == "text/event-stream"
    assert b"data:" in response.data
    assert b'"provider": "knowledge"' in response.data


def test_chat_stream_uses_hosted_gateway_when_token_exists(monkeypatch):
    monkeypatch.setenv("VERCEL_OIDC_TOKEN", "unit-test-oidc-token")

    class FakeStreamResponse:
        ok = True

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def iter_lines(self, decode_unicode=True):
            yield 'data: {"choices":[{"delta":{"content":"A hosted"}}]}'
            yield 'data: {"choices":[{"delta":{"content":" reply."}}]}'
            yield "data: [DONE]"

    monkeypatch.setattr(hosted_model.requests, "post", lambda *args, **kwargs: FakeStreamResponse())
    response = index.app.test_client().post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": "hello"}]},
        buffered=True,
    )
    assert response.status_code == 200
    assert b"A hosted" in response.data
    assert b'"provider": "ai_gateway"' in response.data


def test_hosted_state_does_not_claim_server_persistence():
    client = index.app.test_client()
    state = client.get("/api/state")
    assert state.status_code == 200
    assert state.get_json()["storage"] == "browser"
    saved = client.post("/api/state", json={"sessions": [], "notes": [], "decks": []})
    assert saved.status_code == 409


def test_flask_seo_routes_serve_assets():
    client = index.app.test_client()
    favicon = client.get("/favicon.svg")
    robots = client.get("/robots.txt")
    sitemap = client.get("/sitemap.xml")
    manifest = client.get("/site.webmanifest")
    assert favicon.status_code == 200
    assert favicon.mimetype == "image/svg+xml"
    assert b"#ff762b" in favicon.data
    assert robots.status_code == 200
    assert b"https://zariyas.vercel.app/sitemap.xml" in robots.data
    assert sitemap.status_code == 200
    assert b"https://zariyas.vercel.app/" in sitemap.data
    assert manifest.status_code == 200
    assert b"/favicon.svg" in manifest.data


def test_static_frontend_copies_are_identical():
    assert (ROOT / "webapp" / "static" / "app.js").read_bytes() == (ROOT / "public" / "static" / "app.js").read_bytes()
    assert (ROOT / "webapp" / "static" / "style.css").read_bytes() == (ROOT / "public" / "static" / "style.css").read_bytes()


def test_frontend_uses_hosted_model_and_automatic_bilingual_direction():
    source = (ROOT / "webapp" / "static" / "app.js").read_text(encoding="utf-8")
    assert "function respondTo(session)" in source
    assert "fetch('/api/chat/stream'" in source
    assert "isPureUrdu" in source
    assert "dir','auto'" in source
    assert "localDeviceConnectBtn" not in source
    assert "OLLAMA_ORIGINS" not in source


def test_system_prompt_enforces_readable_bilingual_formatting():
    from webapp.app import SYSTEM_PROMPT

    assert "left-to-right" in SYSTEM_PROMPT
    assert "right-to-left" in SYSTEM_PROMPT
    assert "blank lines between sections" in SYSTEM_PROMPT


def test_no_anthropic_provider_is_used_for_web_chat():
    source = (ROOT / "webapp" / "app.py").read_text(encoding="utf-8")
    assert "import hosted_model" in source
    assert "import local_model" not in source
    assert "anthropic" not in source.lower()
