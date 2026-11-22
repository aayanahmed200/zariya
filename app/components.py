"""Small reusable rendering helpers shared across pages."""
import html
import streamlit as st


def _safe(text: str) -> str:
    return html.escape(str(text))


def render_bubble(content: str, role: str, timestamp: str = ""):
    avatar_class = "bot" if role == "assistant" else "user"
    avatar_letter = "Z" if role == "assistant" else "U"
    bubble_class = "bot" if role == "assistant" else "user"
    time_str = timestamp[11:16] if len(timestamp) > 15 else ""

    col_av, col_msg = (st.columns([1, 11]) if role == "assistant" else st.columns([11, 1]))

    if role == "assistant":
        with col_av:
            st.markdown(
                f'<div class="avatar {avatar_class}">{avatar_letter}</div>',
                unsafe_allow_html=True,
            )
        with col_msg:
            st.markdown(
                f'<div class="bubble {bubble_class}">\n\n{content}\n\n</div>',
                unsafe_allow_html=True,
            )
            if time_str:
                st.markdown(
                    f'<div class="msg-time">{time_str}</div>',
                    unsafe_allow_html=True,
                )
    else:
        with col_msg:
            st.markdown(
                f'<div class="bubble {bubble_class}">{_safe(content)}</div>',
                unsafe_allow_html=True,
            )
            if time_str:
                st.markdown(
                    f'<div class="msg-time" style="text-align:right">{time_str}</div>',
                    unsafe_allow_html=True,
                )
        with col_av:
            st.markdown(
                f'<div class="avatar {avatar_class}">{avatar_letter}</div>',
                unsafe_allow_html=True,
            )
