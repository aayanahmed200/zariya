"""Zariya — a bilingual workspace with hosted open-model chat and a curated fallback.

Hosted chat uses a free open-weight model through Vercel AI Gateway. Vercel
OIDC authenticates the server-to-server request; no browser API key or local
model installation is required. If hosted inference is unavailable, selected
requests fall back to the bundled rule-based knowledge engine.
"""
import base64
import hashlib
import binascii
import io
import math
import os
import secrets
import time
import wave
import json
from pathlib import Path
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, request, session, url_for, render_template, Response, stream_with_context, send_from_directory

import kb_engine
import hosted_model
import supabase_store
import auth_sessions
import security

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
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 24 * 7  # 7 days

# Request size ceiling, security headers, same-origin CORS policy and sanitised
# error responses are installed in one place (see webapp/security.py).
security.install(app)

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
GOOGLE_CX = os.environ.get("GOOGLE_CX", "")
GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "")
VERCEL_HOST = os.environ.get("VERCEL_URL", "").strip()
DEFAULT_BASE_URL = f"https://{VERCEL_HOST}" if VERCEL_HOST else "http://localhost:5000"
APP_BASE_URL = (os.environ.get("APP_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
GITHUB_OAUTH_CONFIGURED = bool(GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET and SESSION_SECRET_CONFIGURED)

# Supabase credentials are server-only. Prefer the new sb_secret_* key; the
# legacy service-role JWT remains supported for existing projects.
SUPABASE_STORE = supabase_store.SupabaseWorkspaceStore(
    os.environ.get("SUPABASE_URL", ""),
    os.environ.get("SUPABASE_SECRET_KEY", "") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""),
)
SUPABASE_USER_WORKSPACE_STORE = supabase_store.SupabaseUserWorkspaceStore()
SUPABASE_AUTH_CONFIGURED = auth_sessions.configured()
MAX_WORKSPACE_STATE_BYTES = 2 * 1024 * 1024

DATA_DIR = Path(__file__).parent / "server"
PUBLIC_DIR = Path(__file__).resolve().parents[1] / "public"
STORE_PATH = DATA_DIR / "store.json"

SYSTEM_PROMPT = (
    "You are Zariya's Custom Zariya Model, a clear, capable bilingual assistant for Urdu and English. "
    "If asked which model you are, reply exactly: I'm the Custom Zariya Model from Zariya. "
    "Do not claim that Zariya independently trained the underlying base model. If asked how it is supplied, explain that it is Zariya's hosted assistant. "
    "Reply in the language the user uses. If the user writes in English, reply in "
    "natural, correctly written English. If the user writes in Urdu, reply in Urdu "
    "script. If they mix languages, mirror that mix naturally. Keep every English "
    "paragraph, heading, list and table left-to-right. Keep Urdu-only blocks right-to-left. "
    "Format answers for easy reading: use a short direct opening, descriptive Markdown "
    "headings when the answer is long, blank lines between sections, concise bullet or "
    "numbered lists for steps, and tables only when they genuinely clarify comparisons. "
    "Avoid huge unbroken paragraphs, excessive headings, decorative symbols, fake citations, "
    "and repetitive introductions. Use fenced code blocks for code. Be accurate, explain "
    "uncertainty, and never claim a lookup or action you did not perform."
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


def _workspace_owner_id():
    """Return a stable, pseudonymous workspace key for Supabase rows."""
    login = session.get("github_login")
    if isinstance(login, str) and login.strip():
        subject = "github:" + login.strip().casefold()
    else:
        visitor_id = session.get("zariya_visitor_id")
        if not isinstance(visitor_id, str) or len(visitor_id) < 24:
            visitor_id = secrets.token_urlsafe(32)
            session["zariya_visitor_id"] = visitor_id
        subject = "anonymous:" + visitor_id
    session.permanent = True
    return hashlib.sha256(subject.encode("utf-8")).hexdigest()


def _normalize_workspace_state(raw):
    """Validate workspace arrays and enforce an API payload-size ceiling."""
    if not isinstance(raw, dict):
        return None, "Workspace data must be an object.", 400
    limits = {"sessions": 500, "notes": 1000, "decks": 500}
    state = {}
    for field, limit in limits.items():
        items = raw.get(field, [])
        if not isinstance(items, list):
            return None, f"{field} must be a list.", 400
        if len(items) > limit:
            return None, f"Too many {field} items (max {limit}).", 413
        if any(not isinstance(item, dict) for item in items):
            return None, f"Every {field} item must be an object.", 400
        state[field] = items
    raw_deleted = raw.get("_deleted", {})
    if not isinstance(raw_deleted, dict):
        return None, "_deleted must be an object.", 400
    deleted_state = {}
    for field in limits:
        items = raw_deleted.get(field, [])
        if not isinstance(items, list):
            return None, f"Deleted {field} must be a list.", 400
        if len(items) > 10000:
            return None, f"Too many deleted {field} (max 10000).", 413
        unique = {}
        for item in items:
            if not isinstance(item, dict):
                return None, f"Every deleted {field} item must be an object.", 400
            item_id, deleted_at = item.get("id"), item.get("deletedAt")
            if (not isinstance(item_id, str) or not item_id.strip() or len(item_id)>128
                or isinstance(deleted_at, bool) or not isinstance(deleted_at, (int,float))
                or not math.isfinite(deleted_at) or deleted_at<=0):
                return None, f"Invalid deleted {field} item.", 400
            previous = unique.get(item_id)
            if previous is None or deleted_at > previous["deletedAt"]:
                unique[item_id] = {"id":item_id,"deletedAt":deleted_at}
        deleted_state[field] = sorted(unique.values(), key=lambda x:x["deletedAt"], reverse=True)
    state["_deleted"] = deleted_state

    size = len(json.dumps(state, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    if size > MAX_WORKSPACE_STATE_BYTES:
        return None, "Workspace data is too large to sync. Export a backup and reduce its size.", 413
    return state, None, None

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
# memory/CPU use or excessive outbound payloads to the hosted AI Gateway.
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
        system_prompt += "\n\nAdditional response preferences from the user:\n" + custom.strip()[:1200]

    temperature = None
    raw_temp = body.get("temperature")
    if isinstance(raw_temp, (int, float)) and not isinstance(raw_temp, bool):
        temperature = max(0.0, min(1.0, float(raw_temp)))

    return system_prompt, temperature

# ---------------------------------------------------------------------------
# Auth: real GitHub OAuth (authorization-code flow), client secret stays server-side
# ---------------------------------------------------------------------------
@app.route("/auth/github/login")
@security.rate_limit("github_login", 10, 60)
def github_login():
    if not GITHUB_OAUTH_CONFIGURED:
        return redirect("/?" + urlencode({
            "authError": "GitHub sign-in is not connected yet. Open Settings → Account & storage for the one-time setup."
        }))
    state = secrets.token_urlsafe(32)
    session.permanent = True
    session["oauth_state"] = state
    redirect_uri = f"{APP_BASE_URL}/auth/github/callback"
    authorize_url = "https://github.com/login/oauth/authorize?" + urlencode({
        "client_id": GITHUB_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "scope": "read:user",
        "state": state,
    })
    return redirect(authorize_url)

@app.route("/auth/github/callback")
def github_callback():
    expected_state = session.pop("oauth_state", None)
    returned_state = request.args.get("state", "")
    if not expected_state or not secrets.compare_digest(returned_state, expected_state):
        return redirect("/?" + urlencode({
            "authError": "GitHub sign-in expired or could not be verified. Please start again from Settings."
        }))
    if request.args.get("error"):
        return redirect("/?" + urlencode({
            "authError": "GitHub sign-in was cancelled. You can try again from Settings."
        }))
    code = request.args.get("code")
    if not code:
        return redirect("/?" + urlencode({
            "authError": "GitHub did not return an authorization code. Please try again."
        }))

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

    login = profile.get("login")
    if not isinstance(login, str) or not login.strip():
        return redirect("/?" + urlencode({
            "authError": "GitHub did not return a usable account profile. Please try again."
        }))
    session.permanent = True
    session["github_login"] = login
    session["github_name"] = profile.get("name") or login
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

def _gateway_oidc_token() -> str | None:
    """Read Vercel's runtime-injected OIDC token from the incoming request."""
    return request.headers.get("x-vercel-oidc-token") or None


# ---------------------------------------------------------------------------
# Chat: Vercel AI Gateway hosted open model -> curated knowledge fallback.
# Gateway authentication is server-side Vercel OIDC; no visitor key is required.
# ---------------------------------------------------------------------------

MAX_TRANSCRIPTION_SECONDS = 60
MAX_TRANSCRIPTION_B64_CHARS = 3_400_000
MAX_TRANSCRIPTION_BYTES = 2_500_000


@app.route("/api/transcribe", methods=["POST"])
@security.require_same_origin
@security.rate_limit('transcribe', 8, 60)
def transcribe():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "A recording was not received. Please try again."}), 400
    encoded_audio = body.get("audio")
    if not isinstance(encoded_audio, str) or not encoded_audio:
        return jsonify({"error": "No microphone audio was received."}), 400
    if len(encoded_audio) > MAX_TRANSCRIPTION_B64_CHARS:
        return jsonify({"error": "That recording is too large. Keep voice notes under 60 seconds."}), 413
    language = body.get("language", "auto")
    if language not in ("auto", "en", "ur"):
        return jsonify({"error": "Choose Auto, English or Urdu before recording."}), 400

    try:
        audio_bytes = base64.b64decode(encoded_audio, validate=True)
    except (binascii.Error, ValueError):
        return jsonify({"error": "The audio data was incomplete. Please record again."}), 400
    if not audio_bytes or len(audio_bytes) > MAX_TRANSCRIPTION_BYTES:
        return jsonify({"error": "That recording is too large or empty. Please record again."}), 413

    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as wav_file:
            channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            sample_rate = wav_file.getframerate()
            frame_count = wav_file.getnframes()
            duration = frame_count / float(sample_rate or 1)
            if channels != 1 or sample_width != 2 or sample_rate != 16000:
                return jsonify({"error": "The microphone audio format was not supported. Please refresh and try again."}), 400
            if frame_count < 4000 or duration > MAX_TRANSCRIPTION_SECONDS + 1:
                return jsonify({"error": "Record between a quarter of a second and 60 seconds of speech."}), 400
    except (wave.Error, EOFError, OSError):
        return jsonify({"error": "The audio recording was not a valid WAV file. Please record again."}), 400

    try:
        result = hosted_model.transcribe_audio(
            audio_bytes,
            media_type="audio/wav",
            language=None if language == "auto" else language,
            oidc_token=_gateway_oidc_token(),
        )
    except hosted_model.GatewayError as exc:
        app.logger.info("Voice transcription failed: %s", exc)
        return jsonify({"error": str(exc)}), 503

    return jsonify({
        "text": result["text"],
        "language": result.get("language"),
        "durationInSeconds": result.get("durationInSeconds") or duration,
    })


@app.route("/api/chat", methods=["POST"])
@security.require_same_origin
@security.rate_limit('chat', 30, 60)
def chat():
    body = request.get_json(silent=True) or {}
    messages, err, err_status = _normalize_messages(body.get("messages"))
    if err:
        return jsonify({"error": err}), err_status
    system_prompt, temperature = _generation_params(body)

    try:
        reply = hosted_model.generate_reply(
            messages,
            system_prompt,
            temperature,
            oidc_token=_gateway_oidc_token(),
        )
    except hosted_model.GatewayError as exc:
        app.logger.warning("Hosted AI request failed: %s", exc)
        return jsonify({"error": str(exc), "provider": "unavailable"}), 503

    last_user = next((m for m in reversed(messages) if m["role"] == "user"), None)
    if last_user and last_user.get("content", "").strip():
        kb_engine.remember_answer(last_user["content"], reply)

    return jsonify({
        "reply": reply,
        "usedModel": True,
        "provider": "hosted",
    })


def _sse(data):
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.route("/api/chat/stream", methods=["POST"])
@security.require_same_origin
@security.rate_limit('chat_stream', 30, 60)
def chat_stream():
    """Stream hosted model output or send a clear provider error to the client."""
    body = request.get_json(silent=True) or {}
    messages, err, err_status = _normalize_messages(body.get("messages"))
    if err:
        return jsonify({"error": err}), err_status
    system_prompt, temperature = _generation_params(body)

    def generate():
        collected = []
        try:
            for part in hosted_model.stream_reply(
                messages,
                system_prompt,
                temperature,
                oidc_token=_gateway_oidc_token(),
            ):
                collected.append(part)
                yield _sse({"delta": part})
        except hosted_model.GatewayError as exc:
            app.logger.warning("Hosted AI stream failed: %s", exc)
            if collected:
                yield _sse({"reset": True})
            yield _sse({"error": str(exc), "provider": "unavailable"})
            return

        full_reply = "".join(collected).strip()
        if not full_reply:
            yield _sse({
                "error": "The free model returned an empty response. Please try again.",
                "provider": "unavailable",
            })
            return

        last_user = next((m for m in reversed(messages) if m["role"] == "user"), None)
        if last_user and last_user.get("content", "").strip():
            kb_engine.remember_answer(last_user["content"], full_reply)

        yield _sse({"done": True, "usedModel": True, "provider": "hosted"})

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/feedback", methods=["POST"])
@security.require_same_origin
@security.rate_limit('feedback', 20, 60)
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
@security.require_same_origin
@security.rate_limit('search', 20, 60)
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
    if SUPABASE_STORE.configured:
        try:
            state = SUPABASE_STORE.get_state(_workspace_owner_id())
        except Exception:
            app.logger.exception("Supabase workspace read failed")
            return jsonify({"error": "Cloud storage could not be reached. Your local browser copy is still available."}), 503
        return jsonify(state or {"sessions": [], "notes": [], "decks": []})

    # Vercel Functions do not provide a durable writable project filesystem.
    # Without Supabase, the browser remains the safe hosted fallback.
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
@security.require_same_origin
@security.rate_limit('state_save', 60, 60)
def save_state():
    body = request.get_json(silent=True)
    state, error, status = _normalize_workspace_state(body)
    if error:
        return jsonify({"error": error}), status

    if SUPABASE_STORE.configured:
        try:
            SUPABASE_STORE.save_state(_workspace_owner_id(), state)
        except Exception:
            app.logger.exception("Supabase workspace save failed")
            return jsonify({"error": "Cloud sync failed. Your browser copy has been kept; please retry."}), 503
        return jsonify({"ok": True, "storage": "supabase"})

    if HOSTED_MODE:
        return jsonify({"ok": False, "error": "Hosted mode uses browser-local storage until Supabase is configured."}), 409
    store = _load_store()
    key = _current_user_key()
    store["users"][key] = state
    _save_store(store)
    return jsonify({"ok": True, "storage": "server_file"})

def _tool_model_reply(messages, task_prompt: str):
    """Run a focused tool task through the hosted model, if it is available."""
    try:
        return hosted_model.generate_reply(
            messages,
            SYSTEM_PROMPT + "\n\n" + task_prompt,
            temperature=0.2,
            oidc_token=_gateway_oidc_token(),
        )
    except hosted_model.GatewayError as exc:
        app.logger.info("Hosted quick tool used knowledge fallback: %s", exc)
        return None


def _parse_flashcard_json(raw: str) -> list[dict]:
    """Parse and validate model-produced flashcards without trusting raw HTML."""
    candidate = raw.strip()
    if candidate.startswith("```"):
        candidate = candidate.split("\n", 1)[-1]
        if candidate.endswith("```"):
            candidate = candidate[:-3].strip()
    try:
        data = json.loads(candidate)
    except (ValueError, TypeError):
        left, right = candidate.find("{"), candidate.rfind("}")
        if left < 0 or right <= left:
            return []
        try:
            data = json.loads(candidate[left:right + 1])
        except (ValueError, TypeError):
            return []
    source_cards = data.get("cards") if isinstance(data, dict) else None
    if not isinstance(source_cards, list):
        return []
    cards = []
    for item in source_cards[:20]:
        if not isinstance(item, dict):
            continue
        front = item.get("front")
        back = item.get("back")
        if not isinstance(front, str) or not isinstance(back, str):
            continue
        front, back = front.strip(), back.strip()
        if front and back and len(front) <= 600 and len(back) <= 2400:
            cards.append({"front": front, "back": back})
    return cards


@app.route("/api/tools/<name>", methods=["POST"])
@security.require_same_origin
@security.rate_limit('tools', 30, 60)
def run_tool(name):
    body = request.get_json(silent=True) or {}
    raw_messages = body.get("messages", [])
    messages, err, err_status = _normalize_messages(raw_messages) if raw_messages else ([], None, None)
    if err:
        return jsonify({"error": err}), err_status
    if name not in ("summarize", "keypoints", "translate", "flashcards"):
        return jsonify({"error": f"Unknown tool '{name}'"}), 404
    if not messages:
        return jsonify({"error": "Add a message to the chat first."}), 400

    if name == "summarize":
        prompt = (
            "Summarise this conversation for the user. Keep the important facts, "
            "decisions and unresolved questions. Use a short title and clear bullet "
            "points where useful. Do not invent information."
        )
        result = _tool_model_reply(messages, prompt)
        if result is None:
            result = kb_engine.summarize_messages(messages)
        return jsonify({"result": result})

    if name == "keypoints":
        prompt = (
            "Extract the main points from this conversation. Return a concise, "
            "well-organised bullet list in the language used by the user. Keep "
            "specific names, dates and quantities accurate; do not invent facts."
        )
        result = _tool_model_reply(messages, prompt)
        if result is None:
            result = kb_engine.key_points(messages)
        return jsonify({"result": result})

    if name == "translate":
        last_user = next((m for m in reversed(messages) if m["role"] == "user"), None)
        if not last_user:
            return jsonify({"result": ""})
        translation_prompt = (
            "Translate the user's text into the other primary language: English to "
            "natural Urdu, or Urdu to natural English. Preserve the original meaning, "
            "names, numbers, formatting and technical terms. If the source mixes "
            "English and Urdu, translate the full message while keeping names and "
            "terms that should remain unchanged. Return only the translation."
        )
        result = _tool_model_reply(
            [{"role": "user", "content": last_user["content"]}],
            translation_prompt,
        )
        if result is None:
            result = kb_engine.translate_words(last_user["content"])
        return jsonify({"result": result})

    flashcard_prompt = (
        "Create up to 12 useful revision flashcards from this conversation. "
        "Prioritise central ideas, definitions and facts. Each card needs a clear "
        "question or term in front and a concise answer in back. Keep both in "
        "the user's language. Do not invent details. Return only valid JSON with a cards array; "
        "each card must have front and back string fields. "
        "Do not wrap it in Markdown fences or add commentary."
    )
    raw_cards = _tool_model_reply(messages, flashcard_prompt)
    cards = _parse_flashcard_json(raw_cards) if raw_cards else []
    if not cards:
        cards = kb_engine.flashcards_from_messages(messages)
    return jsonify({"cards": cards})


@app.route("/api/kb-stats")
def kb_stats():
    return jsonify(kb_engine.knowledge_base_stats())

@app.route("/api/config")
def config():
    """Expose hosted-model readiness without returning authentication details."""
    ai = hosted_model.connection_status(oidc_token=_gateway_oidc_token())
    return jsonify({
        "hostedMode": HOSTED_MODE,
        "supabaseConfigured": SUPABASE_STORE.configured,
        "storageMode": "supabase" if SUPABASE_STORE.configured else ("browser" if HOSTED_MODE else "server_file"),
        "aiConfigured": ai["configured"],
        "aiAvailable": ai["available"],
        "aiProvider": ai["provider"],
        "aiStatus": ai["status"],
        "aiModel": ai["model"],
        "searchConfigured": bool(GOOGLE_API_KEY and GOOGLE_CX),
        "githubConfigured": GITHUB_OAUTH_CONFIGURED,
    })


@app.route("/api/health")
def health():
    ai = hosted_model.connection_status(oidc_token=_gateway_oidc_token())
    return jsonify({
        "ok": True,
        "service": "zariya",
        "mode": "hosted" if HOSTED_MODE else "local",
        "storageMode": "supabase" if SUPABASE_STORE.configured else ("browser" if HOSTED_MODE else "server_file"),
        "aiConfigured": ai["configured"],
        "aiProvider": ai["provider"],
        "knowledgeEntries": len(kb_engine.KB),
    })


# SEO assets are served by Vercel's public directory in production. These
# equivalent Flask routes also make local development and tests behave the same.
@app.route("/favicon.svg")
def favicon():
    return send_from_directory(PUBLIC_DIR, "favicon.svg", mimetype="image/svg+xml", max_age=3600)


@app.route("/favicon.png")
def favicon_png():
    return send_from_directory(PUBLIC_DIR, "favicon.png", mimetype="image/png", max_age=3600)

@app.route("/robots.txt")
def robots_txt():
    return send_from_directory(PUBLIC_DIR, "robots.txt", mimetype="text/plain", max_age=3600)

@app.route("/sitemap.xml")
def sitemap_xml():
    return send_from_directory(PUBLIC_DIR, "sitemap.xml", mimetype="application/xml", max_age=3600)

@app.route("/site.webmanifest")
def site_manifest():
    return send_from_directory(PUBLIC_DIR, "site.webmanifest", mimetype="application/manifest+json", max_age=3600)

@app.route("/")
def index():
    return render_template("index.html")

if __name__ == "__main__":
    DATA_DIR.mkdir(exist_ok=True)
    app.run(debug=DEBUG_MODE, port=int(os.environ.get("PORT", 5000)))
