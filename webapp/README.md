# Zariya Web App

The actively developed Flask application for offline-first Urdu and low-resource-language assistance.

## Overview

The web app connects to Ollama for local model responses and uses a curated offline knowledge engine as a fallback. The default local model is compact, and response quality and speed depend on the model and hardware. Optional integrations run server-side when configured by the deployer.

## Highlights

- Urdu and English support with token-by-token response streaming.
- Local model inference through Ollama.
- Offline fallback for arithmetic, unit conversions, Urdu/English vocabulary, and curated knowledge entries.
- Optional semantic search with local embeddings and keyword fallback.
- Optional Claude, web-search, and GitHub sign-in integrations.

## Technology

Python, Flask, Ollama, vanilla JavaScript, CSS, and optional local embedding models.

## Run locally

Install and start [Ollama](https://ollama.com/), then run:

```bash
pip install -r requirements.txt
cp .env.example .env
python app.py
```

Open `http://localhost:5000`. The first chat request downloads the default local model (`qwen2.5:1.5b`) if Ollama is running.

## Configuration

Copy `.env.example` and configure only the features you plan to use:

- `LOCAL_MODEL_NAME` — Ollama model; defaults to `qwen2.5:1.5b`.
- `OLLAMA_URL` — Ollama server; defaults to `http://localhost:11434`.
- `DISABLE_LOCAL_MODEL=1` — use only the offline knowledge engine.
- `ANTHROPIC_API_KEY` — optional Claude integration.
- `GOOGLE_API_KEY` and `GOOGLE_CX` — optional Google Custom Search integration.
- `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET` — optional GitHub OAuth.
- `KB_EMBEDDING_MODEL` — optional embedding model; defaults to `nomic-embed-text`.

## Tests

- `python test_kb_engine.py` — offline knowledge-base regression checks.
- `pytest test_local_model.py` — Ollama integration tests.
- `pytest test_embeddings.py` — embedding parsing, similarity, caching, and fallback tests.

