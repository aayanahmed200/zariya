import os
os.environ.setdefault("VERCEL","1")
os.environ.setdefault("FLASK_SECRET_KEY","test-only-zariya-secret-which-is-long-enough")
from webapp.app import _normalize_workspace_state

def test_workspace_state_preserves_valid_deletion_tombstones():
    state,error,status=_normalize_workspace_state({
        "sessions":[],"notes":[],"decks":[],
        "_deleted":{"notes":[{"id":"note-1","deletedAt":1234}]},
    })
    assert error is None and status is None
    assert state["_deleted"]=={"sessions":[],"notes":[{"id":"note-1","deletedAt":1234}],"decks":[]}

def test_workspace_state_defaults_tombstones_for_old_clients():
    state,error,status=_normalize_workspace_state({"sessions":[],"notes":[],"decks":[]})
    assert error is None and status is None
    assert state["_deleted"]=={"sessions":[],"notes":[],"decks":[]}

def test_workspace_state_rejects_invalid_tombstones():
    for item in [{"id":"","deletedAt":1},{"id":"x","deletedAt":True},{"id":"x","deletedAt":float("nan")},{"id":"x"*129,"deletedAt":1}]:
        state,error,status=_normalize_workspace_state({"sessions":[],"notes":[],"decks":[],"_deleted":{"notes":[item]}})
        assert state is None and error and status==400

def test_workspace_state_caps_tombstones():
    items=[{"id":f"note-{i}","deletedAt":i+1} for i in range(10001)]
    state,error,status=_normalize_workspace_state({"sessions":[],"notes":[],"decks":[],"_deleted":{"notes":items}})
    assert state is None and status==413
