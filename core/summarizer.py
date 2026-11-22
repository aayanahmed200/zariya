from __future__ import annotations
from typing import Optional


def summarize_conversation(messages: list[dict], engine) -> str:
    if not messages:
        return "No messages to summarize."

    transcript_lines = []
    for m in messages[-40:]:
        prefix = "User" if m["role"] == "user" else "Zariya"
        transcript_lines.append(f"{prefix}: {m['content'][:300]}")
    transcript = "\n".join(transcript_lines)

    summary_messages = [{
        "role": "user",
        "content": (
            "Summarize this conversation. Cover: main topics, key points/answers, "
            "and any action items. Be brief, use bullet points.\n\n"
            f"CONVERSATION:\n{transcript}"
        )
    }]
    return engine.chat(summary_messages)


def extract_key_points(messages: list[dict], engine) -> str:
    if not messages:
        return "No messages to analyze."

    transcript_lines = []
    for m in messages[-30:]:
        prefix = "User" if m["role"] == "user" else "Zariya"
        transcript_lines.append(f"{prefix}: {m['content'][:200]}")
    transcript = "\n".join(transcript_lines)

    req_messages = [{
        "role": "user",
        "content": (
            "Extract the key facts, definitions, and insights from this conversation. "
            "Numbered list, keep it concise.\n\n"
            f"CONVERSATION:\n{transcript}"
        )
    }]
    return engine.chat(req_messages)


def generate_title(messages: list[dict], engine) -> str:
    if not messages:
        return "Untitled conversation"

    first_few = messages[:4]
    transcript = "\n".join(
        f"{'User' if m['role'] == 'user' else 'Zariya'}: {m['content'][:150]}"
        for m in first_few
    )
    req = [{
        "role": "user",
        "content": f"Give this conversation a short title (max 6 words, no quotes):\n\n{transcript}"
    }]
    title = engine.chat(req).strip().strip('"\'').strip()
    return title[:60] if title else "Conversation"
