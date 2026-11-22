"""Sidebar: branding, page nav, conversation list, and storage stats."""
import streamlit as st


def render_sidebar(memory):
    with st.sidebar:
        st.markdown("""
        <div class="sidebar-brand">
          <div class="logo">Z</div>
          <div>
            <div class="name">Zariya</div>
            <div class="sub">ذریعہ</div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        pages = [
            ("chat",       "Chat"),
            ("flashcards", "Flashcards"),
            ("notepad",    "Notepad"),
            ("settings",   "Settings"),
        ]
        for pid, label in pages:
            is_active = st.session_state.page == pid
            if st.button(
                label,
                key=f"nav_{pid}",
                use_container_width=True,
                type="primary" if is_active else "secondary",
            ):
                st.session_state.page = pid
                st.rerun()

        st.markdown("---")

        if st.button("New Conversation", use_container_width=True, type="primary"):
            st.session_state.session_id = memory.new_session()
            st.session_state.page = "chat"
            st.rerun()

        st.markdown('<div class="sidebar-section">Recent</div>', unsafe_allow_html=True)
        sessions = memory.get_sessions()
        for s in sessions[:30]:
            sid    = s["session_id"]
            active = "active" if sid == st.session_state.session_id else ""
            title  = s.get("title", "Untitled")[:34]
            c1, c2 = st.columns([5, 1])
            with c1:
                label = ("-> " if active else "") + title
                if st.button(label, key=f"s_{sid}", use_container_width=True):
                    st.session_state.session_id = sid
                    st.session_state.page = "chat"
                    st.rerun()
            with c2:
                if st.button("x", key=f"d_{sid}"):
                    memory.delete_session(sid)
                    remaining = [x for x in sessions if x["session_id"] != sid]
                    st.session_state.session_id = (
                        remaining[0]["session_id"] if remaining else memory.new_session()
                    )
                    st.rerun()

        stats = memory.get_stats()
        st.markdown(
            f'<div class="sidebar-stats">'
            f'{stats["sessions"]} conversations &nbsp;·&nbsp; '
            f'{stats["messages"]} messages<br>'
            f'{stats["file_size_kb"]} KB on disk'
            f'</div>',
            unsafe_allow_html=True,
        )
