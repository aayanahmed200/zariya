from __future__ import annotations
from typing import Optional
import threading


class TTSEngine:

    def __init__(self):
        self._engine = None
        self._available = False
        self._lock = threading.Lock()
        self._speaking = False
        self._try_init()

    def _try_init(self):
        try:
            import pyttsx3
            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", 160)
            self._engine.setProperty("volume", 1.0)
            voices = self._engine.getProperty("voices")
            if voices:
                for v in voices:
                    if "female" in v.name.lower() or "zira" in v.name.lower():
                        self._engine.setProperty("voice", v.id)
                        break
            self._available = True
        except Exception:
            self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def speak(self, text: str) -> bool:
        if not self._available or not text.strip():
            return False
        clean = self._strip_markdown(text)

        def _run():
            with self._lock:
                self._speaking = True
                try:
                    self._engine.say(clean)
                    self._engine.runAndWait()
                except Exception:
                    pass
                finally:
                    self._speaking = False

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        return True

    def stop(self):
        if self._available and self._speaking:
            try:
                self._engine.stop()
            except Exception:
                pass

    def set_rate(self, rate: int):
        if self._available:
            self._engine.setProperty("rate", max(80, min(300, rate)))

    def set_volume(self, vol: float):
        if self._available:
            self._engine.setProperty("volume", max(0.0, min(1.0, vol)))

    def get_voices(self) -> list[dict]:
        if not self._available:
            return []
        voices = self._engine.getProperty("voices") or []
        return [{"id": v.id, "name": v.name} for v in voices]

    def set_voice(self, voice_id: str):
        if self._available:
            self._engine.setProperty("voice", voice_id)

    @staticmethod
    def _strip_markdown(text: str) -> str:
        import re
        text = re.sub(r"```[\s\S]*?```", " code block ", text)
        text = re.sub(r"`[^`]+`", "", text)
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
        text = re.sub(r"\*(.+?)\*", r"\1", text)
        text = re.sub(r"#{1,6}\s+", "", text)
        text = re.sub(r"!\[.*?\]\(.*?\)", "", text)          # images -- must run before the link regex below,
        text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)      # otherwise ![alt](url) matches the link pattern first
        text = re.sub(r"[-*]\s+", "", text)                  # and leaves a stray "!" in front of the alt text
        return text.strip()


_tts: Optional[TTSEngine] = None


def get_tts() -> TTSEngine:
    global _tts
    if _tts is None:
        _tts = TTSEngine()
    return _tts
