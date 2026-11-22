"""Notepad page: persistent notes stored on disk via core.notes."""
import streamlit as st

from app.components import _safe


def render_notepad(engine, notes):
    st.markdown("""
    <div class="page-header">
      <div class="page-logo">NP</div>
      <div>
        <div class="page-title">Notepad</div>
        <div class="page-sub">Quick offline notes, saved to disk</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    all_notes = notes.get_all()
    editing   = st.session_state.editing_note

    col_list, col_edit = st.columns([2, 3])

    with col_list:
        if st.button("New Note", use_container_width=True, type="primary"):
            new_note = notes.create()
            st.session_state.editing_note = new_note["id"]
            st.rerun()

        st.markdown("<div style='height:.5rem'></div>", unsafe_allow_html=True)

        if not all_notes:
            st.markdown("<div style='color:var(--muted); font-size:13px; padding:1rem 0;'>No notes yet.</div>", unsafe_allow_html=True)

        for note in all_notes:
            nid     = note["id"]
            active  = "border-color:var(--accent);" if nid == editing else ""
            preview = note["body"][:60].replace("\n", " ") or "Empty note"
            date    = note.get("updated_at", note.get("created_at", ""))[:10]

            st.markdown(f"""
            <div class="note-card" style="{active}">
              <div class="note-title">{_safe(note['title'])}</div>
              <div class="note-preview">{_safe(preview)}</div>
              <div class="note-date">{date}</div>
            </div>
            """, unsafe_allow_html=True)

            nb1, nb2 = st.columns([3, 1])
            with nb1:
                if st.button("Open", key=f"open_{nid}", use_container_width=True):
                    st.session_state.editing_note = nid
                    st.rerun()
            with nb2:
                if st.button("Del", key=f"del_note_{nid}", use_container_width=True):
                    notes.delete(nid)
                    if editing == nid:
                        st.session_state.editing_note = None
                    st.rerun()

    with col_edit:
        if editing:
            note = notes.get(editing)
            if note:
                new_title = st.text_input("Title", value=note["title"], key=f"nt_{editing}")
                new_body  = st.text_area("Content", value=note["body"], height=380, key=f"nb_{editing}")

                ec1, ec2, ec3 = st.columns(3)
                with ec1:
                    if st.button("Save", use_container_width=True, type="primary"):
                        notes.update(editing, new_title, new_body)
                        st.success("Saved.")
                with ec2:
                    show_copy = st.button("Copy", use_container_width=True)
                with ec3:
                    if st.button("Improve with AI", use_container_width=True):
                        if engine.get_model_info()["status"] == "loaded" and new_body.strip():
                            with st.spinner("Thinking..."):
                                ai_resp = engine.chat([{
                                    "role": "user",
                                    "content": f"Improve and expand this note, keeping the original meaning:\n\n{new_body}"
                                }])
                            notes.update(editing, new_title, ai_resp)
                            st.rerun()
                        else:
                            st.warning("Model not loaded or note is empty.")
                if show_copy:
                    st.code(new_body, language=None, wrap_lines=True)
            else:
                st.session_state.editing_note = None
                st.rerun()
        else:
            st.markdown("""
            <div style="display:flex; align-items:center; justify-content:center; height:300px; color:var(--muted); font-size:14px;">
              Select a note or create a new one
            </div>
            """, unsafe_allow_html=True)

