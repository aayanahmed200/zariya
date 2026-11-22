import os

os.environ.setdefault("VERCEL", "1")
os.environ.setdefault("FLASK_SECRET_KEY", "test-only-zariya-secret-which-is-long-enough")

from webapp.app import _normalize_workspace_state


def test_workspace_state_accepts_and_preserves_deletion_tombstones():
    raw = {
        "sessions": [],
        "notes": [],
        "decks": [],
        "_deleted": {"notes": [{"id": "note-1", "deletedAt": 1234}]},
    }
    state, error, status = _normalize_workspace_state(raw)
    assert error is None
    assert status is None
    assert state["_deleted"] == {
        "sessions": [],
        "notes": [{"id": "note-1", "deletedAt": 1234}],
        "decks": [],
    }


def test_workspace_state_defaults_missing_tombstones_for_old_clients():
    state, error, status = _normalize_workspace_state({"sessions": [], "notes": [], "decks": []})
    assert error is None
    assert status is None
    assert state["_deleted"] == {"sessions": [], "notes": [], "decks": []}


def test_workspace_state_rejects_invalid_tombstones():
    invalid = [
        {"id": "", "deletedAt": 1234},
        {"id": "note-1", "deletedAt": True},
        {"id": "note-1", "deletedAt": float("nan")},
        {"id": "x" * 129, "deletedAt": 1234},
    ]
    for tombstone in invalid:
        state, error, status = _normalize_workspace_state({
            "sessions": [], "notes": [], "decks": [],
            "_deleted": {"notes": [tombstone]},
        })
        assert state is None
        assert error
        assert status == 400


def test_workspace_state_caps_tombstones_per_collection():
    too_many = [{"id": f"note-{index}", "deletedAt": index + 1} for index in range(10001)]
    state, error, status = _normalize_workspace_state({
        "sessions": [], "notes": [], "decks": [],
        "_deleted": {"notes": too_many},
    })
    assert state is None
    assert error == "Too many deleted notes (max 10000)."
    assert status == 413
