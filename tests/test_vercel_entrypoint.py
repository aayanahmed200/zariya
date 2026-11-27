import os
import re
from pathlib import Path
from types import SimpleNamespace

os.environ["VERCEL"] = "1"
os.environ.setdefault("FLASK_SECRET_KEY", "test-only-zariya-secret-which-is-long-enough")

import index  # noqa: E402
from webapp.app import hosted_model, kb_engine  # noqa: E402

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
    assert (ROOT / "public" / "favicon.png").is_file()
    assert (ROOT / "public" / "favicon.png").read_bytes().startswith(bytes([137,80,78,71,13,10,26,10]))
    assert (ROOT / "public" / "site.webmanifest").is_file()
    assert (ROOT / "public" / "robots.txt").is_file()
    assert (ROOT / "public" / "sitemap.xml").is_file()


def test_profile_avatar_has_nonempty_fallback_and_public_copy_matches():
    app_source = (ROOT / "webapp" / "static" / "app.js").read_text(encoding="utf-8")
    public_source = (ROOT / "public" / "static" / "app.js").read_text(encoding="utf-8")
    assert "sbAvatar.textContent='Z'" in app_source
    assert app_source == public_source


def test_health_endpoint_reports_gateway_mode():
    response = index.app.test_client().get("/api/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert data["mode"] == "hosted"
    assert data["aiProvider"] == "Kilo AI Gateway"
    assert data["knowledgeEntries"] > 0


def test_config_reports_gateway_without_exposing_credentials(monkeypatch):
    monkeypatch.delenv("VERCEL_OIDC_TOKEN", raising=False)
    monkeypatch.delenv("AI_GATEWAY_API_KEY", raising=False)
    response = index.app.test_client().get("/api/config")
    assert response.status_code == 200
    data = response.get_json()
    assert data["hostedMode"] is True
    assert data["aiProvider"] == "Kilo AI Gateway"
    assert data["aiConfigured"] is True
    assert data["aiAvailable"] is True
    assert "VERCEL_OIDC_TOKEN" not in str(data)
    assert "AI_GATEWAY_API_KEY" not in str(data)


def test_gateway_uses_vercel_oidc_without_a_provider_key(monkeypatch):
    monkeypatch.setenv("VERCEL_OIDC_TOKEN", "unit-test-oidc-token")
    monkeypatch.delenv("AI_GATEWAY_API_KEY", raising=False)
    status = hosted_model.connection_status()
    assert status["configured"] is True
    assert status["available"] is True
    assert status["model"] == "kilo-auto/free"
    headers = hosted_model._headers()
    assert headers["Authorization"] == "Bearer unit-test-oidc-token"
    assert "AI_GATEWAY_API_KEY" not in headers


def test_config_reads_vercel_runtime_oidc_request_header(monkeypatch):
    monkeypatch.delenv("VERCEL_OIDC_TOKEN", raising=False)
    monkeypatch.delenv("AI_GATEWAY_API_KEY", raising=False)
    response = index.app.test_client().get(
        "/api/config",
        headers={"x-vercel-oidc-token": "runtime-oidc-test-token"},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["aiConfigured"] is True
    assert data["aiAvailable"] is True
    assert data["aiProvider"] == "Kilo AI Gateway"
    assert "runtime-oidc-test-token" not in response.get_data(as_text=True)


def test_chat_passes_vercel_runtime_oidc_header_to_gateway(monkeypatch):
    monkeypatch.delenv("VERCEL_OIDC_TOKEN", raising=False)
    monkeypatch.delenv("AI_GATEWAY_API_KEY", raising=False)
    calls = []

    def fake_generate(messages, system_prompt, temperature=None, oidc_token=None):
        calls.append(oidc_token)
        return "A hosted answer."

    monkeypatch.setattr(hosted_model, "generate_reply", fake_generate)
    response = index.app.test_client().post(
        "/api/chat",
        headers={"x-vercel-oidc-token": "runtime-oidc-test-token"},
        json={"messages": [{"role": "user", "content": "hello"}]},
    )
    assert response.status_code == 200
    assert response.get_json()["provider"] == "hosted"
    assert calls == ["runtime-oidc-test-token"]


def test_stream_passes_vercel_runtime_oidc_header_to_gateway(monkeypatch):
    monkeypatch.delenv("VERCEL_OIDC_TOKEN", raising=False)
    monkeypatch.delenv("AI_GATEWAY_API_KEY", raising=False)
    calls = []

    def fake_stream(messages, system_prompt, temperature=None, oidc_token=None):
        calls.append(oidc_token)
        yield "A hosted stream."

    monkeypatch.setattr(hosted_model, "stream_reply", fake_stream)
    response = index.app.test_client().post(
        "/api/chat/stream",
        headers={"x-vercel-oidc-token": "runtime-oidc-test-token"},
        json={"messages": [{"role": "user", "content": "hello"}]},
        buffered=True,
    )
    assert response.status_code == 200
    assert b"A hosted stream." in response.data
    assert b'"provider": "hosted"' in response.data
    assert calls == ["runtime-oidc-test-token"]


def test_chat_request_uses_anonymous_kilo_free_model_without_a_key(monkeypatch):
    monkeypatch.delenv("VERCEL_OIDC_TOKEN", raising=False)
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
    assert captured["url"] == "https://ai-gateway.kilo.ai/api/v1/chat/completions"
    assert "Authorization" not in captured["headers"]
    assert captured["payload"]["model"] == "kilo-auto/free"
    assert captured["payload"]["stream"] is False
    assert captured["payload"]["messages"][0]["role"] == "system"


def test_hosted_stream_yields_openai_compatible_deltas(monkeypatch):
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


def test_chat_returns_real_error_when_free_models_are_unavailable(monkeypatch):
    monkeypatch.delenv("VERCEL_OIDC_TOKEN", raising=False)
    monkeypatch.delenv("AI_GATEWAY_API_KEY", raising=False)

    def fail(*args, **kwargs):
        raise hosted_model.GatewayError("The shared free-model request limit has been reached.")

    monkeypatch.setattr(hosted_model, "generate_reply", fail)
    response = index.app.test_client().post(
        "/api/chat",
        json={"messages": [{"role": "user", "content": "hello"}]},
    )
    assert response.status_code == 503
    data = response.get_json()
    assert data["provider"] == "unavailable"
    assert "shared free-model request limit" in data["error"]


def test_stream_endpoint_reports_free_model_error_without_fake_knowledge_answer(monkeypatch):
    monkeypatch.delenv("VERCEL_OIDC_TOKEN", raising=False)
    monkeypatch.delenv("AI_GATEWAY_API_KEY", raising=False)

    def fail(*args, **kwargs):
        raise hosted_model.GatewayError("The free model is busy. Try again later.")

    monkeypatch.setattr(hosted_model, "stream_reply", fail)
    response = index.app.test_client().post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": "hello"}]},
        buffered=True,
    )
    assert response.status_code == 200
    assert response.mimetype == "text/event-stream"
    assert b'"provider": "unavailable"' in response.data
    assert b'"error":' in response.data
    assert b'"provider": "knowledge"' not in response.data


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
    assert b'"provider": "hosted"' in response.data


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
    transparent_favicon = client.get("/favicon.png")
    assert favicon.status_code == 200
    assert favicon.mimetype == "image/svg+xml"
    assert b"#ff762b" in favicon.data
    assert robots.status_code == 200
    assert b"https://zariyas.vercel.app/sitemap.xml" in robots.data
    assert sitemap.status_code == 200
    assert b"https://zariyas.vercel.app/" in sitemap.data
    assert manifest.status_code == 200
    assert transparent_favicon.status_code == 200
    assert transparent_favicon.mimetype == "image/png"
    assert transparent_favicon.data.startswith(bytes([137,80,78,71,13,10,26,10]))
    assert b"/favicon.png" in manifest.data


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


def test_hosted_chat_uses_json_accept_header(monkeypatch):
    monkeypatch.setenv("VERCEL_OIDC_TOKEN", "unit-test-oidc-token")
    captured = {}

    class FakeResponse:
        ok = True
        def json(self):
            return {"choices": [{"message": {"content": "answer"}}]}

    def fake_post(url, headers, json, timeout, **kwargs):
        captured["headers"] = headers
        return FakeResponse()

    monkeypatch.setattr(hosted_model.requests, "post", fake_post)
    hosted_model.generate_reply([{"role": "user", "content": "hello"}], "You are Zariya.")
    assert captured["headers"]["Accept"] == "application/json"


def test_free_model_stream_uses_event_stream_accept_header(monkeypatch):
    monkeypatch.delenv("VERCEL_OIDC_TOKEN", raising=False)
    monkeypatch.delenv("AI_GATEWAY_API_KEY", raising=False)
    captured = {}

    class FakeResponse:
        ok = True

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def iter_lines(self, decode_unicode=True):
            yield 'data: {"choices":[{"delta":{"content":"streamed"}}]}'
            yield "data: [DONE]"

    def fake_post(url, headers, json, stream, timeout):
        captured["headers"] = headers
        captured["url"] = url
        return FakeResponse()

    monkeypatch.setattr(hosted_model.requests, "post", fake_post)
    tokens = list(hosted_model.stream_reply(
        [{"role": "user", "content": "hello"}], "You are Zariya."
    ))
    assert "".join(tokens) == "streamed"
    assert captured["headers"]["Accept"] == "text/event-stream"
    assert "Authorization" not in captured["headers"]
    assert captured["url"].startswith("https://ai-gateway.kilo.ai/")


def test_summarize_quick_tool_uses_hosted_model(monkeypatch):
    calls = []
    def fake_generate(messages, system_prompt, temperature=None, oidc_token=None):
        calls.append((messages, system_prompt, temperature))
        return "A concise summary."
    monkeypatch.setattr(hosted_model, "generate_reply", fake_generate)
    response = index.app.test_client().post(
        "/api/tools/summarize",
        json={"messages": [{"role": "user", "content": "A conversation about biology."}]},
    )
    assert response.status_code == 200
    assert response.get_json()["result"] == "A concise summary."
    assert "Summarise this conversation" in calls[0][1]


def test_translate_quick_tool_only_sends_latest_user_text(monkeypatch):
    calls = []
    def fake_generate(messages, system_prompt, temperature=None, oidc_token=None):
        calls.append(messages)
        return "السلام علیکم"
    monkeypatch.setattr(hosted_model, "generate_reply", fake_generate)
    response = index.app.test_client().post(
        "/api/tools/translate",
        json={"messages": [
            {"role": "user", "content": "Earlier text"},
            {"role": "assistant", "content": "Previous answer"},
            {"role": "user", "content": "Hello there"},
        ]},
    )
    assert response.status_code == 200
    assert response.get_json()["result"] == "السلام علیکم"
    assert calls[0] == [{"role": "user", "content": "Hello there"}]


def test_flashcard_tool_parses_and_filters_model_json(monkeypatch):
    raw = chr(96)*3 + 'json\n{"cards":[{"front":"What is a cell?","back":"The basic unit of life."},{"front":"Bad card","back":""}]}\n' + chr(96)*3
    monkeypatch.setattr(hosted_model, "generate_reply", lambda *args, **kwargs: raw)
    response = index.app.test_client().post(
        "/api/tools/flashcards",
        json={"messages": [{"role": "user", "content": "Explain cells."}]},
    )
    assert response.status_code == 200
    assert response.get_json()["cards"] == [
        {"front": "What is a cell?", "back": "The basic unit of life."}
    ]


def test_quick_tool_falls_back_when_hosted_model_fails(monkeypatch):
    def fail(*args, **kwargs):
        raise hosted_model.GatewayError("temporarily unavailable")
    monkeypatch.setattr(hosted_model, "generate_reply", fail)
    monkeypatch.setattr(kb_engine, "summarize_messages", lambda messages: "Fallback summary.")
    response = index.app.test_client().post(
        "/api/tools/summarize",
        json={"messages": [{"role": "user", "content": "hello"}]},
    )
    assert response.status_code == 200
    assert response.get_json()["result"] == "Fallback summary."


def test_voice_input_records_wav_and_offers_urdu_english_language_choice():
    html = (ROOT / "webapp" / "templates" / "index.html").read_text(encoding="utf-8")
    source = (ROOT / "webapp" / "static" / "app.js").read_text(encoding="utf-8")
    assert 'id="voiceLanguage"' in html
    assert 'dir="auto"' in html
    assert 'data-language="en"' in html
    assert 'data-language="ur"' in html
    assert "navigator.mediaDevices.getUserMedia" in source
    assert "function encodeWav(samples,sampleRate)" in source
    assert "fetch('/api/transcribe'" in source
    assert "Microphone permission was blocked" in source
    assert "Transcript ready. Review it, then press send." in source
    assert "stopVoiceRecognition();" in source
    assert "SpeechRecognitionClass" in source
    assert "function startDictation()" in source


def test_workspace_backup_and_flashcard_edit_controls_exist():
    html = (ROOT / "webapp" / "templates" / "index.html").read_text(encoding="utf-8")
    source = (ROOT / "webapp" / "static" / "app.js").read_text(encoding="utf-8")
    assert 'id="exportWorkspaceBtn"' in html
    assert 'id="importWorkspaceBtn"' in html
    assert 'id="importWorkspaceFile"' in html
    assert "zariya-workspace-backup" in source
    assert "function normaliseImportedWorkspace" in source
    assert "replace the chats, notes and flashcard decks" in source
    assert "browser could not save more data" in source
    assert "function editDeck(id)" in source
    assert 'data-action="edit"' in source
    assert "previousCards.get(row.dataset.cardId)" in source


def test_browser_sse_parser_is_loaded_and_stream_parser_uses_it():
    html = (ROOT / "webapp" / "templates" / "index.html").read_text(encoding="utf-8")
    source = (ROOT / "webapp" / "static" / "app.js").read_text(encoding="utf-8")
    parser = (ROOT / "webapp" / "static" / "sse.js").read_text(encoding="utf-8")
    assert '/static/sse.js?' in html
    assert "window.ZariyaSSE.consume" in source
    assert 'pending.indexOf("\\n\\n")' in parser
    assert "buffer.indexOf('\\\\\\\\n\\\\\\\\n')" not in source


def test_srs_migration_assigns_missing_card_ids_and_repairs_invalid_due_dates():
    source = (ROOT / "webapp" / "static" / "app.js").read_text(encoding="utf-8")
    assert "if(!c.id) c.id = uid();" in source
    assert "if(c.due === undefined || !Number.isFinite(Date.parse(c.due)))" in source


def test_workspace_controls_and_keyboard_filter_buttons_are_wired():
    html = (ROOT / "webapp" / "templates" / "index.html").read_text(encoding="utf-8")
    source = (ROOT / "webapp" / "static" / "app.js").read_text(encoding="utf-8")
    assert 'id="exportWorkspaceBtn"' in html
    assert 'id="importWorkspaceBtn"' in html
    assert 'id="storageStatus"' in html
    assert "function updateQuickToolsState()" in source
    assert "Start a chat before using this tool." in source
    assert "isQuickToolBusy=true" in source
    assert "function updateNoteActionState()" in source
    assert "aria-pressed=" in source
    assert "if(isGenerating && currentSessionId!==s.id) stopGenerating();" in source
    assert "if(isGenerating) stopGenerating();" in source


def test_flashcard_editor_preserves_existing_review_data():
    source = (ROOT / "webapp" / "static" / "app.js").read_text(encoding="utf-8")
    assert "function editDeck(id)" in source
    assert "const previousCards = new Map" in source
    assert "...(previous||{})" in source
    assert "existingDeck.cards=cards;" in source
    assert "if(!c.id) c.id = uid();" in source


def test_new_note_selects_the_new_empty_editor_instead_of_previous_note():
    source = (ROOT / "webapp" / "static" / "app.js").read_text(encoding="utf-8")
    handler = source[source.index("document.getElementById('newNoteBtn')"):source.index("document.getElementById('deleteNoteBtn').addEventListener")]
    assert "currentNoteId=null;" in handler
    assert "openNote(n.id);" in handler
    assert "activeNoteTagFilter=null;" in handler


def test_deleting_or_restoring_notes_selects_a_valid_note():
    source = (ROOT / "webapp" / "static" / "app.js").read_text(encoding="utf-8")
    delete_block = source[source.index("document.getElementById('deleteNoteBtn')"):source.index("let noteTitleSaveTimer")]
    restore_block = source[source.index("function restoreWorkspaceBackup"):source.index("document.getElementById('exportWorkspaceBtn')")]
    assert "currentNoteId = null;" in delete_block
    assert "activeNoteTagFilter = null;" in delete_block
    assert "currentNoteId=null;" in restore_block


def test_voice_settings_explain_hosted_transcription_and_privacy():
    html = (ROOT / "webapp" / "templates" / "index.html").read_text(encoding="utf-8")
    assert "English and Urdu voice transcription" in html
    assert "browser's speech engine" in html
    assert "nothing is uploaded" in html
    assert "transcribes it on the server" in html
    assert "Ollama replies" not in html
    assert "sent with your messages to Ollama" not in html
    assert "Hosted AI" in html


def test_flashcard_json_import_is_bounded_and_repairs_review_values():
    source = (ROOT / "webapp" / "static" / "app.js").read_text(encoding="utf-8")
    importer = source[source.index("function importDeckFromJson"):source.index("document.getElementById('importDeckBtn')")]
    assert "cardsSource.slice(0,30)" in importer
    assert "c.front.slice(0,600)" in importer
    assert "c.back.slice(0,2400)" in importer
    assert "Math.min(4,Math.max(1.3,ease))" in importer
    assert "Number.isFinite(Date.parse(c.due))" in importer


def test_speech_output_removes_markdown_before_reading():
    source = (ROOT / "webapp" / "static" / "app.js").read_text(encoding="utf-8")
    assert "function speechPlainText(value)" in source
    assert "Code block omitted." in source
    assert "function speak(text)" in source
    assert "new SpeechSynthesisUtterance(readable)" in source
    assert "Speech unavailable" in source


def test_local_state_loader_remains_async():
    source = (ROOT / "webapp" / "static" / "app.js").read_text(encoding="utf-8")
    assert "async function loadServerState()" in source


def test_chat_generation_state_is_isolated_per_request_and_saves_partial_once():
    source = (ROOT / "webapp" / "static" / "app.js").read_text(encoding="utf-8")
    assert "let activeGeneration = null;" in source
    assert "controller:new AbortController()" in source
    assert "signal:generation.controller.signal" in source
    assert "if(activeGeneration===generation)" in source
    assert "generation.partialSaved=true;" in source
    assert "generation.controller.abort();" in source
    assert "let currentAbort = null;" not in source
    assert "let stopped = false;" not in source


def test_chat_navigation_returns_to_chat_from_other_workspace_views():
    source = (ROOT / "webapp" / "static" / "app.js").read_text(encoding="utf-8")
    new_session = source[source.index("function newSession()"):source.index("function currentSession()")]
    session_list = source[source.index("function renderSessionList()"):source.index("document.getElementById('sessSearch').addEventListener")]
    assert "switchView('chat');" in new_session
    assert "switchView('chat');" in session_list


def test_empty_conversation_search_has_a_clear_search_action():
    source = (ROOT / "webapp" / "static" / "app.js").read_text(encoding="utf-8")
    assert "No matching chats" in source
    assert "Clear search" in source
    assert "renderSessionList();" in source


def test_notes_empty_state_prevents_unsaved_typing_and_offers_creation():
    html = (ROOT / "webapp" / "templates" / "index.html").read_text(encoding="utf-8")
    source = (ROOT / "webapp" / "static" / "app.js").read_text(encoding="utf-8")
    assert 'id="noteEmptyState"' in html
    assert 'id="noteEditorFields" hidden' in html
    assert 'id="createFirstNoteBtn"' in html
    assert "function syncNoteEditorState()" in source
    assert "document.getElementById('newNoteBtn').click();" in source


def test_flashcard_empty_state_supports_manual_deck_creation():
    source = (ROOT / "webapp" / "static" / "app.js").read_text(encoding="utf-8")
    assert "Your first deck starts here" in source
    assert "Create first deck" in source
    assert "document.getElementById('newDeckBtn').click();" in source


def test_hosted_ai_copy_has_no_leftover_ollama_instructions():
    html = (ROOT / "webapp" / "templates" / "index.html").read_text(encoding="utf-8")
    assert "Hosted AI" in html
    assert "works with Ollama" not in html
    assert "Checking Ollama" not in html


def test_workspace_toggles_and_mobile_navigation_expose_accessible_state():
    html = (ROOT / "webapp" / "templates" / "index.html").read_text(encoding="utf-8")
    source = (ROOT / "webapp" / "static" / "app.js").read_text(encoding="utf-8")
    assert 'aria-expanded="false" aria-controls="sidebar"' in html
    assert 'aria-pressed="true">Light' in html
    assert "timestampsToggle.setAttribute('aria-pressed'" in source
    assert "ttsToggle.setAttribute('aria-pressed'" in source
    assert "setAttribute('aria-expanded','true')" in source
    assert "setAttribute('aria-expanded','false')" in source


def test_note_editor_displays_automatic_save_feedback():
    html = (ROOT / "webapp" / "templates" / "index.html").read_text(encoding="utf-8")
    source = (ROOT / "webapp" / "static" / "app.js").read_text(encoding="utf-8")
    assert 'id="noteSaveStatus"' in html
    assert "function setNoteSaveStatus(message,warning=false)" in source
    assert "Unsaved changes" in source
    assert "Saved just now" in source
    assert "Could not save" in source
    assert "return saved;" in source
    assert "previousNoteId!==currentNoteId" in source
    assert "if(changed) setNoteSaveStatus('Saved on this device');" in source


def _sample_wav_bytes(seconds=1):
    import io
    import wave
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        wav_file.writeframes(b"\\x00\\x00" * int(16000 * seconds))
    return buffer.getvalue()


def test_transcription_route_validates_audio_and_uses_server_gateway(monkeypatch):
    import base64
    calls = []
    def fake_transcribe(audio_bytes, media_type="audio/wav", language=None, oidc_token=None):
        calls.append((audio_bytes, media_type, language, oidc_token))
        return {"text": "السلام علیکم hello", "language": "ur", "durationInSeconds": 1.0}
    monkeypatch.setattr(hosted_model, "transcribe_audio", fake_transcribe)
    client = index.app.test_client()
    assert client.post("/api/transcribe", json={}).status_code == 400
    audio = _sample_wav_bytes()
    response = client.post("/api/transcribe", headers={"x-vercel-oidc-token": "test-oidc"}, json={
        "audio": base64.b64encode(audio).decode("ascii"),
        "mediaType": "audio/wav",
        "language": "ur",
    })
    assert response.status_code == 200
    assert response.get_json()["text"] == "السلام علیکم hello"
    assert calls[0] == (audio, "audio/wav", "ur", "test-oidc")


def test_transcription_route_rejects_invalid_format_and_language():
    import base64
    client = index.app.test_client()
    audio = _sample_wav_bytes()
    encoded = base64.b64encode(audio).decode("ascii")
    assert client.post("/api/transcribe", json={"audio": encoded, "language": "fr"}).status_code == 400
    assert client.post("/api/transcribe", json={"audio": base64.b64encode(b"not wav").decode("ascii")}).status_code == 400


def test_gateway_transcription_uses_oidc_and_microsoft_provider_options(monkeypatch):
    captured = {}
    class FakeResponse:
        ok = True
        status_code = 200
        def json(self):
            return {"text": "Hello world", "language": "en", "durationInSeconds": 1.5}
    def fake_post(url, headers, json, timeout):
        captured.update(url=url, headers=headers, payload=json, timeout=timeout)
        return FakeResponse()
    monkeypatch.setattr(hosted_model.requests, "post", fake_post)
    result = hosted_model.transcribe_audio(b"wav-bytes", language="ur", oidc_token="oidc-token")
    assert result["text"] == "Hello world"
    assert captured["url"].endswith("/v4/ai/transcription-model")
    assert captured["headers"]["Authorization"] == "Bearer oidc-token"
    assert captured["headers"]["ai-model-id"] == "microsoft/mai-transcribe-2"
    assert captured["payload"]["providerOptions"]["azure"]["language"] == "ur"
    assert "locales" not in captured["payload"]["providerOptions"]["azure"]
    assert "transcribeStyle" not in captured["payload"]["providerOptions"]["azure"]
    assert captured["timeout"] == (8, 50)


def test_microphone_uses_recorded_wav_and_custom_accessible_language_dropdown():
    html = (ROOT / "webapp" / "templates" / "index.html").read_text(encoding="utf-8")
    source = (ROOT / "webapp" / "static" / "app.js").read_text(encoding="utf-8")
    assert 'aria-haspopup="listbox"' in html
    assert 'data-language="auto"' in html
    assert 'data-language="en"' in html
    assert 'data-language="ur"' in html
    assert "navigator.mediaDevices.getUserMedia" in source
    assert "function encodeWav(samples,sampleRate)" in source
    assert "fetch('/api/transcribe'" in source
    assert "SpeechRecognitionClass" in source
    assert "function startDictation()" in source
    capture = source[source.index("async function startVoiceRecognition()"):source.index("async function stopVoiceRecognition()")]
    assert capture.index("pendingStreamPromise=navigator.mediaDevices.getUserMedia") < capture.index("const resumePromise=recordingContext.resume()")
    assert "await Promise.all([pendingStreamPromise,resumePromise])" in capture
    assert "Transcript ready. Review it, then press send." in source


def test_urdu_uses_readable_noto_sans_arabic_and_transcription_cost_is_disclosed():
    html = (ROOT / "webapp" / "templates" / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "webapp" / "static" / "style.css").read_text(encoding="utf-8")
    assert "Noto+Sans+Arabic" in html
    assert "English and Urdu voice transcription" in html
    assert "browser's speech engine" in html
    assert "Noto Sans Arabic" in css
    assert "line-height:1.85" in css
    assert "Noto Nastaliq Urdu" not in css


def test_transparent_favicon_is_used_by_page_and_manifest():
    import json
    html = (ROOT / "webapp" / "templates" / "index.html").read_text(encoding="utf-8")
    manifest = json.loads((ROOT / "public" / "site.webmanifest").read_text(encoding="utf-8"))
    assert 'href="/favicon.svg?v=20261127-1"' in html
    assert 'href="/favicon.png?v=20261127-1"' in html
    assert manifest["icons"][0]["src"] == "/favicon.png?v=20261127-1"
    assert manifest["icons"][0]["type"] == "image/png"
    assert any(icon["type"] == "image/svg+xml" for icon in manifest["icons"])


def test_voice_state_is_initialized_before_composer_handlers():
    source = (ROOT / "webapp" / "static" / "app.js").read_text(encoding="utf-8")
    assert source.index("let voiceState = 'idle';") < source.index("function syncSendState()")
    assert source.index("let shouldListen = false;") < source.index("function syncSendState()")


def test_uploaded_favicon_is_transparent_rgba_at_128px():
    icon = (ROOT / "public" / "favicon.png").read_bytes()
    assert icon[:8] == bytes([137, 80, 78, 71, 13, 10, 26, 10])
    assert int.from_bytes(icon[16:20], "big") == 128
    assert int.from_bytes(icon[20:24], "big") == 128
    assert icon[25] == 6  # Truecolour PNG with an alpha channel.


def test_mixed_urdu_english_markdown_wraps_only_arabic_script_runs():
    source = (ROOT / "webapp" / "static" / "app.js").read_text(encoding="utf-8")
    assert "function wrapUrduRuns(value)" in source
    assert 'class="urdu-run" lang="ur" dir="rtl"' in source
    assert "text = wrapUrduRuns(text);" in source
    assert "wrapUrduRuns(escapeHtml(result.snippet || ''))" in source
    assert "wrapUrduRuns(escapeHtml(label))" in source


def test_chat_and_notepad_apply_urdu_typography_while_typing():
    html = (ROOT / "webapp" / "templates" / "index.html").read_text(encoding="utf-8")
    source = (ROOT / "webapp" / "static" / "app.js").read_text(encoding="utf-8")
    css = (ROOT / "webapp" / "static" / "style.css").read_text(encoding="utf-8")
    assert 'id="note-title-input" placeholder="Untitled note" aria-label="Note title" dir="auto"' in html
    assert 'id="note-body-input" placeholder="Start writing here…" dir="auto"' in html
    assert "function syncUrduInput(element)" in source
    assert "syncUrduInput(input);" in source
    assert "syncUrduInput(document.getElementById('note-title-input'));" in source
    assert "syncUrduInput(document.getElementById('note-body-input'));" in source
    assert "syncUrduInput(document.getElementById('note-tags-input'));" in source
    assert ".urdu-run{" in css
    assert "unicode-bidi:isolate" in css


def test_flashcards_and_quiz_render_mixed_urdu_english_without_forcing_full_rtl():
    source = (ROOT / "webapp" / "static" / "app.js").read_text(encoding="utf-8")
    assert "dir=\"auto\">'+wrapUrduRuns(escapeHtml(c.front))" in source
    assert "dir=\"auto\">'+wrapUrduRuns(escapeHtml(c.back))" in source
    assert "wrapUrduRuns(escapeHtml(opt))" in source
    assert "wrapUrduRuns(escapeHtml(q.front))" in source
    assert "isPureUrdu(opt)?' is-urdu urdu':''" in source


def test_quiz_options_lock_after_answer_and_show_accessible_feedback():
    source = (ROOT / "webapp" / "static" / "app.js").read_text(encoding="utf-8")
    assert 'id=\"quizFeedback\" role=\"status\" aria-live=\"polite\"' in source
    assert "b.disabled=true;" in source
    assert "b.setAttribute('aria-pressed',String(isChosen));" in source
    assert "Your answer, correct" in source
    assert "Your answer, incorrect" in source
    assert "quiz-feedback.correct" in (ROOT / "webapp" / "static" / "style.css").read_text(encoding="utf-8")


def test_response_style_dropdown_is_accessible_and_preserves_custom_instructions():
    html = (ROOT / "webapp" / "templates" / "index.html").read_text(encoding="utf-8")
    source = (ROOT / "webapp" / "static" / "app.js").read_text(encoding="utf-8")
    assert 'aria-haspopup="listbox"' in html
    for preset in ("balanced", "concise", "steps", "detailed"):
        assert f'data-response-style="{preset}"' in html
    assert "responseStylePresets" in source
    assert "systemPrompt:[responseStylePresets[genPrefs.responseStyle||'balanced']?.instruction,genPrefs.persona].filter(Boolean).join" in source
    assert "genPrefs.persona='';" in source
    assert "genPrefs={persona:'', temperature:0.5}" not in source
    assert "responsePresetOptions[(index+direction+responsePresetOptions.length)%responsePresetOptions.length].focus();" in source


def test_urdu_direction_updates_in_custom_instructions_and_flashcard_editor():
    html = (ROOT / "webapp" / "templates" / "index.html").read_text(encoding="utf-8")
    source = (ROOT / "webapp" / "static" / "app.js").read_text(encoding="utf-8")
    css = (ROOT / "webapp" / "static" / "style.css").read_text(encoding="utf-8")
    assert 'id="personaInput"' in html and 'id="personaInput"' in html[html.index('id="personaInput"')-20:html.index('id="personaInput"')+200]
    assert 'dir="auto"' in html[html.index('id="personaInput"')-20:html.index('id="personaInput"')+280]
    assert 'class="deck-front" maxlength="600" required placeholder="Question or term" dir="auto"' in source
    assert 'class="deck-back" maxlength="2400" required rows="2" placeholder="Answer or definition" dir="auto"' in source
    assert "frontInput.addEventListener('input',()=>syncUrduInput(frontInput));" in source
    assert "backInput.addEventListener('input',()=>syncUrduInput(backInput));" in source
    assert "#personaInput.input-urdu,.deck-front.input-urdu,.deck-back.input-urdu" in css
