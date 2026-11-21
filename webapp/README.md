# Zariya Flask Web App

**Live application:** [zariyas.vercel.app](https://zariyas.vercel.app/)

The Urdu- and English-language browser workspace, powered by Ollama with a built-in knowledge fallback.

## Overview

The Flask app provides chat, chat history, notepad, flashcards, deck import/export and browser speech features. Ollama is the only generative model provider. In production, visitors can connect their own local Ollama server directly from the browser without a paid cloud API key. Optional Ollama Cloud inference is supported through a server-side key. Without a model connection, selected queries are handled by the built-in rule-based knowledge engine.

## Repository contents

- `app.py` — Flask routes and request handling.
- `local_model.py` — Ollama local/cloud API connection, model listing and streaming.
- `kb_engine.py` — rule-based Urdu/English knowledge and selected operations.
- `embeddings.py` — optional local semantic search for local development.
- `server/` — bundled knowledge JSON and local-development storage.
- `templates/` — browser application shell.
- `static/` — source CSS, JavaScript and logo; mirrored to root `public/static/` for Vercel.

## Technology

Python, Flask, Requests, python-dotenv, Ollama, vanilla JavaScript and CSS.

## Run locally

```bash
python -m venv .venv
# Activate the environment, then:
pip install -r requirements.txt
cp .env.example .env
python app.py
```

Install and start [Ollama](https://ollama.com/download). Zariya uses `http://localhost:11434` by default. Pull a model first (for example, `qwen2.5:1.5b`), then choose it from Settings.

## Deploy to Vercel

Import the repository into Vercel with the project root set to `.`. The root `index.py` exports the Flask app, root `requirements.txt` contains the web runtime dependencies, and Vercel serves `public/` from its static asset CDN.

Vercel cannot run a desktop Ollama daemon inside a Function. The free path is to connect the visitor's Ollama app directly from the browser: install Ollama, download a model (for example `ollama pull qwen2.5:1.5b`), then allow `https://zariyas.vercel.app` in `OLLAMA_ORIGINS`. On Windows use `setx OLLAMA_ORIGINS "https://zariyas.vercel.app"`, quit and reopen Ollama, and press Test & connect in Settings. Local prompts stay on the visitor's computer.

Optional hosted inference uses an `OLLAMA_API_KEY` configured in Vercel Project Settings → Environment Variables. Direct Ollama Cloud API access is metered and can require usage credits; it is not needed for the local connection.

The Cloud API key is used on the server only. Ollama Cloud does not expose the local model inventory endpoint; Settings shows the active cloud model and lets you enter another model name manually.

Never place the Ollama API key in browser JavaScript, HTML or committed files.

## Configuration

- `OLLAMA_API_KEY` — required for Ollama Cloud or an authenticated remote Ollama endpoint.
- `OLLAMA_BASE_URL` — optional API root; local default is `http://localhost:11434`, hosted default is `https://ollama.com`.
- `OLLAMA_MODEL` — default model; local default is `qwen2.5:1.5b`, hosted default is `gemma4:31b`.
- `GOOGLE_API_KEY` and `GOOGLE_CX` — optional Google Custom Search credentials for the Search web tool.
- `FLASK_SECRET_KEY`, `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET` — optional GitHub profile sign-in configuration.

## Tests

From the repository root:

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest tests/
```

## Scope and limitations

The included knowledge engine is a curated, rule-based fallback, not a general-purpose language model. Ollama Cloud processes prompts and responses to generate answers. Browser chat history, notes and flashcards are kept in the visitor's local storage; they are not synced across devices or accounts, and clearing browser storage removes them. Model output can be incorrect.

## License

The code is licensed under the MIT License. See [../LICENSE](../LICENSE) for the full text.
