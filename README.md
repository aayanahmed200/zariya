# Zariya

[![Python](https://img.shields.io/badge/python-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/flask-000000?style=for-the-badge&logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![Streamlit](https://img.shields.io/badge/streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)](https://streamlit.io/)
**Repository:** [zariya](https://github.com/aayanahmed200/zariya)

Zariya is an offline-first AI assistant for Urdu and other low-resource languages. Once a model is downloaded, it runs entirely on your own device, so it works without an internet connection and doesn't depend on any cloud API to hold a conversation.

## Overview

A lot of AI tools quietly assume two things: that you have a solid internet connection, and that your language already has good support baked into the model. Neither of those is true everywhere, and they're especially not true for a lot of Urdu speakers. I started Zariya to see how far a genuinely local, privacy-first AI system could go, and to make sure Urdu wasn't treated as an afterthought.

## Architecture

The project has gone through two iterations, and both still work:

- **`webapp/`** - the version I'm actively developing. A Flask backend with a browser front end. It talks to a local model through Ollama, streams responses back token by token, and falls back to a small offline knowledge engine (no dependencies, no network calls) if a model isn't available yet. Claude API access, web search, and GitHub sign-in are all optional and configured server-side, so nobody using the app ever has to hold an API key.
- **the original Streamlit app** (`app/`, `core/`, `models/`) - a single-process version that loads a GGUF model directly with `llama.cpp`. Simpler to reason about, no server involved.

If you're only going to run one, use the web app - see [`webapp/README.md`](webapp/README.md) for its full setup.

## Capabilities

- Works fully offline once a model is downloaded
- Bilingual Urdu/English support
- Local inference - no data leaves your machine unless you turn on an optional cloud feature yourself
- Streaming, token-by-token responses in the web app
- A small offline knowledge engine as a safety net when no model is loaded yet
- Semantic fallback search over the knowledge base: when the fast keyword matcher comes up empty, the web app can optionally use a local Ollama embedding model to find the closest entry by meaning, not just shared words - and degrades silently back to keyword-only if Ollama or the embedding model isn't available

## Technology

- Python
- Flask (web app)
- Streamlit + llama-cpp-python (original app)
- Ollama for local model inference (web app)
- Vanilla JS/CSS front end

## Repository structure

- `webapp/` - Flask app, local model + offline fallback, browser front end
- `app/`, `core/`, `models/` - original Streamlit app and inference engine
- `tests/` - pytest suite for `core/`
- `run.py` - entry point for the Streamlit app
- `requirements.txt` - dependencies for the Streamlit app
- `requirements-dev.txt` - adds pytest, for running `tests/`

## Run locally

Run the web app - see [`webapp/README.md`](webapp/README.md) for full setup (Ollama install, `.env` config, optional Claude/search/GitHub sign-in).

To run the original Streamlit app instead: `pip install -r requirements.txt && streamlit run run.py`, then place a GGUF model in `models/` per `models/PLACE_MODEL_HERE.txt`.

## Status

Actively working on this. The offline knowledge engine covers everyday conversation, a general vocabulary bank, and a growing set of Pakistan-specific civic, financial, and cultural terms (CNIC/NADRA, mobile wallets, utilities, Ramadan-related terms, and similar), but it's still primarily a fixed lookup table, not a language model - ask it something outside that set (and outside what semantic search can match) and it says so rather than guessing. The local model path is only as good as whatever you point it at - a 1.5B model on a laptop CPU won't compete with a hosted large model, and I'd rather say that upfront than pretend otherwise.

## Testing

- `tests/` - covers the Streamlit app's core logic (`core/`): session memory, notes, flashcard generation/parsing, TTS markdown stripping, model downloads, and inference (chat + streaming, including the chat-template-unsupported fallback path). Run with `pip install -r requirements-dev.txt && pytest tests/`.
- `webapp/test_kb_engine.py` - runs 570 varied prompts through the offline knowledge engine and checks for crashes or regressions. Run with `python webapp/test_kb_engine.py` (standard library only, no install needed).
- `webapp/test_local_model.py` - covers the Ollama integration: model-tag matching, and reply generation/streaming. Run with `pytest webapp/test_local_model.py`.
- `webapp/test_embeddings.py` - covers the semantic KB search fallback: embedding parsing, cosine similarity, caching, and the two required fallback behaviors (keyword-empty triggers semantic search; embeddings unavailable falls back silently to keyword-only). Run with `pytest webapp/test_embeddings.py`.

## License

MIT - see [LICENSE](LICENSE).
