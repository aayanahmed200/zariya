from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from webapp.supabase_store import SupabaseUserWorkspaceStore


USER_ID = "5c5f5c75-9e2e-4ad5-a18b-0bb85fce6d6b"
STATE = {"sessions": [], "notes": [{"id": "note-1"}], "decks": []}


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


class FakeRlsClient:
    def __init__(self, query):
        self.query = query
        self.table_name = None

    def table(self, name):
        self.table_name = name
        return self.query


def test_user_workspace_reads_through_the_request_scoped_auth_client():
    query = FakeQuery([{"state": STATE}])
    client = FakeRlsClient(query)
    store = SupabaseUserWorkspaceStore()

    assert store.get_state(USER_ID, client) == STATE
    assert client.table_name == "zariya_user_workspaces"
    assert ("eq", ("user_id", USER_ID), {}) in query.calls
    assert ("limit", (1,), {}) in query.calls


def test_user_workspace_upsert_uses_the_user_uuid_as_conflict_key():
    query = FakeQuery()
    client = FakeRlsClient(query)
    store = SupabaseUserWorkspaceStore()

    store.save_state(USER_ID, STATE, client)

    assert client.table_name == "zariya_user_workspaces"
    upsert = next(call for call in query.calls if call[0] == "upsert")
    payload = upsert[1][0]
    assert payload["user_id"] == USER_ID
    assert payload["state"] == STATE
    assert payload["updated_at"]
    assert upsert[2] == {"on_conflict": "user_id"}


def test_user_workspace_rejects_invalid_uuid_before_querying():
    query = FakeQuery()
    client = FakeRlsClient(query)
    store = SupabaseUserWorkspaceStore()

    with pytest.raises(ValueError):
        store.get_state("not-a-user-id", client)
    with pytest.raises(ValueError):
        store.save_state("not-a-user-id", STATE, client)
    assert client.table_name is None
    assert query.calls == []


def test_postgres_migration_has_owner_scoped_row_level_security():
    from pathlib import Path

    migration = (
        Path(__file__).resolve().parents[1]
        / "supabase"
        / "migrations"
        / "20261126150211_create_rls_protected_authenticated_workspaces.sql"
    ).read_text(encoding="utf-8")
    assert "enable row level security" in migration.lower()
    assert "references auth.users(id) on delete cascade" in migration.lower()
    assert "revoke all on table public.zariya_user_workspaces from public, anon" in migration.lower()
    assert "grant select, insert, update on table public.zariya_user_workspaces to authenticated" in migration.lower()
    assert migration.lower().count("(select auth.uid()) = user_id") == 4
    assert "with check" in migration.lower()
    assert "to anon" not in migration.lower()

    least_privilege = (
        Path(__file__).resolve().parents[1]
        / "supabase"
        / "migrations"
        / "20261126151531_restrict_authenticated_workspace_table_grants.sql"
    ).read_text(encoding="utf-8").lower()
    assert "revoke all on table public.zariya_user_workspaces from public, anon, authenticated" in least_privilege
    assert "grant select, insert, update on table public.zariya_user_workspaces to authenticated" in least_privilege
    assert "truncate" not in least_privilege
