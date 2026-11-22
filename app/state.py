"""Session state defaults, shared across all pages."""
import streamlit as st


def init_state(memory):
    defaults = {
        "page": "chat",
        "pending_input": "",
        "tts_rate": 160,
        "tts_enabled": False,
        "show_timestamps": False,
        "max_tokens": 512,
        "temperature": 0.7,
        "fc_cards": [],
        "fc_flipped": set(),
        "fc_known": set(),
        "editing_note": None,
        "regen_trigger": None,
    }
    sessions = memory.get_sessions()
    if "session_id" not in st.session_state:
        st.session_state["session_id"] = (
            sessions[0]["session_id"] if sessions else memory.new_session()
        )
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
