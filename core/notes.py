from __future__ import annotations
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).parent.parent / "data"
NOTES_FILE = DATA_DIR / "notes.json"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_all() -> list[dict]:
    if not NOTES_FILE.exists():
        return []
    try:
        with open(NOTES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_all(notes: list[dict]) -> None:
    """Writes to a temp file in the same directory, then atomically renames it
    over the real file, so a crash or kill mid-write can never leave
    notes.json truncated or corrupted (matches the pattern already used by
    core/model_downloader.py for its downloaded model file)."""
    tmp_path = NOTES_FILE.with_suffix(".json.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(notes, f, ensure_ascii=False, indent=2)
    tmp_path.replace(NOTES_FILE)


class NotesManager:

    def __init__(self):
        self._notes: list[dict] = _load_all()

    def _find(self, note_id: str) -> Optional[dict]:
        return next((n for n in self._notes if n["id"] == note_id), None)

    def create(self, title: str = "Untitled", body: str = "") -> dict:
        note = {
            "id": str(uuid.uuid4()),
            "title": title,
            "body": body,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        self._notes.append(note)
        _save_all(self._notes)
        return note

    def update(self, note_id: str, title: str, body: str) -> bool:
        note = self._find(note_id)
        if note is None:
            return False
        note["title"] = title
        note["body"] = body
        note["updated_at"] = datetime.now().isoformat()
        _save_all(self._notes)
        return True

    def delete(self, note_id: str) -> bool:
        before = len(self._notes)
        self._notes = [n for n in self._notes if n["id"] != note_id]
        if len(self._notes) < before:
            _save_all(self._notes)
            return True
        return False

    def get_all(self) -> list[dict]:
        return sorted(self._notes, key=lambda n: n.get("updated_at", ""), reverse=True)

    def get(self, note_id: str) -> Optional[dict]:
        return self._find(note_id)


_manager: Optional[NotesManager] = None


def get_notes() -> NotesManager:
    global _manager
    if _manager is None:
        _manager = NotesManager()
    return _manager
