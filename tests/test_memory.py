"""Tests for core/memory.py (MemoryManager)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import core.memory as memory


def make_manager(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "DATA_DIR", tmp_path)
    monkeypatch.setattr(memory, "HISTORY_FILE", tmp_path / "chat_history.json")
    return memory.MemoryManager()


def test_new_session_and_add_message(tmp_path, monkeypatch):
    mgr = make_manager(tmp_path, monkeypatch)
    sid = mgr.new_session()
    mgr.add_message(sid, "user", "Hello there, this is a test message")
    mgr.add_message(sid, "assistant", "Hi! How can I help?")
    msgs = mgr.get_messages(sid)
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"


def test_session_title_derives_from_first_user_message(tmp_path, monkeypatch):
    mgr = make_manager(tmp_path, monkeypatch)
    sid = mgr.new_session()
    mgr.add_message(sid, "user", "Hello there, this is a test message")
    sessions = mgr.get_sessions()
    assert sessions[0]["title"] == "Hello there, this is a test message"


def test_remove_last_message_role_guard(tmp_path, monkeypatch):
    mgr = make_manager(tmp_path, monkeypatch)
    sid = mgr.new_session()
    mgr.add_message(sid, "user", "hi")
    mgr.add_message(sid, "assistant", "hello")
    # last message is assistant -- refusing to remove it as "user" prevents
    # deleting the wrong message from under the caller
    assert mgr.remove_last_message(sid, role="user") is False
    assert len(mgr.get_messages(sid)) == 2
    assert mgr.remove_last_message(sid, role="assistant") is True
    assert len(mgr.get_messages(sid)) == 1


def test_search_finds_matching_content(tmp_path, monkeypatch):
    mgr = make_manager(tmp_path, monkeypatch)
    sid = mgr.new_session()
    mgr.add_message(sid, "user", "What is the capital of France?")
    mgr.add_message(sid, "assistant", "The capital of France is Paris")
    results = mgr.search("paris")
    assert len(results) == 1
    assert results[0]["session_id"] == sid


def test_delete_session(tmp_path, monkeypatch):
    mgr = make_manager(tmp_path, monkeypatch)
    sid = mgr.new_session()
    mgr.add_message(sid, "user", "hi")
    assert mgr.delete_session(sid) is True
    assert mgr.get_sessions() == []
    assert mgr.delete_session(sid) is False  # already gone


def test_rename_session(tmp_path, monkeypatch):
    mgr = make_manager(tmp_path, monkeypatch)
    sid = mgr.new_session()
    mgr.add_message(sid, "user", "hi")
    mgr.rename_session(sid, "My renamed chat")
    sessions = mgr.get_sessions()
    assert sessions[0]["title"] == "My renamed chat"
