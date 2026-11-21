# Zariya

An Urdu- and English-language assistant with browser-based chat, notes and flashcards, a bundled knowledge fallback, and optional AI integrations.

## Overview

The Flask web app in `webapp/` is the deployable browser application. It runs on Vercel as a Python Flask app and works without API credentials through its bundled Urdu/English knowledge engine. Add an Anthropic API key to enable generative chat, or Google Custom Search credentials to enable web search.

The Streamlit app remains available for local experimentation. It uses a separate GGUF model workflow and is not part of the Vercel deployment.

## Repository contents

- `index.py` — Vercel entry point for the Flask app.
- `webapp/` — Flask routes, knowledge engine, templates and browser interface.
- `public/static/` — browser assets served by Vercel's static CDN.
- `app/` and `core/` — local Streamlit interface and model helpers.
- `tests/` — automated tests for the Vercel entry point and local core modules.

## Technology

Python 3.12, Flask, Requests, python-dotenv, vanilla JavaScript and CSS. Ollama is supported for local development only; Vercel Functions do not host the local Ollama service.

## Run locally

### Flask web app

```bash
cd webapp
python -m venv .venv
# Activate the environment, then:
pip install -r requirements.txt
cp .env.example .env
python app.py
```

Open [http://localhost:5000](http://localhost:5000). Without provider credentials, chat uses the bundled knowledge engine. For local model responses during development, start Ollama separately.

### Streamlit app

```bash
python -m venv .venv
# Activate the environment, then:
pip install -r requirements-streamlit.txt
python run.py
```

Place a compatible GGUF file at `models/model.gguf` to enable local generation in the Streamlit app.

To run the repository tests:

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest tests/
```

### Vercel

Import the repository into Vercel with the project root set to `.`. Vercel detects the Flask application through `index.py`; the root `requirements.txt` installs only the web runtime dependencies.

The app works without environment variables. Optional project environment variables are:

- `FLASK_SECRET_KEY` — a private random value of at least 32 characters; required for persistent sessions and GitHub OAuth.
- `ANTHROPIC_API_KEY` and optionally `ANTHROPIC_MODEL` — enables generative chat. Prompts are sent to Anthropic.
- `GOOGLE_API_KEY` and `GOOGLE_CX` — enables Google Custom Search.
- `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET` and `APP_BASE_URL` — enables GitHub sign-in. Configure the OAuth callback as `<APP_BASE_URL>/auth/github/callback`.

Ollama is automatically disabled in hosted mode. Chats, notes and flashcards are stored in the visitor's browser local storage; they are not synced across devices or accounts. The knowledge engine is rule-based, not a general-purpose language model.

## Scope and limitations

The built-in knowledge engine handles supported operations and curated entries only, so broad open-ended questions need an optional AI provider for generative answers. Answers can be inaccurate. Anthropic and Google integrations send relevant prompts or searches to those services. Browser-local data is not cloud backup or account sync.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for the full text.
