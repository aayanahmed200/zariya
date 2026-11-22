from __future__ import annotations
import json
import re


def generate_flashcards(topic: str, engine, count: int = 8) -> list[dict]:
    messages = [{
        "role": "user",
        "content": (
            f"Create exactly {count} study flashcards about: {topic}\n\n"
            "Return ONLY a JSON array, no explanation. Format:\n"
            '[{"front": "Question?", "back": "Answer."}, ...]\n\n'
            "Questions should be clear, answers 1-3 sentences."
        )
    }]

    raw = engine.chat(messages)
    cards = _parse_json_cards(raw)
    if cards:
        return cards[:count]
    return _parse_fallback(raw, count)


def generate_flashcards_from_chat(messages: list[dict], engine) -> list[dict]:
    transcript = "\n".join(
        f"{'Q' if m['role'] == 'user' else 'A'}: {m['content'][:200]}"
        for m in messages[-20:]
    )
    req = [{
        "role": "user",
        "content": (
            "Based on this conversation, create 6 study flashcards covering the key concepts.\n"
            "Return ONLY a JSON array:\n"
            '[{"front": "Question?", "back": "Answer."}, ...]\n\n'
            f"CONVERSATION:\n{transcript}"
        )
    }]
    raw = engine.chat(req)
    cards = _parse_json_cards(raw)
    return cards if cards else []


def _parse_json_cards(text: str) -> list[dict]:
    match = re.search(r'\[[\s\S]*\]', text)
    if not match:
        return []
    try:
        data = json.loads(match.group())
        if isinstance(data, list):
            result = []
            for item in data:
                if isinstance(item, dict):
                    front = item.get("front") or item.get("question") or item.get("q", "")
                    back = item.get("back") or item.get("answer") or item.get("a", "")
                    if front and back:
                        result.append({"front": str(front), "back": str(back)})
            return result
    except Exception:
        pass
    return []


def _parse_fallback(text: str, count: int) -> list[dict]:
    cards = []
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    i = 0
    while i < len(lines) and len(cards) < count:
        line = lines[i]
        if line.lower().startswith(("q:", "question:", "front:")):
            front = re.sub(r'^(q:|question:|front:)\s*', '', line, flags=re.I)
            back = ""
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                if next_line.lower().startswith(("a:", "answer:", "back:")):
                    back = re.sub(r'^(a:|answer:|back:)\s*', '', next_line, flags=re.I)
                    i += 1
            if front and back:
                cards.append({"front": front, "back": back})
        i += 1
    return cards
