from unittest.mock import Mock

import pytest

from webapp import supabase_store


OWNER_ID = "a" * 64
SECRET_KEY = "sb_secret_example_key_that_is_long_enough_123456789"


def test_store_requires_https_and_server_key():
    assert not supabase_store.SupabaseWorkspaceStore("", SECRET_KEY).configured
    assert not supabase_store.SupabaseWorkspaceStore("http://db.example", SECRET_KEY).configured
    assert supabase_store.SupabaseWorkspaceStore("https://project.supabase.co", SECRET_KEY).configured


def test_get_state_uses_server_only_apikey(monkeypatch):
    response = Mock()
    response.json.return_value = [{"state": {"sessions": [], "notes": [], "decks": []}}]
    response.raise_for_status.return_value = None
    captured = {}

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return response

    monkeypatch.setattr(supabase_store.requests, "get", fake_get)
    store = supabase_store.SupabaseWorkspaceStore("https://project.supabase.co", SECRET_KEY)

    result = store.get_state(OWNER_ID)

    assert result == {"sessions": [], "notes": [], "decks": []}
    assert captured["url"] == "https://project.supabase.co/rest/v1/zariya_workspaces"
    assert captured["headers"]["apikey"] == SECRET_KEY
    assert "Authorization" not in captured["headers"]
    assert captured["params"]["owner_id"] == "eq." + OWNER_ID


def test_save_state_upserts_without_returning_workspace_data(monkeypatch):
    response = Mock()
    response.raise_for_status.return_value = None
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return response

    monkeypatch.setattr(supabase_store.requests, "post", fake_post)
    store = supabase_store.SupabaseWorkspaceStore("https://project.supabase.co", SECRET_KEY)
    state = {"sessions": [{"id": "chat-1"}], "notes": [], "decks": []}

    store.save_state(OWNER_ID, state)

    assert captured["params"] == {"on_conflict": "owner_id"}
    assert captured["json"]["owner_id"] == OWNER_ID
    assert captured["json"]["state"] == state
    assert captured["headers"]["Prefer"] == "resolution=merge-duplicates,return=minimal"


def test_owner_id_validation_rejects_arbitrary_identifiers():
    store = supabase_store.SupabaseWorkspaceStore("https://project.supabase.co", SECRET_KEY)
    with pytest.raises(ValueError):
        store.get_state("not-a-hash")
