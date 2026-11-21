import os
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
    assert data["aiProvider"] == "Vercel AI Gateway"
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
    assert response.get_json()["provider"] == "ai_gateway"
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
    assert b'"provider": "ai_gateway"' in response.data
    assert calls == ["runtime-oidc-test-token"]


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


def test_ai_gateway_chat_uses_json_accept_header(monkeypatch):
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


def test_ai_gateway_stream_uses_event_stream_accept_header(monkeypatch):
    monkeypatch.setenv("VERCEL_OIDC_TOKEN", "unit-test-oidc-token")
    captured = {}

    class FakeResponse:
        ok = True
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_value, traceback):
            return False
        def iter_lines(self, decode_unicode=True):
            yield "data: [DONE]"

    def fake_post(url, headers, json, stream, timeout):
        captured["headers"] = headers
        return FakeResponse()

    monkeypatch.setattr(hosted_model.requests, "post", fake_post)
    list(hosted_model.stream_reply([{"role": "user", "content": "hello"}], "You are Zariya."))
    assert captured["headers"]["Accept"] == "text/event-stream"


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


def test_voice_input_has_urdu_english_choice_and_permission_feedback():
    html = (ROOT / "webapp" / "templates" / "index.html").read_text(encoding="utf-8")
    source = (ROOT / "webapp" / "static" / "app.js").read_text(encoding="utf-8")
    assert 'id="voiceLanguage"' in html
    assert 'dir="auto"' in html
    assert 'value="ur-PK"' in html
    assert "recognizer.continuous = true" in source
    assert "recognizer.interimResults = true" in source
    assert "Microphone permission was blocked" in source
    assert "Voice captured. Review the transcript before sending." in source
    assert "stopVoiceRecognition();" in source


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
    assert "data-action=\\"edit\\"" in source
    assert "previousCards.get(row.dataset.cardId)" in source


def test_browser_sse_parser_is_loaded_and_stream_parser_uses_it():
    html = (ROOT / "webapp" / "templates" / "index.html").read_text(encoding="utf-8")
    source = (ROOT / "webapp" / "static" / "app.js").read_text(encoding="utf-8")
    parser = (ROOT / "webapp" / "static" / "sse.js").read_text(encoding="utf-8")
    assert '/static/sse.js?' in html
    assert "window.ZariyaSSE.consume" in source
    assert 'pending.indexOf("\\\\n\\\\n")' in parser
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
    handler = source[source.index("document.getElementById('newNoteBtn')"):source.index("document.getElementById('deleteNoteBtn')")]
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


def test_voice_settings_explain_browser_processing_and_hosted_model_wording():
    html = (ROOT / "webapp" / "templates" / "index.html").read_text(encoding="utf-8")
    assert "English and Urdu voice typing" in html
    assert "Zariya does not save voice recordings" in html
    assert "browser's speech-recognition provider" in html
    assert "Ollama replies" not in html
    assert "sent with your messages to Ollama" not in html
    assert "Hosted open-model chat" in html


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
