"""
Zariya -- offline-first, privacy-focused AI platform for Urdu and low-resource languages.

Architecture, and why it's built this way:
- All API keys (Anthropic, Google, GitHub OAuth) live server-side in environment
  variables. The browser never sees them, never stores them, and never has to
  ask the person using the app for anything -- that's configured once by whoever
  deploys it, not per visitor.
- The offline knowledge engine (kb_engine.py) has zero dependencies and zero
  network calls. It's the guaranteed fallback if no keys are configured, and it's
  what makes this genuinely offline-capable, not just "offline until the API key
  runs out."
- GitHub sign-in is real OAuth (authorization-code flow), not a public-profile
  lookup -- the client secret is exchanged server-side, exactly the way GitHub's
  own docs require, and is never exposed to the browser.
- Two generation knobs (a custom system prompt / persona, and a temperature /
  creativity value) can be sent per-request from the client and are applied to
  whichever backend (Claude or the local model) ends up answering. Both are
  optional and fall back to sane defaults, so older requests without them still
  work unchanged.
"""
import os
import secrets
import time
import json
from pathlib import Path
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, request, session, url_for, render_template, Response, stream_with_context

import kb_engine
import local_model

load_dotenv()

app = Flask(__name__)
FLASK_SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "")
SESSION_SECRET_VALUE = FLASK_SECRET_KEY.lower()
SESSION_SECRET_CONFIGURED = len(FLASK_SECRET_KEY) >= 32 and not any(
    marker in SESSION_SECRET_VALUE for marker in ("change-this", "replace-with", "your-secret", "example")
)
app.secret_key = FLASK_SECRET_KEY or secrets.token_hex(32)

# Debug mode is opt-in only (never on by default) since Flask's debugger
# exposes an interactive Python console / arbitrary code execution to anyone
# who can trigger an unhandled exception -- fine for local development,
# dangerous left on for anything reachable over a network.
DEBUG_MODE = os.environ.get("FLASK_DEBUG", "0") == "1"
HOSTED_MODE = bool(os.environ.get("VERCEL"))

