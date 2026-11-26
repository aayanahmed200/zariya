import os

os.environ.setdefault("VERCEL", "1")
os.environ.setdefault("FLASK_SECRET_KEY", "test-only-zariya-secret-which-is-long-enough")

import index  # noqa: E402
from webapp import security  # noqa: E402


def client():
    security.reset_rate_limits()
    return index.app.test_client()


def test_security_headers_are_set_on_pages_and_api():
    c = client()
    for path in ("/", "/api/health"):
        response = c.get(path)
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
        assert "Access-Control-Allow-Origin" not in response.headers


def test_cross_site_write_is_rejected():
    c = client()
    response = c.post("/api/feedback", json={"question": "x", "rating": "up"},
                      headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
    assert "another site" in response.get_json()["error"]


def test_same_site_write_is_allowed():
    c = client()
    response = c.post("/api/feedback", json={"question": "x", "rating": "sideways"},
                      headers={"Origin": "http://localhost"})
    assert response.status_code == 400


def test_api_errors_do_not_leak_internals():
    c = client()
    response = c.get("/api/this-route-does-not-exist")
    assert response.status_code == 404
    body = response.get_json()
    assert body["error"] == "Not found."
    text = response.get_data(as_text=True)
    for leak in ("Traceback", "site-packages", ".py", "werkzeug"):
        assert leak not in text


def test_repeated_requests_are_rate_limited():
    c = client()
    statuses = [c.post("/api/feedback", json={"question": "x", "rating": "up"}).status_code
                for _ in range(21)]
    assert statuses[0] == 200
    assert statuses[-1] == 429
    response = c.post("/api/feedback", json={"question": "x", "rating": "up"})
    assert response.headers["Retry-After"] == "60"


def test_oversized_body_is_rejected_without_a_traceback():
    c = client()
    response = c.post("/api/state", data=b"x" * (security.MAX_REQUEST_BYTES + 10),
                      headers={"Content-Type": "application/json"})
    assert response.status_code == 413
    assert "too large" in response.get_json()["error"].lower()
