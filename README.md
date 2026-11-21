# Zariya

**Live application:** [zariyas.vercel.app](https://zariyas.vercel.app/)

An Urdu- and English-language workspace for chat, notes and flashcards, powered by Ollama models with a built-in knowledge fallback.

## Overview

The Flask web app in `webapp/` is the deployable browser application. It uses Ollama as its only generative model provider. On Vercel it connects to Ollama Cloud; during local development it can connect to an Ollama server running on the same computer. If no model endpoint is configured, supported requests use the bundled rule-based knowledge engine.

The older Streamlit app remains available for local experimentation and uses a separate GGUF model workflow.

## Repository contents

- `index.py` — Vercel entry point for the Flask app.
- `webapp/` — Flask routes, Ollama integration, bilingual knowledge engine, templates and browser interface.
- `public/` — favicon, web manifest, robots policy, sitemap and static browser assets.
- `app/` and `core/` — local Streamlit interface and model helpers.
- `tests/` — automated checks for the Vercel app and Ollama integration.

## Technology

Python 3.12, Flask, Requests, python-dotenv, Ollama, vanilla JavaScript and CSS. The Vercel deployment uses Ollama Cloud; local development supports the Ollama desktop/server application.

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

Install and start [Ollama](https://ollama.com/download), then pull a model such as `qwen2.5:1.5b`. Zariya connects to the local service at `http://localhost:11434` by default.

### Streamlit app

```bash
python -m venv .venv
# Activate the environment, then:
pip install -r requirements-streamlit.txt
python run.py
```

Place a compatible GGUF file at `models/model.gguf` to enable local generation in the Streamlit app.

Run the repository tests with:

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest tests/
```

## Deploy to Vercel

Import the repository into Vercel with the project root set to `.`. Vercel detects the Flask application through `index.py`; the root `requirements.txt` installs the lightweight web runtime.

To enable generative chat, add these server-side environment variables in Vercel Project Settings → Environment Variables:

- `OLLAMA_API_KEY` — create a key in [Ollama settings](https://ollama.com/settings/keys). Required for direct Ollama Cloud API access.
- `OLLAMA_MODEL` — optional model name; defaults to `gemma4:31b`. You can change the model in Zariya Settings.
- `OLLAMA_BASE_URL` — optional endpoint override; defaults to `https://ollama.com` on Vercel. A private remote Ollama server must be reachable over HTTPS and protected with an API key.

The key is used only by the server and is never sent to browser JavaScript. Ollama Cloud processes prompts and responses to generate answers. Without an Ollama key, Zariya falls back to its limited bundled knowledge engine.

Chats, notes and flashcards are stored in the visitor's browser local storage; they are not synced across devices or accounts. The Streamlit app and local Ollama development workflow are not part of the Vercel deployment.

## Scope and limitations

The built-in knowledge engine supports selected calculations, translations and curated knowledge entries. It is not a general-purpose language model. Generated answers can be inaccurate. Optional Google Search sends search terms to Google when enabled. Browser-local data is not cloud backup or account sync.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for the full text.