# Basic session-cookie hardening: SameSite=Lax blocks the cookie from being
# sent on most cross-site requests (CSRF mitigation) without breaking normal
# top-level navigation/links; Secure is only forced when not in local debug
# mode so plain http://localhost dev still works; a bounded lifetime means a
# stale session cookie doesn't stay valid forever.
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = HOSTED_MODE or not DEBUG_MODE
app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 24 * 7  # 7 days

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
GOOGLE_CX = os.environ.get("GOOGLE_CX", "")
GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "")
VERCEL_HOST = os.environ.get("VERCEL_URL", "").strip()
DEFAULT_BASE_URL = f"https://{VERCEL_HOST}" if VERCEL_HOST else "http://localhost:5000"
APP_BASE_URL = (os.environ.get("APP_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
GITHUB_OAUTH_CONFIGURED = bool(GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET and SESSION_SECRET_CONFIGURED)

DATA_DIR = Path(__file__).parent / "server"
STORE_PATH = DATA_DIR / "store.json"

SYSTEM_PROMPT = (
    "You are Zariya, a warm, concise bilingual Urdu/English assistant built as a "
    "privacy-first, offline-first platform for Urdu and other low-resource languages. "
    "Reply in whichever language the user writes in, mixing naturally if they mix."
)

# ---------------------------------------------------------------------------
# Tiny JSON-file store for notes/flashcards/sessions (per logged-in GitHub user
# if signed in, otherwise a shared local/anonymous bucket -- this is a uni-scale
# demo, not a multi-tenant production database).
# ---------------------------------------------------------------------------
def _load_store():
    if STORE_PATH.exists():
        import json
        return json.loads(STORE_PATH.read_text(encoding="utf-8"))
    return {"users": {}}

def _save_store(store):
    """Writes to a temp file in the same directory, then atomically renames it
    over the real file, so a crash or kill mid-write can never leave
    store.json truncated or corrupted (matches the pattern already used by
    core/model_downloader.py for its downloaded model file)."""
    import json
    tmp_path = STORE_PATH.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(STORE_PATH)

def _current_user_key():
    return session.get("github_login", "anonymous")

def _user_bucket(store):
    key = _current_user_key()
    store["users"].setdefault(key, {"sessions": [], "notes": [], "decks": []})
    return store["users"][key]

# ---------------------------------------------------------------------------
# Input validation helpers -- keep malformed client input from ever crashing a
# route with an unhandled 500. A misbehaving or future frontend change should
# get a clear 400 error back, not a blank server error page.
# ---------------------------------------------------------------------------
# Basic request-size guards, consistent with the systemPrompt cap below: an
# unbounded messages array or unbounded combined content length is an easy way
# for a misbehaving client (or a deliberately abusive one) to force huge
# memory/CPU use or huge outbound payloads to Claude/Ollama on every request.
MAX_MESSAGES = 200
MAX_TOTAL_CONTENT_CHARS = 200_000

def _normalize_messages(raw):
    """Validates the 'messages' list coming from the client.
    Returns (messages, error, status) where error is None on success, or a
    short user-facing string describing what's wrong, paired with the HTTP
    status code that best fits it (400 for malformed input, 413 for a
    payload that's simply too large)."""
    if not isinstance(raw, list) or not raw:
        return None, "No messages provided", 400
    if len(raw) > MAX_MESSAGES:
        return None, f"Too many messages (max {MAX_MESSAGES})", 413
    cleaned = []
    total_chars = 0
    for m in raw:
        if not isinstance(m, dict):
            return None, "Each message must be an object with 'role' and 'content'", 400
        role = m.get("role")
        content = m.get("content")
        if role not in ("user", "assistant", "system") or not isinstance(content, str):
            return None, "Each message needs a valid 'role' (user/assistant/system) and a string 'content'", 400
        total_chars += len(content)
        if total_chars > MAX_TOTAL_CONTENT_CHARS:
            return None, f"Combined message content is too long (max {MAX_TOTAL_CONTENT_CHARS} characters)", 413
        cleaned.append({"role": role, "content": content})
    return cleaned, None, None

def _generation_params(body):
    """Optional per-request generation overrides from the client: a custom
    persona / system prompt, and a creativity (temperature) value. Both are
    optional -- a missing or invalid value just falls back to the server
    default, so older frontend code (or a stray request) keeps working
    exactly as before."""
    system_prompt = SYSTEM_PROMPT
    custom = body.get("systemPrompt")
    if isinstance(custom, str) and custom.strip():
        system_prompt = custom.strip()[:2000]  # generous cap, just to stop abuse

    temperature = None
    raw_temp = body.get("temperature")
    if isinstance(raw_temp, (int, float)) and not isinstance(raw_temp, bool):
        temperature = max(0.0, min(1.0, float(raw_temp)))

    return system_prompt, temperature

# ---------------------------------------------------------------------------
# Auth: real GitHub OAuth (authorization-code flow), client secret stays server-side
# ---------------------------------------------------------------------------
@app.route("/auth/github/login")
def github_login():
    if not GITHUB_OAUTH_CONFIGURED:
        return jsonify({"error": "GitHub OAuth isn't configured on this server yet. "
                                  "Set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET in .env."}), 400
    state = secrets.token_urlsafe(16)
    session["oauth_state"] = state
    redirect_uri = f"{APP_BASE_URL}/auth/github/callback"
    authorize_url = (
        "https://github.com/login/oauth/authorize"
        f"?client_id={GITHUB_CLIENT_ID}&redirect_uri={redirect_uri}"
        f"&scope=read:user&state={state}"
    )
    return redirect(authorize_url)

@app.route("/auth/github/callback")
def github_callback():
    if request.args.get("state") != session.get("oauth_state"):
        return jsonify({"error": "State mismatch -- possible CSRF, or your session expired. Try signing in again."}), 400
    code = request.args.get("code")
    if not code:
        return jsonify({"error": "GitHub didn't return an authorization code."}), 400

    try:
        token_res = requests.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,  # server-side only, never sent to the browser
                "code": code,
                "redirect_uri": f"{APP_BASE_URL}/auth/github/callback",
            },
            timeout=10,
        )
        token_res.raise_for_status()
        token_data = token_res.json()
    except Exception as e:
        app.logger.warning("GitHub token exchange failed: %s", e)
        return redirect("/?" + urlencode({"authError": "GitHub sign-in failed while exchanging the authorization code. Please try again."}))

    access_token = token_data.get("access_token")
    if not access_token:
        return redirect("/?" + urlencode({"authError": "GitHub sign-in failed -- no access token was returned."}))

    try:
        user_res = requests.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"},
            timeout=10,
        )
        user_res.raise_for_status()
        profile = user_res.json()
    except Exception as e:
        app.logger.warning("GitHub profile fetch failed: %s", e)
        return redirect("/?" + urlencode({"authError": "GitHub sign-in failed while fetching your profile. Please try again."}))

    session["github_login"] = profile.get("login")
    session["github_name"] = profile.get("name") or profile.get("login")
    session["github_avatar"] = profile.get("avatar_url")
    session["github_bio"] = profile.get("bio") or ""
    return redirect("/")

