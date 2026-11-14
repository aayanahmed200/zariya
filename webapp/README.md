# Zariya Web App

The actively developed Flask application for offline-first Urdu and low-resource-language assistance.

## Setup

Install and start [Ollama](https://ollama.com/), then run:

```bash
pip install -r requirements.txt
cp .env.example .env
python app.py
```

Open `http://localhost:5000`. The first chat request downloads the default local model (`qwen2.5:1.5b`) if Ollama is running. The offline knowledge engine can respond while the model downloads.

## How it works

- The Flask server connects to Ollama over its local HTTP API for model responses.
- `kb_engine.py` provides an offline fallback for arithmetic, unit conversions, Urdu/English vocabulary, and curated knowledge-base entries.
- Optional semantic search uses an Ollama embedding model when configured; it falls back to keyword matching if embeddings are unavailable.
- Optional Claude and web-search integrations run server-side when the deployer configures their credentials.
- GitHub sign-in uses a server-side OAuth flow when enabled.

## Configuration

Copy `.env.example` and configure only the features you plan to use:

- `LOCAL_MODEL_NAME` — Ollama model name; defaults to `qwen2.5:1.5b`.
- `OLLAMA_URL` — Ollama server URL; defaults to `http://localhost:11434`.
- `DISABLE_LOCAL_MODEL=1` — disable Ollama and use only the offline knowledge engine.
- `ANTHROPIC_API_KEY` — optional Claude integration.
- `GOOGLE_API_KEY` and `GOOGLE_CX` — optional Google Custom Search integration.
- `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET` — optional GitHub OAuth app credentials.
- `KB_EMBEDDING_MODEL` — optional Ollama embedding model; defaults to `nomic-embed-text`.

## Settings

The browser settings allow a per-browser persona prompt, response creativity setting, and switching between models already downloaded by Ollama. Changes take effect on the next message.

## Tests

- `python test_kb_engine.py` — offline knowledge-base regression checks.
- `pytest test_local_model.py` — Ollama integration tests.
- `pytest test_embeddings.py` — embedding parsing, similarity, caching, and fallback tests.

## Limitations

The default local model is small and may be slower or less capable than hosted models. The offline knowledge engine is a curated lookup system, not a general-purpose language model. Optional cloud integrations are separate from the offline path.

## Project files

- `app.py` — Flask routes, OAuth, and provider integrations.
- `kb_engine.py` — offline knowledge engine and fallback search.
- `local_model.py` — Ollama client.
- `embeddings.py` — optional local semantic search.
- `templates/` and `static/` — browser interface.
- `server/` — knowledge-base data and runtime cache files.
