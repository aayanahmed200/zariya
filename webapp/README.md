# Zariya - Web App

This is the actively developed version of Zariya: a Flask backend with a browser front end, built around privacy-first, offline-first AI for Urdu and other low-resource languages.

## How it's built

This is a real Flask backend plus a browser front end, not a single static page, and that matters for a few reasons.

By default, Zariya talks to a free local model runner called Ollama, which runs open-source models entirely on your own machine, so there's no API key to sign up for and nothing to paste into a settings screen. If you do choose to add optional Claude, Google Search, or GitHub OAuth credentials, they live in a server-side `.env` file - whoever deploys this configures them once, and the person using the app never has to enter a key themselves. GitHub sign-in uses a real OAuth authorization-code flow with the client secret exchanged server-side, the way GitHub's own docs describe, not a public-profile lookup dressed up as a login.

Underneath all of that sits `kb_engine.py`, a genuinely offline core with no dependencies and no network calls: arithmetic, unit conversion, a bilingual Urdu/English dictionary of roughly 699 words, and a curated knowledge base of roughly 792 entries matched with a fuzzy scorer. It's the guaranteed fallback if Ollama isn't installed or running, or while a model is still downloading, so the app never goes blank. When the local model (or Claude, if configured) gives a real answer, it gets cached server-side and reused for similarly worded questions later - a growing local memory, not model retraining.

## Setup

1. Install Ollama once: https://ollama.com/download (a normal installer for Windows/Mac/Linux - no C++ compiler, no account, nothing to configure). Make sure it's running.
2. Run these commands:
   ```bash
   pip install -r requirements.txt
   cp .env.example .env
   python app.py
   ```
3. Open `http://localhost:5000`. On the first chat request, Zariya asks Ollama to pull a small model (`qwen2.5:1.5b` by default, about 1GB, free, one-time) automatically - no command needed from you. The offline knowledge engine answers immediately in the meantime, then the app switches over to the real local model once it's ready.

This used to load model files directly in-process with `llama-cpp-python`, which needed a working C++ build toolchain and failed to install on a number of machines. Talking to Ollama over plain HTTP instead avoids that entirely - Ollama ships its own prebuilt binaries.

### Using a different local model

Set `LOCAL_MODEL_NAME` in `.env` to any model name from https://ollama.com/library (for example `llama3.2:1b` or `qwen2.5:3b`).

### Running Ollama elsewhere

Set `OLLAMA_URL` in `.env` if Ollama is running on a different host or port than the default `http://localhost:11434`.

### Disabling the local model entirely

Set `DISABLE_LOCAL_MODEL=1` in `.env` for a purely offline, lookup-table-only deployment that never tries to contact Ollama.

### Optional: Claude API

Get a key from the Anthropic Console and set `ANTHROPIC_API_KEY` in `.env`. When it's set, Claude is tried first, then the local model, then the offline knowledge engine.

### Optional: Web search

Create a search engine at programmablesearchengine.google.com (set it to search the whole web) and an API key at console.cloud.google.com (enable the Custom Search API). Set `GOOGLE_API_KEY` and `GOOGLE_CX`.

### Optional: Semantic knowledge-base search

The offline knowledge engine's fast keyword/edit-distance matcher is tried first; if it comes back empty, `embeddings.py` can fall back to semantic search using Ollama's embedding endpoint. Pull an embedding model once (`ollama pull nomic-embed-text`, the default - set `KB_EMBEDDING_MODEL` in `.env` to use a different one) and it's used automatically from then on. KB embeddings are computed once and cached to `server/kb_embeddings_cache.json`, keyed by content hash, so only new or changed entries are re-embedded. If Ollama or the embedding model isn't available, this fails silently and the app keeps working with keyword matching only.

### Optional: Real GitHub sign-in

Create an OAuth App at github.com/settings/developers:

- Homepage URL: `http://localhost:5000`
- Authorization callback URL: `http://localhost:5000/auth/github/callback`

Set `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET` in `.env`.

## Persona, creativity, and switching models

A few things are tunable from Settings, per browser, without touching `.env`:

- **Persona / system prompt.** Replace Zariya's default personality with your own instructions for this browser only. Leave it blank to use the default.
- **Creativity.** A temperature slider (0 to 1) sent with every chat request, applied to whichever backend answers -- lower for more predictable replies, higher for more varied ones.
- **Local model switching.** Settings lists every model Ollama has already pulled and lets you switch the active one instantly, or type in any model name from https://ollama.com/library to pull and switch to a new one in the background.

None of this requires a restart -- changes take effect on the next message.


## An honest limit

The default local model is small (1.5B parameters) so it downloads quickly and runs on ordinary laptop CPUs, but it's noticeably less capable and slower than a large hosted model. The offline knowledge engine below it is a curated lookup table with a fuzzy matcher, not a language model, and will always have gaps outside its ~792 entries. For higher-quality or faster answers, connect the Claude API or point `LOCAL_MODEL_NAME` at a larger Ollama model - there's no way around that trade-off, and I'd rather say so here than pretend otherwise.

## Project layout

- `app.py` - Flask app: routes, OAuth, Claude/Search proxying, model fallback chain
- `kb_engine.py` - offline knowledge engine (no dependencies, no network), with an optional semantic-search fallback
- `embeddings.py` - Ollama embeddings client + cosine-similarity search + on-disk cache, used by `kb_engine.py`'s semantic fallback
- `local_model.py` - local-model inference via Ollama's HTTP API
- `templates/index.html` - frontend markup
- `static/app.js` - frontend logic (talks only to this server's own API)
- `static/style.css` - styling
- `server/kb_data.json` - dictionary + knowledge base data
- `server/kb_embeddings_cache.json` - cached KB embeddings for semantic search (created at runtime, gitignored)
- `server/store.json` - per-user notes/sessions/decks (created at runtime)
- `server/learned.json` - cached AI answers (created at runtime)
