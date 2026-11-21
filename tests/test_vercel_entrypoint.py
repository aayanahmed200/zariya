import json
import os
from pathlib import Path

os.environ["VERCEL"] = "1"
os.environ.setdefault("FLASK_SECRET_KEY", "test-only-zariya-secret-which-is-long-enough")

import index  # noqa: E402
from webapp import local_model  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def test_homepage_renders_workspace_and_seo():
    response = index.app.test_client().get("/")
    assert response.status_code == 200
    body = response.data
    assert b"Zariya" in body
    assert b"/static/app.js" in body
    assert b"Ollama models" in body
    assert b"newDeckDialog" in body
    assert b'rel="canonical"' in body
    assert b"https://zariyas.vercel.app/" in body
    assert b"localDeviceConnectBtn" in body
    assert b"twitter:card\" content=\"summary_large_image" in body
    assert b"favicon.svg?v=20261121-4" in body
    assert b'application/ld+json' in body
    assert b"Urdu" in body
    assert b"Flashcards" in body


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

def test_health_endpoint_reports_hosted_mode():
    response = index.app.test_client().get("/api/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert data["mode"] == "hosted"
    assert data["knowledgeEntries"] > 0


def test_hosted_config_reports_ollama_without_exposing_credentials(monkeypatch):
    monkeypatch.setattr(local_model, "OLLAMA_API_KEY", "")
    response = index.app.test_client().get("/api/config")
    assert response.status_code == 200
    data = response.get_json()
    assert data["hostedMode"] is True
    assert data["ollamaMode"] == "cloud"
    assert data["ollamaConfigured"] is False
    assert data["ollamaAvailable"] is False
    assert "ollamaApiKey" not in data
    assert "unit-test-ollama-key" not in json.dumps(data)
    assert "claudeConfigured" not in data


def test_ollama_cloud_probe_does_not_call_local_model_inventory(monkeypatch):
    monkeypatch.setattr(local_model, "HOSTED_MODE", True)
    monkeypatch.setattr(local_model, "_MODE", "cloud")
    monkeypatch.setattr(local_model, "OLLAMA_API_KEY", "unit-test-ollama-key")

    def unexpected_request(*args, **kwargs):
        raise AssertionError("Ollama Cloud health check must not call /api/tags")

    monkeypatch.setattr(local_model.requests, "get", unexpected_request)
    available, status = local_model._probe(force=True)
    assert available is True
    assert "verified on first message" in status


def test_ollama_cloud_request_uses_server_side_bearer_key(monkeypatch):
    monkeypatch.setattr(local_model, "OLLAMA_API_KEY", "unit-test-ollama-key")
    monkeypatch.setattr(local_model, "OLLAMA_BASE_URL", "https://ollama.com")
    monkeypatch.setattr(local_model, "_MODE", "cloud")
    monkeypatch.setattr(local_model, "_probe", lambda force=False: (True, "key configured"))
    captured = {}

    class FakeResponse:
        ok = True

        def json(self):
            return {"message": {"content": "A sample answer from Ollama."}}

    def fake_post(url, headers, json, timeout, **kwargs):
        captured.update(url=url, headers=headers, payload=json)
        return FakeResponse()

    monkeypatch.setattr(local_model.requests, "post", fake_post)
    reply = local_model.generate_reply(
        [{"role": "user", "content": "Explain photosynthesis"}],
        "You are Zariya.",
        temperature=0.4,
        model="gemma4:31b",
    )

    assert reply == "A sample answer from Ollama."
    assert captured["url"] == "https://ollama.com/api/chat"
    assert captured["headers"]["Authorization"] == "Bearer unit-test-ollama-key"
    assert captured["payload"]["model"] == "gemma4:31b"
    assert captured["payload"]["stream"] is False
    assert captured["payload"]["messages"][0]["role"] == "system"


def test_ollama_stream_yields_tokens(monkeypatch):
    monkeypatch.setattr(local_model, "OLLAMA_API_KEY", "unit-test-ollama-key")
    monkeypatch.setattr(local_model, "_probe", lambda force=False: (True, "connected"))

    class FakeStreamResponse:
        ok = True

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def iter_lines(self):
            yield b'{"message":{"content":"Hello"},"done":false}'
            yield b'{"message":{"content":" from Ollama"},"done":false}'
            yield b'{"done":true}'

    def fake_post(*args, **kwargs):
        return FakeStreamResponse()

    monkeypatch.setattr(local_model.requests, "post", fake_post)
    tokens = list(local_model.stream_reply(
        [{"role": "user", "content": "Say hello"}],
        "You are Zariya.",
        model="gemma4:31b",
    ))
    assert "".join(tokens) == "Hello from Ollama"


def test_hosted_state_does_not_claim_server_persistence():
    client = index.app.test_client()
    state = client.get("/api/state")
    assert state.status_code == 200
    assert state.get_json()["storage"] == "browser"
    saved = client.post("/api/state", json={"sessions": [], "notes": [], "decks": []})
    assert saved.status_code == 409


def test_chat_has_knowledge_fallback_without_ollama_key(monkeypatch):
    monkeypatch.setattr(local_model, "OLLAMA_API_KEY", "")
    client = index.app.test_client()
    response = client.post("/api/chat", json={"messages": [{"role": "user", "content": "hello"}]})
    assert response.status_code == 200
    data = response.get_json()
    assert data["reply"]
    assert data["usedModel"] is False
    assert data["provider"] == "knowledge"


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


def test_no_paid_local_ollama_flow_is_present_in_frontend():
    source = (ROOT / "webapp" / "static" / "app.js").read_text(encoding="utf-8")
    assert "function connectLocalDevice()" in source
    assert "function streamLocalOllama(" in source
    assert "LOCAL_OLLAMA_BASE = 'http://127.0.0.1:11434'" in source
    assert "LOCAL_OLLAMA_BASE+'/api/chat'" in source
    assert "isPureUrdu" in source
    assert "dir','auto'" in source


def test_ollama_cloud_credit_error_recommends_local_mode():
    class FakeResponse:
        status_code = 402

    message = local_model._friendly_http_error(FakeResponse())
    assert "usage credits" in message
    assert "local Ollama" in message


def test_stream_endpoint_remains_available_without_cloud_key(monkeypatch):
    monkeypatch.setattr(local_model, "OLLAMA_API_KEY", "")
    response = index.app.test_client().post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": "hello"}]},
        buffered=True,
    )
    assert response.status_code == 200
    assert response.mimetype == "text/event-stream"
    assert b"data:" in response.data
