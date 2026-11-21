import os

# Exercise the Flask app exactly as Vercel imports it, without starting any
# local Ollama model worker during the test.
os.environ["VERCEL"] = "1"
os.environ["DISABLE_LOCAL_MODEL"] = "1"
os.environ.setdefault("FLASK_SECRET_KEY", "test-only-zariya-secret-which-is-long-enough")

import index  # noqa: E402


def test_homepage_renders():
    response = index.app.test_client().get("/")
    assert response.status_code == 200
    assert b"Zariya" in response.data
    assert b"/static/app.js" in response.data


def test_health_endpoint_reports_hosted_mode():
    response = index.app.test_client().get("/api/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert data["mode"] == "hosted"
    assert data["knowledgeEntries"] > 0


def test_hosted_config_does_not_advertise_local_ollama():
    data = index.app.test_client().get("/api/config").get_json()
    assert data["hostedMode"] is True
    assert data["localModelAvailable"] is False
    assert data["githubConfigured"] is False


def test_hosted_state_does_not_claim_server_persistence():
    client = index.app.test_client()
    state = client.get("/api/state")
    assert state.status_code == 200
    assert state.get_json()["storage"] == "browser"
    saved = client.post("/api/state", json={"sessions": [], "notes": [], "decks": []})
    assert saved.status_code == 409


def test_chat_has_a_working_knowledge_fallback():
    client = index.app.test_client()
    response = client.post("/api/chat", json={"messages": [{"role": "user", "content": "hello"}]})
    assert response.status_code == 200
    data = response.get_json()
    assert data["reply"]
    assert data["usedRealModel"] is False
