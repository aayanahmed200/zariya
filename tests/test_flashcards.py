"""Tests for core/flashcards.py -- flashcard generation and parsing."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import core.flashcards as fc


class FakeEngine:
    def __init__(self, response):
        self.response = response

    def chat(self, messages):
        return self.response


def test_clean_json_response():
    engine = FakeEngine('[{"front": "What is 2+2?", "back": "4"}, '
                         '{"front": "Capital of France?", "back": "Paris"}]')
    cards = fc.generate_flashcards("math", engine, count=2)
    assert len(cards) == 2
    assert cards[0]["front"] == "What is 2+2?"
    assert cards[0]["back"] == "4"


def test_json_wrapped_in_prose_and_alt_key_names():
    # Models often add chatty prose around the JSON, and sometimes use
    # question/answer instead of front/back -- both need to parse.
    engine = FakeEngine(
        'Sure! Here are your flashcards:\n[{"question": "Q1?", "answer": "A1"}]\nHope that helps!'
    )
    cards = fc.generate_flashcards("topic", engine, count=1)
    assert len(cards) == 1
    assert cards[0]["front"] == "Q1?"
    assert cards[0]["back"] == "A1"


def test_fallback_to_q_and_a_format_when_json_parsing_fails():
    engine = FakeEngine(
        "Q: What is the mitochondria?\nA: The powerhouse of the cell.\n"
        "Q: What is DNA?\nA: Genetic material."
    )
    cards = fc.generate_flashcards("bio", engine, count=2)
    assert len(cards) == 2
    assert cards[0]["front"] == "What is the mitochondria?"


def test_generate_from_chat_messages():
    messages = [
        {"role": "user", "content": "Explain photosynthesis"},
        {"role": "assistant", "content": "Photosynthesis converts light to energy"},
    ]
    engine = FakeEngine('[{"front":"What converts light to energy?","back":"Photosynthesis"}]')
    cards = fc.generate_flashcards_from_chat(messages, engine)
    assert len(cards) == 1
    assert cards[0]["front"] == "What converts light to energy?"


def test_garbage_response_returns_empty_list_not_a_crash():
    engine = FakeEngine("I don't know how to make flashcards about that, sorry!")
    cards = fc.generate_flashcards("nonsense", engine, count=2)
    assert cards == []
