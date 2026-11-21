# Zariya Flask Web App

**Live application:** [zariyas.vercel.app](https://zariyas.vercel.app/)

A hosted Urdu and English workspace for chat, notes and flashcards. Visitors can open the site and chat without installing Ollama, downloading a model or entering a personal API key.

## Overview

The Flask app provides chat, bilingual voice typing, chat history, notepad, flashcards, deck import/export and browser text-to-speech. Chat is routed server-side through Vercel AI Gateway using the short-lived OIDC token injected into each Function request as `x-vercel-oidc-token`. The default open-weight model is `nvidia/nemotron-3.5-lightning-free`, currently listed at $0 per input/output token. Free provider capacity and rate limits can change; when hosted inference is unavailable, selected requests use the bundled rule-based knowledge engine.

The current NVIDIA model-provider listing does not advertise zero-data-retention or a no-training guarantee. Chat prompts are transmitted to the Gateway and model provider. Voice typing uses the browser speech-recognition service; its audio handling depends on the browser's provider. Zariya does not store voice recordings. Users should not enter passwords, private records or sensitive information.

Quick actions for conversation summaries, key points, translation and flashcards use the hosted model where it is available, and use the bundled knowledge engine if the provider is unavailable. The composer supports English and Urdu voice typing in browsers that expose the Web Speech Recognition API. The voice language can be selected next to the microphone button. Zariya does not store voice recordings; audio may be processed by the browser's speech-recognition provider. Workspace backup export and restore are available in Settings, and existing flashcard decks can be edited while retaining review scheduling.

## Repository contents

- `app.py` — Flask routes and request handling.
- `hosted_model.py` — Vercel AI Gateway authentication, chat completions and streaming.
- `kb_engine.py` — rule-based Urdu/English knowledge and selected operations.
- `embeddings.py` — optional local semantic search for development.
- `server/` — bundled knowledge JSON and local-development storage.
- `templates/` — browser application shell.
- `static/` — source CSS, JavaScript and logo; mirrored to root `public/static/` for Vercel.

## Technology

Python, Flask, Requests, python-dotenv, Vercel AI Gateway, vanilla JavaScript and CSS.

## Run locally

```bash
python -m venv .venv
# Activate the environment, then:
pip install -r requirements.txt
cp .env.example .env
python app.py
```

The local Flask app works without a model token using its built-in knowledge fallback. For local hosted-model testing only, set `AI_GATEWAY_API_KEY` in your uncommitted `.env` file. The deployed website does not require this variable: Vercel injects the OIDC token as `x-vercel-oidc-token` on the incoming Function request when OIDC token generation is enabled.

## Deploy to Vercel

Import the repository into Vercel with the project root set to `.`. The root `index.py` exports the Flask app, root `requirements.txt` contains the web runtime dependencies, and Vercel serves `public/` from its static asset CDN.

Vercel OIDC token generation is enabled for the project. At Function runtime, Vercel injects the short-lived token as `x-vercel-oidc-token`; the Flask routes pass that header to `https://ai-gateway.vercel.sh/v1/chat/completions`. Visitors do not need to install an app, download a model or supply an API key.

The default Gateway model is `nvidia/nemotron-3.5-lightning-free`. Its live catalogue listing currently shows $0 input and output token pricing. Free model availability and provider rate limits are not guaranteed. Override it with `AI_GATEWAY_MODEL` only if another model is supported and intentionally configured.

## Configuration

- `AI_GATEWAY_MODEL` — optional server-side model override; defaults to `nvidia/nemotron-3.5-lightning-free`.
- `AI_GATEWAY_API_KEY` — optional for local development only; do not commit it. Vercel deployments use OIDC instead.
- `GOOGLE_API_KEY` and `GOOGLE_CX` — optional Google Custom Search credentials for the Search web tool.
- `FLASK_SECRET_KEY`, `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET` — optional GitHub profile sign-in configuration.

## Tests

From the repository root:

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest tests/
```

## Data and limitations

Hosted AI prompts are sent to Vercel AI Gateway and NVIDIA's selected model provider. The provider does not currently advertise zero-data-retention or a no-training guarantee; do not send sensitive information. Browser chat history, notes and flashcards are kept in the visitor's local storage; they are not synced across devices or accounts, and clearing browser storage removes them. Model output can be incorrect. The built-in knowledge engine is a limited rule-based fallback rather than a general-purpose AI model.

## License

The code is licensed under the MIT License. See [../LICENSE](../LICENSE) for the full text.
