from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from webapp import supabase_store


OWNER_ID = "a" * 64
SECRET_KEY = "sb_secret_example_key_that_is_long_enough_123456789"
PUBLISHABLE_KEY = "sb_publishable_example_key_that_is_public_123456789"


class FakeQuery:
    def __init__(self, data=None):
        self.data = data if data is not None else []
        self.calls = []

    def select(self, *args, **kwargs):
        self.calls.append(("select", args, kwargs))
        return self

    def eq(self, *args, **kwargs):
        self.calls.append(("eq", args, kwargs))
        return self

    def limit(self, *args, **kwargs):
        self.calls.append(("limit", args, kwargs))
        return self

    def upsert(self, *args, **kwargs):
        self.calls.append(("upsert", args, kwargs))
        return self

    def execute(self):
        return SimpleNamespace(data=self.data)


class FakeClient:
    def __init__(self, query):
        self.query = query
        self.table_name = None

    def table(self, name):
        self.table_name = name
        return self.query


def test_store_requires_https_and_server_secret_key():
    assert not supabase_store.SupabaseWorkspaceStore("", SECRET_KEY).configured
    assert not supabase_store.SupabaseWorkspaceStore("http://db.example", SECRET_KEY).configured
    assert supabase_store.SupabaseWorkspaceStore("https://project.supabase.co", SECRET_KEY).configured


def test_publishable_key_alone_cannot_enable_private_server_storage():
    # A publishable key is intentionally insufficient for this table because
    # the current Flask session is not a Supabase Auth JWT subject to RLS.
    assert not supabase_store.SupabaseWorkspaceStore(
        "https://project.supabase.co", PUBLISHABLE_KEY
    ).configured


def test_legacy_service_role_jwt_remains_supported():
    token = "eyJ" + ("a" * 50) + "." + ("b" * 20) + "." + ("c" * 20)
    assert supabase_store.SupabaseWorkspaceStore(
        "https://project.supabase.co", token
    ).configured


def test_get_state_uses_sdk_with_server_secret(monkeypatch):
    query = FakeQuery([{"state": {"sessions": [], "notes": [], "decks": []}}])
    client = FakeClient(query)
    created = {}

    def fake_create_client(url, key):
        created["url"] = url
        created["key"] = key
        return client

    monkeypatch.setattr(supabase_store, "create_client", fake_create_client)
    store = supabase_store.SupabaseWorkspaceStore("https://project.supabase.co", SECRET_KEY)

    result = store.get_state(OWNER_ID)

    assert result == {"sessions": [], "notes": [], "decks": []}
    assert created == {"url": "https://project.supabase.co", "key": SECRET_KEY}
    assert client.table_name == "zariya_workspaces"
    assert ("select", ("state",), {}) in query.calls
    assert ("eq", ("owner_id", OWNER_ID), {}) in query.calls
    assert ("limit", (1,), {}) in query.calls


def test_client_is_reused_between_reads_and_writes(monkeypatch):
    query = FakeQuery([{"state": {"sessions": [], "notes": [], "decks": []}}])
    client = FakeClient(query)
    created = []

    def fake_create_client(url, key):
        created.append((url, key))
        return client

    monkeypatch.setattr(supabase_store, "create_client", fake_create_client)
    store = supabase_store.SupabaseWorkspaceStore("https://project.supabase.co", SECRET_KEY)

    store.get_state(OWNER_ID)
    store.save_state(OWNER_ID, {"sessions": [], "notes": [], "decks": []})

    assert created == [("https://project.supabase.co", SECRET_KEY)]


def test_save_state_upserts_workspace_by_owner_id(monkeypatch):
    query = FakeQuery()
    client = FakeClient(query)
    monkeypatch.setattr(supabase_store, "create_client", lambda url, key: client)
    store = supabase_store.SupabaseWorkspaceStore("https://project.supabase.co", SECRET_KEY)
    state = {"sessions": [{"id": "chat-1"}], "notes": [], "decks": []}

    store.save_state(OWNER_ID, state)

    upsert = next(call for call in query.calls if call[0] == "upsert")
    payload = upsert[1][0]
    assert payload["owner_id"] == OWNER_ID
    assert payload["state"] == state
    assert payload["updated_at"]
    assert upsert[2] == {"on_conflict": "owner_id"}


def test_owner_id_validation_rejects_arbitrary_identifiers(monkeypatch):
    store = supabase_store.SupabaseWorkspaceStore("https://project.supabase.co", SECRET_KEY)
    create_client = Mock()
    monkeypatch.setattr(supabase_store, "create_client", create_client)

    with pytest.raises(ValueError):
        store.get_state("not-a-hash")

    create_client.assert_not_called()
