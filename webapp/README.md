# Zariya Flask Web App

The Urdu- and English-language browser application, deployable to Vercel with a bundled knowledge fallback.

## Overview

The Flask app provides chat, chat history, notepad, flashcards, import/export tools and browser speech features. It answers supported requests through its built-in knowledge engine without API credentials. Anthropic, Google Custom Search and GitHub OAuth are optional server-side integrations.

## Repository contents

- `app.py` — Flask routes, sessions and request handling.
- `local_model.py` — Ollama integration for local development.
- `kb_engine.py` — rule-based Urdu/English responses and knowledge lookup.
- `embeddings.py` — optional local semantic search.
- `server/` — bundled knowledge JSON and local-development storage.
- `templates/` — browser application shell.
- `static/` — source CSS, JavaScript and logo; mirrored to root `public/static/` for Vercel.
- `test_*.py` — knowledge, local-model and embedding checks.

## Technology

Python, Flask, Requests, python-dotenv, vanilla JavaScript and CSS. Ollama is an external service used only during local development.

## Run locally

```bash
python -m venv .venv
# Activate the environment, then:
pip install -r requirements.txt
cp .env.example .env
python app.py
```

Open [http://localhost:5000](http://localhost:5000). If Ollama is running locally, the app can use its configured model; otherwise it falls back to the bundled knowledge engine.

## Vercel deployment

Import the repository into Vercel with the project root set to `.`. The root `index.py` exports the Flask app, root `requirements.txt` contains only the web runtime dependencies, and Vercel serves `public/static/` from its static asset CDN.

Hosted mode disables Ollama because a Vercel Function does not run a persistent local Ollama daemon. Without an AI provider key, the chat uses the bundled rule-based knowledge engine.

## Configuration

Set optional values in Vercel Project Settings → Environment Variables, or copy `.env.example` to `.env` for local development:

- `FLASK_SECRET_KEY` — private random signing key of at least 32 characters. Required for reliable session cookies and GitHub OAuth.
- `APP_BASE_URL` — public base URL for OAuth callbacks; Vercel's deployment hostname is used as a fallback.
- `ANTHROPIC_API_KEY` and `ANTHROPIC_MODEL` — optional generative chat provider.
- `GOOGLE_API_KEY` and `GOOGLE_CX` — optional Google Custom Search.
- `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET` — optional GitHub profile sign-in; it is enabled only when both credentials and a stable `FLASK_SECRET_KEY` are configured.
- `DISABLE_LOCAL_MODEL=1` — disables Ollama; the Vercel entry point sets this automatically.

Never put provider credentials in browser JavaScript. Enabling Claude or Google Search sends relevant prompts or queries to those external providers.

## Tests

From the repository root:

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest tests/
```

Local web-app checks can be run from this directory with pytest installed:

```bash
python test_kb_engine.py
pytest test_local_model.py
pytest test_embeddings.py
```

## Scope and limitations

The knowledge engine is a curated, rule-based fallback, not a general-purpose language model. Its coverage is limited to supported operations and bundled entries. In hosted mode, chats, notes and flashcards are kept in the visitor's browser local storage; they are not synced across devices or accounts, and clearing browser storage removes them. Ollama is local-development only. Optional Anthropic and Google integrations send relevant content to those external services, and answers can be inaccurate.

## License

The code is licensed under the MIT License. See [../LICENSE](../LICENSE) for the full text.
