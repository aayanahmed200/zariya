import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import streamlit as st

from core.inference import get_engine
from core.memory import get_memory
from core.notes import get_notes
from core.tts import get_tts

from app.styles import STYLE_BLOCK
from app.state import init_state
from app.sidebar import render_sidebar
from app.views.chat import render_chat
from app.views.flashcards import render_flashcards
from app.views.notepad import render_notepad
from app.views.settings import render_settings

st.set_page_config(
    page_title="Zariya",
    page_icon="assets/favicon.png" if Path("assets/favicon.png").exists() else None,
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(STYLE_BLOCK, unsafe_allow_html=True)

memory = get_memory()
engine = get_engine()
notes  = get_notes()
tts    = get_tts()

init_state(memory)

engine._max_tokens  = st.session_state.max_tokens
engine._temperature = st.session_state.temperature

render_sidebar(memory)

page = st.session_state.page

if page == "chat":
    render_chat(engine, memory, tts)
elif page == "flashcards":
    render_flashcards(engine)
elif page == "notepad":
    render_notepad(engine, notes)
elif page == "settings":
    render_settings(engine, memory, tts)
