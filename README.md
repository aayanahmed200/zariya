# Zariya

An Urdu- and English-language assistant with local model options and a rule-based knowledge fallback. The repository contains two separate applications: a Streamlit app and a Flask web app.

## Overview

The original application at the repository root uses `llama-cpp-python` to run a GGUF model locally. The launcher is `run.py`; place a compatible model at `models/model.gguf` for local generation.

The newer application is in `webapp/`. It is a Flask app that uses Ollama for local model responses and a built-in knowledge engine when a model is unavailable. It can also connect to optional services such as Claude, Google Custom Search and GitHub OAuth when the deployer configures the relevant credentials.

These are separate implementations with separate dependencies and setup steps. See [the web app README](webapp/README.md) for its configuration details.

## Repository contents

- `app/` — Streamlit interface, chat views, settings, notes and flashcards.
- `core/` — local inference, model download, memory, notes, flashcards, summarisation and text-to-speech helpers.
- `models/` — location for the GGUF model used by the Streamlit app.
- `webapp/` — Flask application, Ollama integration, knowledge engine, templates and browser assets.
- `tests/` — tests for the original application's core functions.

## Technology

Python, Streamlit, `llama-cpp-python`, Flask, Ollama, Requests, vanilla JavaScript and CSS. Ollama is installed separately from the Python packages.

## Run locally

### Streamlit application

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

The launcher starts Streamlit. Add a compatible GGUF file at `models/model.gguf`; without it, the interface can start but local model responses will not be available.

### Flask web application

```bash
cd webapp
pip install -r requirements.txt
cp .env.example .env
python app.py
```

Install and start [Ollama](https://ollama.com) to use local model generation. If it is unavailable, the app can fall back to its built-in knowledge engine. Configure optional integrations in `webapp/.env.example` only when you intend to use them.

Run the root tests with `pytest tests/`. The web app has its own checks in `webapp/`; see [webapp/README.md](webapp/README.md).

## Scope and limitations

The knowledge engine is a curated, rule-based fallback, not a general-purpose language model. Model output can be incorrect. The local applications can run without cloud credentials, but enabling Claude or web search sends the relevant request to those external services. The Flask web app stores application data in a local JSON file and is documented in its source as a demonstration-scale setup, not a multi-tenant production database.

## License

MIT. See [LICENSE](LICENSE).