@app.route("/auth/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})

@app.route("/api/me")
def me():
    if session.get("github_login"):
        return jsonify({
            "signedIn": True,
            "login": session["github_login"],
            "name": session.get("github_name"),
            "avatar": session.get("github_avatar"),
            "bio": session.get("github_bio"),
            "githubConfigured": GITHUB_OAUTH_CONFIGURED,
        })
    return jsonify({"signedIn": False, "githubConfigured": GITHUB_OAUTH_CONFIGURED})

# ---------------------------------------------------------------------------
# Chat: Claude API (server-side key) -> local model -> offline knowledge engine.
# The person using the app is never asked for a key -- whoever deploys the
# server configures it once in .env.
# ---------------------------------------------------------------------------
@app.route("/api/chat", methods=["POST"])
def chat():
    body = request.get_json(silent=True) or {}
    messages, err, err_status = _normalize_messages(body.get("messages"))
    if err:
        return jsonify({"error": err}), err_status
    system_prompt, temperature = _generation_params(body)

    used_real_model = False
    reply = None

    if ANTHROPIC_API_KEY:
        try:
            claude_body = {
                "model": ANTHROPIC_MODEL,
                "max_tokens": 1000,
                "system": system_prompt,
                "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
            }
            if temperature is not None:
                claude_body["temperature"] = temperature
            res = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                },
                json=claude_body,
                timeout=30,
            )
            res.raise_for_status()
            data = res.json()
            text_block = next((b for b in data.get("content", []) if b.get("type") == "text"), None)
            reply = text_block["text"] if text_block else None
            used_real_model = reply is not None
        except Exception as e:
            app.logger.warning("Claude API call failed, falling back to offline: %s", e)

    if reply is None and local_model.is_available():
        local_reply = local_model.generate_reply(messages, system_prompt, temperature)
        if local_reply:
            reply = local_reply
            used_real_model = True

    if reply is None:
        try:
            reply = kb_engine.offline_reply(messages)
        except Exception:
            app.logger.exception("offline_reply crashed")
            reply = ("Something went wrong answering that offline. Try rephrasing your "
                      "message, or a simpler one like a math expression or a greeting.")

    if used_real_model:
        last_user = next((m for m in reversed(messages) if m["role"] == "user"), None)
        if last_user and last_user.get("content", "").strip():
            kb_engine.remember_answer(last_user["content"], reply)

    return jsonify({"reply": reply, "usedRealModel": used_real_model})

def _sse(data):
    return f"data: {json.dumps(data)}\n\n"

