"""Chat page: message history, streaming responses, and quick actions."""
import streamlit as st

from app.components import _safe, render_bubble
from core.summarizer import summarize_conversation, extract_key_points, generate_title
from core.flashcards import generate_flashcards_from_chat


def render_chat(engine, memory, tts):
    model_info  = engine.get_model_info()
    ready       = model_info["status"] == "loaded"
    dot_class   = "on" if ready else "off"
    dot_label   = model_info.get("name", "No model") if ready else "Model missing"

    st.markdown(f"""
    <div class="page-header">
      <div class="page-logo">Z</div>
      <div>
        <div class="page-title">Zariya</div>
        <div class="page-sub">ذریعہ &nbsp;·&nbsp; Urdu & English &nbsp;·&nbsp; Offline</div>
      </div>
      <div class="status-pill">
        <span class="dot {dot_class}"></span>
        {_safe(dot_label)}
      </div>
    </div>
    """, unsafe_allow_html=True)

    tc1, tc2, tc3, tc4, tc5 = st.columns([2, 2, 2, 2, 4])
    with tc1:
        if st.button("Summarize", use_container_width=True):
            st.session_state.pending_input = "__SUMMARIZE__"
    with tc2:
        if st.button("Key Points", use_container_width=True):
            st.session_state.pending_input = "__KEYPOINTS__"
    with tc3:
        if st.button("Flashcards", use_container_width=True):
            st.session_state.pending_input = "__FLASHCARDS__"
    with tc4:
        if st.button("Auto-Title", use_container_width=True):
            st.session_state.pending_input = "__AUTOTITLE__"

    st.markdown("<div style='height:.5rem'></div>", unsafe_allow_html=True)

    session     = next((s for s in memory.get_sessions() if s["session_id"] == st.session_state.session_id), None)
    raw_msgs    = session.get("messages", []) if session else []
    messages    = [{"role": m["role"], "content": m["content"]} for m in raw_msgs]

    if not messages:
        st.markdown("""
        <div class="empty">
          <div class="empty-title">Assalam-o-Alaikum</div>
          <div class="empty-sub">Ask anything in Urdu or English.</div>
          <div class="empty-urdu">کچھ بھی پوچھیں</div>
        </div>
        """, unsafe_allow_html=True)

        suggestions = [
            ("اردو میں کہانی لکھو", True),
            ("Explain machine learning", False),
            ("Python mein loop kaise likhte hain?", False),
            ("پاکستان کی تاریخ", True),
            ("Write a professional email", False),
            ("مجھے ریاضی سکھاؤ", True),
            ("What is quantum computing?", False),
            ("Translate: Good morning", False),
        ]
        cols = st.columns(4)
        for i, (sug, is_urdu) in enumerate(suggestions):
            with cols[i % 4]:
                if st.button(sug, key=f"sug_{i}", use_container_width=True):
                    st.session_state.pending_input = sug
                    st.rerun()

    else:
        show_ts = st.session_state.show_timestamps
        for i, raw_msg in enumerate(raw_msgs):
            role    = raw_msg["role"]
            content = raw_msg["content"]
            ts      = raw_msg.get("timestamp", "") if show_ts else ""
            render_bubble(content, role, ts)

        last_bot = next((m for m in reversed(raw_msgs) if m["role"] == "assistant"), None)
        if last_bot:
            b1, b2, b3, b4, _ = st.columns([1.5, 1.5, 1.5, 1.5, 5])
            with b1:
                show_copy = st.button("Copy", key="copy_last")
            with b2:
                if st.button("Regenerate", key="regen_last"):
                    memory.remove_last_message(st.session_state.session_id, role="assistant")
                    st.session_state.regen_trigger = True
                    st.rerun()
            with b3:
                if tts.available:
                    if st.button("Read aloud", key="tts_last"):
                        tts.speak(last_bot["content"])
            with b4:
                if st.button("Auto-title", key="pin_sess"):
                    st.session_state.pending_input = "__AUTOTITLE__"
                    st.rerun()
            if show_copy:
                st.code(last_bot["content"], language=None, wrap_lines=True)

    if st.session_state.get("regen_trigger"):
        st.session_state.regen_trigger = False
        messages = memory.get_messages(st.session_state.session_id)
        if ready and messages:
            with st.chat_message("assistant", avatar="assistant"):
                placeholder = st.empty()
                full = ""
                for tok in engine.stream_with_settings(messages,
                        max_tokens=st.session_state.max_tokens,
                        temperature=st.session_state.temperature):
                    full += tok
                    placeholder.markdown(full + "▌")
                placeholder.markdown(full)
                memory.add_message(st.session_state.session_id, "assistant", full)
                if tts.available and st.session_state.tts_enabled:
                    tts.speak(full)
            st.rerun()

    user_input = st.chat_input("Ask anything in Urdu or English...")

    if st.session_state.pending_input:
        user_input = st.session_state.pending_input
        st.session_state.pending_input = ""

    if user_input:
        if user_input == "__SUMMARIZE__":
            msgs = memory.get_messages(st.session_state.session_id)
            if msgs and ready:
                with st.spinner("Summarizing..."):
                    summary = summarize_conversation(msgs, engine)
                memory.add_message(st.session_state.session_id, "assistant",
                    f"**Conversation Summary**\n\n{summary}")
                st.rerun()
            else:
                st.info("Start a conversation first, or check model status.")

        elif user_input == "__KEYPOINTS__":
            msgs = memory.get_messages(st.session_state.session_id)
            if msgs and ready:
                with st.spinner("Extracting key points..."):
                    kp = extract_key_points(msgs, engine)
                memory.add_message(st.session_state.session_id, "assistant",
                    f"**Key Points**\n\n{kp}")
                st.rerun()
            else:
                st.info("Start a conversation first, or check model status.")

        elif user_input == "__FLASHCARDS__":
            msgs = memory.get_messages(st.session_state.session_id)
            if msgs and ready:
                with st.spinner("Generating flashcards..."):
                    cards = generate_flashcards_from_chat(msgs, engine)
                if cards:
                    st.session_state.fc_cards   = cards
                    st.session_state.fc_flipped = set()
                    st.session_state.fc_known   = set()
                    st.session_state.page       = "flashcards"
                    st.rerun()
                else:
                    st.warning("Couldn't generate flashcards. Try asking about a specific topic first.")
            else:
                st.info("Start a conversation first, or check model status.")

        elif user_input == "__AUTOTITLE__":
            msgs = memory.get_messages(st.session_state.session_id)
            if msgs and ready:
                with st.spinner("Generating title..."):
                    new_title = generate_title(msgs, engine)
                memory.rename_session(st.session_state.session_id, new_title)
                st.success(f'Renamed to: "{new_title}"')
                st.rerun()

        else:
            memory.add_message(st.session_state.session_id, "user", user_input.strip())
            render_bubble(user_input.strip(), "user")

            msgs = memory.get_messages(st.session_state.session_id)

            if ready:
                with st.chat_message("assistant", avatar="assistant"):
                    placeholder = st.empty()
                    placeholder.markdown(
                        '<div class="bubble bot thinking"><span></span><span></span><span></span></div>',
                        unsafe_allow_html=True,
                    )
                    full = ""
                    for tok in engine.stream_with_settings(
                        msgs,
                        max_tokens=st.session_state.max_tokens,
                        temperature=st.session_state.temperature,
                    ):
                        full += tok
                        placeholder.markdown(full + "▌")
                    placeholder.markdown(full)
                memory.add_message(st.session_state.session_id, "assistant", full)
                if tts.available and st.session_state.tts_enabled:
                    tts.speak(full)
            else:
                err = ("**No model loaded.** Go to Settings for setup instructions.")
                render_bubble(err, "assistant")
                memory.add_message(st.session_state.session_id, "assistant", err)
            st.rerun()

