# Zariya Flask Web App

The Flask application for Urdu- and English-language assistance, with Ollama-backed local generation and a rule-based offline fallback.

## Overview

The web app streams responses from a local Ollama model when one is available. If local inference is disabled or unavailable, it can answer supported queries with its built-in knowledge engine. Optional integrations include Claude, Google Custom Search and GitHub OAuth; these require credentials configured by the deployer.

## Repository contents

- `app.py` — Flask routes, sessions and request handling.
- `local_model.py` — Ollama model availability, downloads and inference.
- `kb_engine.py` — rule-based offline answers and knowledge lookup.
- `embeddings.py` — optional local semantic search.
- `server/` — knowledge-base data and local application storage.
- `templates/` and `static/` — browser interface.
- `test_*.py` — offline knowledge, local-model and embedding checks.

## Technology

Python, Flask, Ollama, Requests, python-dotenv, vanilla JavaScript and CSS. Ollama and any selected model are installed separately from the Python packages.

## Run locally

Install and start [Ollama](https://ollama.com/), then from this directory run:

```bash
pip install -r requirements.txt
cp .env.example .env
python app.py
```

Open [http://localhost:5000](http://localhost:5000). The first chat request attempts to pull the default model, `qwen2.5:1.5b`, if Ollama is running and the model is not already available.

## Configuration

Copy `.env.example` to `.env` and set only the options you plan to use:

- `FLASK_SECRET_KEY` — session signing key; set a private random value outside local development.
- `APP_BASE_URL` — base URL used to construct OAuth callback URLs.
- `LOCAL_MODEL_NAME` — Ollama model name; defaults to `qwen2.5:1.5b`.
- `OLLAMA_URL` — Ollama server URL; defaults to `http://localhost:11434`.
- `DISABLE_LOCAL_MODEL=1` — skip local inference and use the offline knowledge engine.
- `ANTHROPIC_API_KEY` — optional Claude integration.
- `GOOGLE_API_KEY` and `GOOGLE_CX` — optional Google Custom Search integration.
- `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET` — optional GitHub OAuth.
- `KB_EMBEDDING_MODEL` — optional embedding model; defaults to `nomic-embed-text`.

## Tests

Install pytest, then run the checks from this directory:

```bash
pip install pytest
python test_kb_engine.py
pytest test_local_model.py
pytest test_embeddings.py
```

The local-model tests exercise the integration code; they do not establish model quality or replace testing with the Ollama instance and model you intend to use.

## Scope and limitations

The knowledge engine is a small, rule-based fallback rather than a general-purpose language model. Its coverage is limited to the bundled entries and supported operations. Model responses can be inaccurate. When Claude or web search is enabled, relevant prompts or searches are sent to the selected external service. This application stores its local data in JSON files and is a demonstration-scale application, not a multi-user production service.

## License

The code is licensed under the MIT License. See [../LICENSE](../LICENSE) for the full text.