@app.route("/api/chat/stream", methods=["POST"])
def chat_stream():
    """Same fallback chain as /api/chat (Claude -> local model -> offline
    knowledge engine), but streams the reply back as Server-Sent Events so
    the local model can show up token-by-token like a real LLM chat instead
    of the browser waiting on one big blocking response. Claude and the
    offline knowledge engine don't support token streaming here, so their
    replies are sent as a single event -- only the local model path streams
    incrementally."""
    body = request.get_json(silent=True) or {}
    messages, err, err_status = _normalize_messages(body.get("messages"))
    if err:
        return jsonify({"error": err}), err_status
    system_prompt, temperature = _generation_params(body)

    def generate():
        used_real_model = False
        full_reply = None

        if ANTHROPIC_API_KEY:
            try:
                claude_body = {
                    "model": ANTHROPIC_MODEL,
                    "max_tokens": 1000,
                    "system": system_prompt,
                    "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
                }
                if temperature is not None:
                    claude_body["temperature"] = temperature
                res = requests.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "Content-Type": "application/json",
                        "x-api-key": ANTHROPIC_API_KEY,
                        "anthropic-version": "2023-06-01",
                    },
                    json=claude_body,
                    timeout=30,
                )
                res.raise_for_status()
                data = res.json()
                text_block = next((b for b in data.get("content", []) if b.get("type") == "text"), None)
                if text_block:
                    full_reply = text_block["text"]
                    used_real_model = True
                    yield _sse({"delta": full_reply})
            except Exception as e:
                app.logger.warning("Claude API call failed, falling back to offline: %s", e)

        if full_reply is None and local_model.is_available():
            collected = []
            for token in local_model.stream_reply(messages, system_prompt, temperature):
                collected.append(token)
                yield _sse({"delta": token})
            if collected:
                full_reply = "".join(collected)
                used_real_model = True

        if full_reply is None:
            try:
                full_reply = kb_engine.offline_reply(messages)
            except Exception:
                app.logger.exception("offline_reply crashed")
                full_reply = ("Something went wrong answering that offline. Try rephrasing your "
                               "message, or a simpler one like a math expression or a greeting.")
            yield _sse({"delta": full_reply})

        if used_real_model and full_reply:
            last_user = next((m for m in reversed(messages) if m["role"] == "user"), None)
            if last_user and last_user.get("content", "").strip():
                kb_engine.remember_answer(last_user["content"], full_reply)

        yield _sse({"done": True, "usedRealModel": used_real_model})

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

@app.route("/api/feedback", methods=["POST"])
def feedback():
    body = request.get_json(silent=True) or {}
    question = body.get("question", "")
    rating = body.get("rating", "")
    if rating not in ("up", "down"):
        return jsonify({"error": "rating must be 'up' or 'down'"}), 400
    updated = kb_engine.rate_learned_answer(question, rating)
    return jsonify({"ok": True, "updated": updated})
# ---------------------------------------------------------------------------
# Web search: Google Custom Search (server-side key)
# ---------------------------------------------------------------------------
@app.route("/api/search", methods=["POST"])
def web_search():
    body = request.get_json(silent=True) or {}
    query = body.get("query", "").strip()
    if not query:
        return jsonify({"error": "No query provided"}), 400
    if len(query) > MAX_TOTAL_CONTENT_CHARS:
        return jsonify({"error": f"Search query is too long (max {MAX_TOTAL_CONTENT_CHARS} characters)"}), 413
    if not (GOOGLE_API_KEY and GOOGLE_CX):
        return jsonify({"error": "Web search isn't configured on this server. "
                                  "Set GOOGLE_API_KEY and GOOGLE_CX in .env."}), 400
    try:
        res = requests.get(
            "https://www.googleapis.com/customsearch/v1",
            params={"key": GOOGLE_API_KEY, "cx": GOOGLE_CX, "q": query},
            timeout=15,
        )
        res.raise_for_status()
        data = res.json()
        items = [
            {"title": i.get("title"), "link": i.get("link"), "snippet": i.get("snippet", "")}
            for i in data.get("items", [])[:5]
        ]
        return jsonify({"results": items})
    except requests.exceptions.HTTPError as e:
        return jsonify({"error": f"Google Search API error: {e}"}), 502
    except Exception as e:
        return jsonify({"error": f"Web search failed: {e}"}), 502

# ---------------------------------------------------------------------------
# Notes / Flashcards / Sessions -- simple per-user JSON storage
# ---------------------------------------------------------------------------
@app.route("/api/state", methods=["GET"])
def get_state():
    # Vercel Functions do not provide a durable writable project filesystem.
    # Hosted chat, notes and flashcards are stored in the visitor's browser.
    if HOSTED_MODE:
        return jsonify({"sessions": [], "notes": [], "decks": [], "storage": "browser"})
    store = _load_store()
    key = _current_user_key()
    is_new_user = key not in store["users"]
    bucket = _user_bucket(store)
    if is_new_user:
        _save_store(store)
    return jsonify(bucket)

