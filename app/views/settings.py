"""Settings page: model setup/download, generation params, TTS, data."""
import json as _json

import streamlit as st

from app.components import _safe
from core.model_downloader import RECOMMENDED_MODELS, download_model, validate_url, DownloadError


def render_settings(engine, memory, tts):
    st.markdown("""
    <div class="page-header">
      <div class="page-logo">Cfg</div>
      <div>
        <div class="page-title">Settings</div>
        <div class="page-sub">Model, interface, TTS, data</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    with st.container():
        st.markdown('<div class="setting-group">', unsafe_allow_html=True)
        st.markdown('<div class="setting-title">Model</div>', unsafe_allow_html=True)
        info = engine.get_model_info()
        if info["status"] == "loaded":
            st.markdown(f"""
            <div class="model-badge">{_safe(info['name'])} &nbsp;·&nbsp; {info['size_mb']} MB</div>
            """, unsafe_allow_html=True)
        else:
            st.markdown('<div class="model-badge err">No model loaded</div>', unsafe_allow_html=True)

            dl_choice = st.selectbox(
                "Download a model",
                [m["label"] for m in RECOMMENDED_MODELS] + ["Custom URL..."],
                key="model_dl_choice",
            )
            if dl_choice == "Custom URL...":
                dl_url = st.text_input(
                    "Direct .gguf download URL",
                    placeholder="https://huggingface.co/.../resolve/main/model.gguf",
                    key="model_dl_custom_url",
                )
            else:
                dl_url = next(m["url"] for m in RECOMMENDED_MODELS if m["label"] == dl_choice)
                st.caption(dl_url)

            if st.button("Download model", type="primary", use_container_width=True):
                url_err = validate_url(dl_url) if dl_url else "Enter a URL first."
                if url_err:
                    st.error(url_err)
                else:
                    progress_bar = st.progress(0.0)
                    status = st.empty()

                    def _on_progress(done, total, _bar=progress_bar, _status=status):
                        if total:
                            _bar.progress(min(done / total, 1.0))
                            _status.caption(f"{done / 1e6:.0f} MB / {total / 1e6:.0f} MB")
                        else:
                            _status.caption(f"{done / 1e6:.0f} MB downloaded")

                    try:
                        download_model(dl_url, progress_callback=_on_progress)
                        engine.reload()
                        st.success("Model downloaded and loaded.")
                        st.rerun()
                    except DownloadError as e:
                        st.error(str(e))

            with st.expander("Manual setup instead"):
                st.markdown("""
1. Download a `.gguf` model from [huggingface.co/TheBloke](https://huggingface.co/TheBloke)
2. Place it in the `models/` folder as `model.gguf`
3. Restart the app

**GPU acceleration:**
```bash
# NVIDIA
CMAKE_ARGS="-DLLAMA_CUDA=on" pip install llama-cpp-python --force-reinstall
# Apple Silicon
CMAKE_ARGS="-DLLAMA_METAL=on" pip install llama-cpp-python --force-reinstall
```
                """)
        st.markdown('</div>', unsafe_allow_html=True)

    with st.container():
        st.markdown('<div class="setting-group">', unsafe_allow_html=True)
        st.markdown('<div class="setting-title">Generation</div>', unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            new_temp = st.slider("Temperature", 0.0, 1.5, st.session_state.temperature, 0.05,
                help="Higher = more creative. Lower = more focused.")
            st.session_state.temperature = new_temp
        with c2:
            new_tok = st.slider("Max tokens", 128, 2048, st.session_state.max_tokens, 64,
                help="Maximum length of each response.")
            st.session_state.max_tokens = new_tok
        st.markdown('</div>', unsafe_allow_html=True)

    with st.container():
        st.markdown('<div class="setting-group">', unsafe_allow_html=True)
        st.markdown('<div class="setting-title">Text-to-Speech</div>', unsafe_allow_html=True)
        if tts.available:
            st.session_state.tts_enabled = st.toggle("Auto read-aloud", st.session_state.tts_enabled)
            voices = tts.get_voices()
            if voices:
                voice_names = [v["name"] for v in voices]
                sel = st.selectbox("Voice", voice_names)
                chosen = next((v for v in voices if v["name"] == sel), None)
                if chosen:
                    tts.set_voice(chosen["id"])
            new_rate = st.slider("Speed (wpm)", 80, 280, st.session_state.tts_rate, 10)
            st.session_state.tts_rate = new_rate
            tts.set_rate(new_rate)
            if st.button("Test voice"):
                tts.speak("Assalam-o-Alaikum. Main Zariya hoon, aap ka offline AI assistant.")
        else:
            st.info("TTS not available. Install: `pip install pyttsx3`")
        st.markdown('</div>', unsafe_allow_html=True)

    with st.container():
        st.markdown('<div class="setting-group">', unsafe_allow_html=True)
        st.markdown('<div class="setting-title">Interface</div>', unsafe_allow_html=True)
        st.session_state.show_timestamps = st.toggle(
            "Show message timestamps", st.session_state.show_timestamps)
        st.markdown('</div>', unsafe_allow_html=True)

    with st.container():
        st.markdown('<div class="setting-group">', unsafe_allow_html=True)
        st.markdown('<div class="setting-title">Data</div>', unsafe_allow_html=True)
        stats = memory.get_stats()
        sc1, sc2, sc3 = st.columns(3)
        with sc1:
            st.metric("Conversations", stats["sessions"])
        with sc2:
            st.metric("Messages", stats["messages"])
        with sc3:
            st.metric("Storage", f"{stats['file_size_kb']} KB")

        st.markdown("<div style='height:.5rem'></div>", unsafe_allow_html=True)

        sid     = st.session_state.session_id
        session = next((s for s in memory.get_sessions() if s["session_id"] == sid), None)
        if session:
            ec1, ec2, ec3 = st.columns(3)
            with ec1:
                text = memory.export_session(sid)
                if text:
                    st.download_button("Export chat (.txt)", text,
                        file_name=f"zariya_{session['title'][:20]}.txt",
                        mime="text/plain", use_container_width=True)
            with ec2:
                all_data = _json.dumps(memory.get_sessions(), ensure_ascii=False, indent=2)
                st.download_button("Export all (.json)", all_data,
                    file_name="zariya_all_chats.json",
                    mime="application/json", use_container_width=True)
            with ec3:
                if st.button("Clear all history", use_container_width=True):
                    memory.clear_all()
                    st.session_state.session_id = memory.new_session()
                    st.success("Cleared.")
                    st.rerun()

        st.markdown("<div style='height:.5rem'></div>", unsafe_allow_html=True)
        if session:
            new_name = st.text_input("Rename current conversation", value=session.get("title",""))
            if st.button("Rename"):
                memory.rename_session(sid, new_name)
                st.success(f'Renamed to "{new_name}"')
                st.rerun()

        st.markdown("**Search all conversations**")
        q = st.text_input("Search", placeholder="Type to search...", label_visibility="collapsed")
        if q:
            results = memory.search(q)
            if results:
                for r in results[:12]:
                    prefix = "You" if r["role"] == "user" else "Zariya"
                    st.markdown(f"""
                    <div style="background:var(--surface2); border:1px solid var(--border); border-radius:8px; padding:9px 13px; margin-bottom:7px;">
                      <div style="font-size:11px; color:var(--muted);">{_safe(r['session_title'])} &nbsp;·&nbsp; {prefix}</div>
                      <div style="font-size:13px; margin-top:3px;">{_safe(r['snippet'])}...</div>
                    </div>
                    """, unsafe_allow_html=True)
                    if st.button("Open", key=f"sr_{r['session_id']}_{r['snippet'][:10]}"):
                        st.session_state.session_id = r["session_id"]
                        st.session_state.page = "chat"
                        st.rerun()
            else:
                st.info("No results found.")
        st.markdown('</div>', unsafe_allow_html=True)

    with st.container():
        st.markdown('<div class="setting-group">', unsafe_allow_html=True)
        st.markdown('<div class="setting-title">About</div>', unsafe_allow_html=True)
        st.markdown("""
**Zariya v2** — Offline AI Assistant for Urdu & English

Built with `llama-cpp-python`, `Streamlit`, `pyttsx3`

Fully local — no data leaves your device.
Supports Urdu, Roman Urdu, and English.

[GitHub](https://github.com/aayanahmed200/zariya) · MIT License
        """)
        st.markdown('</div>', unsafe_allow_html=True)
