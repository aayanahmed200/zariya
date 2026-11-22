"""Tests for core/notes.py (NotesManager)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import core.notes as notes


def make_manager(tmp_path, monkeypatch):
    monkeypatch.setattr(notes, "DATA_DIR", tmp_path)
    monkeypatch.setattr(notes, "NOTES_FILE", tmp_path / "notes.json")
    return notes.NotesManager()


def test_create_and_get(tmp_path, monkeypatch):
    mgr = make_manager(tmp_path, monkeypatch)
    n = mgr.create("Test", "body text")
    assert mgr.get(n["id"])["title"] == "Test"
    assert mgr.get(n["id"])["body"] == "body text"


def test_update_existing_note(tmp_path, monkeypatch):
    mgr = make_manager(tmp_path, monkeypatch)
    n = mgr.create("Test", "body")
    assert mgr.update(n["id"], "Updated", "new body") is True
    updated = mgr.get(n["id"])
    assert updated["title"] == "Updated"
    assert updated["body"] == "new body"


def test_update_nonexistent_note_returns_false(tmp_path, monkeypatch):
    mgr = make_manager(tmp_path, monkeypatch)
    assert mgr.update("nonexistent-id", "x", "y") is False


def test_delete_note(tmp_path, monkeypatch):
    mgr = make_manager(tmp_path, monkeypatch)
    n = mgr.create("Test", "body")
    assert mgr.delete(n["id"]) is True
    assert mgr.get(n["id"]) is None
    assert mgr.delete(n["id"]) is False  # already gone


def test_get_all_returns_every_note(tmp_path, monkeypatch):
    mgr = make_manager(tmp_path, monkeypatch)
    mgr.create("A", "1")
    mgr.create("B", "2")
    all_notes = mgr.get_all()
    assert len(all_notes) == 2
    assert {n["title"] for n in all_notes} == {"A", "B"}