@app.route("/api/state", methods=["POST"])
def save_state():
    if HOSTED_MODE:
        return jsonify({"ok": False, "error": "Hosted mode uses browser-local storage."}), 409
    body = request.get_json(silent=True) or {}
    store = _load_store()
    key = _current_user_key()
    store["users"][key] = {
        "sessions": body.get("sessions", []),
        "notes": body.get("notes", []),
        "decks": body.get("decks", []),
    }
    _save_store(store)
    return jsonify({"ok": True})

@app.route("/api/tools/<name>", methods=["POST"])
def run_tool(name):
    body = request.get_json(silent=True) or {}
    raw_messages = body.get("messages", [])
    messages, err, err_status = _normalize_messages(raw_messages) if raw_messages else ([], None, None)
    if err:
        return jsonify({"error": err}), err_status
    if name == "summarize":
        return jsonify({"result": kb_engine.summarize_messages(messages)})
    if name == "keypoints":
        return jsonify({"result": kb_engine.key_points(messages)})
    if name == "translate":
        last_user = next((m for m in reversed(messages) if m["role"] == "user"), None)
        if not last_user:
            return jsonify({"result": ""})
        return jsonify({"result": kb_engine.translate_words(last_user["content"])})
    if name == "flashcards":
        return jsonify({"cards": kb_engine.flashcards_from_messages(messages)})
    return jsonify({"error": f"Unknown tool '{name}'"}), 404

@app.route("/api/kb-stats")
def kb_stats():
    return jsonify(kb_engine.knowledge_base_stats())

@app.route("/api/config")
def config():
    """Expose provider availability, never credentials or secret values."""
    return jsonify({
        "hostedMode": HOSTED_MODE,
        "claudeConfigured": bool(ANTHROPIC_API_KEY),
        "searchConfigured": bool(GOOGLE_API_KEY and GOOGLE_CX),
        "githubConfigured": GITHUB_OAUTH_CONFIGURED,
        "localModelAvailable": False if HOSTED_MODE else local_model.is_available(),
        "localModelStatus": "Disabled on Vercel serverless" if HOSTED_MODE else local_model.load_status(),
        "localModelProgress": {"completed": 0, "total": 0} if HOSTED_MODE else local_model.load_progress(),
        "localModelName": local_model.current_model(),
    })

@app.route("/api/health")
def health():
    return jsonify({
        "ok": True,
        "service": "zariya",
        "mode": "hosted" if HOSTED_MODE else "local",
        "knowledgeEntries": len(kb_engine.KB),
    })

@app.route("/api/local-model/retry", methods=["POST"])
def local_model_retry():
    """Manually wakes up the background model-download loop instead of waiting
    out its backoff delay -- surfaced as a "Retry download" button in Settings
    for when a pull has failed and the automatic wait would otherwise take up
    to a minute."""
    return jsonify(local_model.retry_now())

@app.route("/api/local-model/models")
def local_model_models():
    """Lists every model Ollama already has pulled on this machine, plus which
    one is currently active, so Settings can offer a model switcher without
    ever needing to touch .env."""
    return jsonify({"models": local_model.list_models(), "active": local_model.current_model()})

@app.route("/api/local-model/select", methods=["POST"])
def local_model_select():
    """Switches the active local model at runtime. If the requested model
    isn't pulled yet, this starts a background download exactly like the
    first-run setup does, and the frontend polls /api/config for progress."""
    body = request.get_json(silent=True) or {}
    name = body.get("model", "")
    if not isinstance(name, str):
        return jsonify({"ok": False, "error": "model must be a string"}), 400
    result = local_model.set_active_model(name)
    return jsonify(result)

@app.route("/")
def index():
    return render_template("index.html")

if __name__ == "__main__":
    DATA_DIR.mkdir(exist_ok=True)
    app.run(debug=DEBUG_MODE, port=int(os.environ.get("PORT", 5000)))
