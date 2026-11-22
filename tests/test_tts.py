"""Tests for core/tts.py -- graceful degradation and markdown stripping."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import core.tts as tts


def test_graceful_degradation_when_pyttsx3_unavailable():
    # This sandbox has no audio device / pyttsx3 install -- speak() etc.
    # must no-op safely rather than raise.
    engine = tts.TTSEngine()
    assert engine.speak("hello") is False
    assert engine.get_voices() == []
    engine.stop()       # must not raise even though unavailable
    engine.set_rate(500)  # must not raise even though unavailable


def test_strip_markdown_bold_and_italic():
    assert tts.TTSEngine._strip_markdown("**bold** and *italic*") == "bold and italic"


def test_strip_markdown_headings():
    assert tts.TTSEngine._strip_markdown("# Heading\n\nSome text") == "Heading\n\nSome text"


def test_strip_markdown_inline_code():
    assert tts.TTSEngine._strip_markdown("Check this `code` out") == "Check this  out"


def test_strip_markdown_links():
    assert tts.TTSEngine._strip_markdown("[link text](http://example.com)") == "link text"


def test_strip_markdown_bullets():
    assert tts.TTSEngine._strip_markdown("- bullet one\n- bullet two") == "bullet one\nbullet two"


def test_strip_markdown_images_are_removed_entirely():
    # Regression test: images used to leave a stray "!" because the link-stripping
    # regex ran first and consumed ![alt](url) as if it were a link, matching only
    # the [alt](url) portion and stranding the leading "!". Images must be stripped
    # to nothing, not "!alt".
    assert tts.TTSEngine._strip_markdown("![alt](img.png)") == ""


def test_strip_markdown_mixed_image_and_link_in_one_string():
    text = "Look: ![a graph](chart.png) shows growth, see [docs](http://x.com) too"
    assert tts.TTSEngine._strip_markdown(text) == "Look:  shows growth, see docs too"
