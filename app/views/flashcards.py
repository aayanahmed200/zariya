"""Flashcards page: generate, review, and track study cards."""
import streamlit as st

from app.components import _safe
from core.flashcards import generate_flashcards


def render_flashcards(engine):
    st.markdown("""
    <div class="page-header">
      <div class="page-logo">FC</div>
      <div>
        <div class="page-title">Flashcards</div>
        <div class="page-sub">AI-generated study cards</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    with st.expander("Generate new flashcards", expanded=not st.session_state.fc_cards):
        col_t, col_n = st.columns([4, 1])
        with col_t:
            topic = st.text_input("Topic", placeholder="e.g. Python decorators, WW2 causes, Photosynthesis...")
        with col_n:
            count = st.selectbox("Cards", [6, 8, 10, 12], index=1)
        if st.button("Generate", type="primary", use_container_width=True):
            if not topic.strip():
                st.warning("Enter a topic first.")
            elif engine.get_model_info()["status"] != "loaded":
                st.error("Model not loaded. Check Settings.")
            else:
                with st.spinner(f"Generating {count} flashcards on '{topic}'..."):
                    cards = generate_flashcards(topic, engine, count=count)
                if cards:
                    st.session_state.fc_cards   = cards
                    st.session_state.fc_flipped = set()
                    st.session_state.fc_known   = set()
                    st.success(f"Generated {len(cards)} cards.")
                    st.rerun()
                else:
                    st.error("Failed to generate cards. Try a more specific topic.")

    cards = st.session_state.fc_cards
    if cards:
        known  = st.session_state.fc_known
        total  = len(cards)
        pct    = int(len(known) / total * 100) if total else 0

        st.markdown(f"""
        <div class="fc-progress">
          <span style="font-size:12px; color:var(--muted)">{len(known)}/{total} known</span>
          <div class="fc-bar"><div class="fc-fill" style="width:{pct}%"></div></div>
          <span style="font-size:12px; color:var(--accent)">{pct}%</span>
        </div>
        """, unsafe_allow_html=True)

        if len(known) == total:
            st.success("All cards reviewed. Generate a new set to keep going.")

        b1, b2, b3 = st.columns([1, 1, 4])
        with b1:
            if st.button("Shuffle"):
                import random
                random.shuffle(st.session_state.fc_cards)
                # fc_known/fc_flipped track cards by position, not identity -- a shuffle
                # without clearing both would silently reattach "known" to the wrong card.
                st.session_state.fc_flipped = set()
                st.session_state.fc_known = set()
                st.rerun()
        with b2:
            if st.button("Reset"):
                st.session_state.fc_flipped = set()
                st.session_state.fc_known   = set()
                st.rerun()

        cols = st.columns(2)
        for i, card in enumerate(cards):
            flipped = i in st.session_state.fc_flipped
            is_known = i in st.session_state.fc_known
            card_class = "fc-card flipped" if flipped else "fc-card"
            border_extra = "border-color:var(--success);" if is_known else ""

            with cols[i % 2]:
                if flipped:
                    st.markdown(f"""
                    <div class="{card_class}" style="{border_extra}">
                      <div class="fc-label">Answer</div>
                      <div class="fc-text fc-answer">{_safe(card['back'])}</div>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div class="{card_class}">
                      <div class="fc-label">Question {i+1}</div>
                      <div class="fc-text">{_safe(card['front'])}</div>
                    </div>
                    """, unsafe_allow_html=True)

                c1, c2, c3 = st.columns(3)
                with c1:
                    label = "Hide" if flipped else "Reveal"
                    if st.button(label, key=f"flip_{i}", use_container_width=True):
                        flipped_set = st.session_state.fc_flipped
                        if i in flipped_set:
                            flipped_set.discard(i)
                        else:
                            flipped_set.add(i)
                        st.session_state.fc_flipped = flipped_set
                        st.rerun()
                with c2:
                    if st.button("Know it", key=f"know_{i}", use_container_width=True):
                        st.session_state.fc_known.add(i)
                        st.session_state.fc_flipped.discard(i)
                        st.rerun()
                with c3:
                    if st.button("Again", key=f"again_{i}", use_container_width=True):
                        st.session_state.fc_known.discard(i)
                        st.session_state.fc_flipped.discard(i)
                        st.rerun()

