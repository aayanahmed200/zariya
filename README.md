# Zariya

**Live application:** [zariyas.vercel.app](https://zariyas.vercel.app/)

A bilingual Urdu and English workspace for AI chat, voice typing, notes and flashcards. The hosted website uses an open-weight language model through Vercel AI Gateway; visitors do not need to install Ollama or create an API key.

## Overview

The Flask web app in `webapp/` is the deployable browser application. Chat requests are sent from the Flask server to Vercel AI Gateway using the short-lived OIDC token that Vercel injects into each Function request as `x-vercel-oidc-token`. The default model is `nvidia/nemotron-3.5-lightning-free`, which is currently listed at $0 per input and output token in the Vercel AI Gateway catalogue. Free-model capacity and rate limits can change, so the app falls back to its built-in knowledge engine when hosted inference is unavailable.

The model is hosted by a third-party provider. Its current provider listing does not advertise zero-data-retention or a no-training guarantee. Avoid entering passwords, private records or other sensitive information in chat.

The composer records microphone audio in the browser and sends a short WAV recording to the server-side transcription endpoint. Vercel AI Gateway routes it to Microsoft MAI-Transcribe 2, with automatic language detection or explicit English/Urdu selection. This avoids the browser's experimental Web Speech Recognition API. Microphone permission and a secure HTTPS context are required. Zariya does not save recordings, but audio is transmitted to Vercel AI Gateway and Microsoft Azure for transcription. The listed transcription rate is approximately $0.10 per audio hour and may change. The workspace also supports JSON backup export and restore, and existing flashcard decks can be edited without resetting their spaced-repetition history.

Quick actions for summaries, key points, translation and flashcard creation use the hosted model with the built-in knowledge engine as a fallback. Urdu is rendered with a dedicated Noto Sans Arabic typeface, including Urdu phrases embedded in English answers. Response-style presets (Balanced, Concise, Step-by-step and Detailed) work alongside optional custom instructions; flashcards and quiz controls use bilingual text rendering and clear answer feedback.

The older Streamlit app remains available for local experimentation and uses a separate GGUF model workflow; it is not required to use the hosted website.

## Repository contents

- `index.py` — Vercel entry point for the Flask app.
- `webapp/` — Flask routes, hosted AI Gateway adapter, bilingual knowledge engine, templates and browser interface.
- `public/` — favicon, web manifest, robots policy, sitemap and static browser assets.
- `app/` and `core/` — local Streamlit interface and model helpers.
- `tests/` — automated checks for the hosted app, streaming, Gateway integration and SEO.

## Technology

Python 3.12, Flask, Requests, python-dotenv, Vercel AI Gateway, vanilla JavaScript and CSS.

## Run locally

```bash
cd webapp
python -m venv .venv
# Activate the environment, then:
pip install -r requirements.txt
cp .env.example .env
python app.py
```

Without an AI Gateway token, the local Flask server still starts and uses the bundled knowledge fallback. For local hosted-model testing, add an `AI_GATEWAY_API_KEY` to your uncommitted `.env` file. The deployed website does not need this key; Vercel supplies the OIDC token in the incoming Function request header.

### Streamlit app

```bash
python -m venv .venv
# Activate the environment, then:
pip install -r requirements-streamlit.txt
python run.py
```

Place a compatible GGUF file at `models/model.gguf` to enable generation in the separate Streamlit app.

Run the repository tests with:

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest tests/
```

## Deploy to Vercel

Import the repository into Vercel with the project root set to `.`. Vercel detects the Flask application through `index.py`; the root `requirements.txt` installs the web runtime.

The Vercel project has OIDC token generation enabled. At build time Vercel exposes `VERCEL_OIDC_TOKEN`; at Function runtime it injects the short-lived token as `x-vercel-oidc-token`, which the Flask routes pass to AI Gateway. No provider-specific API key or visitor setup is required. The optional `AI_GATEWAY_MODEL` environment variable can override the default model, but the configured model must be available through the team's Gateway.

The default NVIDIA Nemotron 3.5 Lightning Free model is currently listed at $0 per token. That is the model's current catalogue price, not a guarantee of unlimited capacity or permanent availability. If it is unavailable or rate-limited, chat falls back to the built-in knowledge engine until hosted inference is available again.

## Data and limitations

Chats, notes and flashcards are stored in the visitor's browser local storage; they are not synced across devices or accounts. Clearing browser storage removes them. For AI chat, message content is transmitted to Vercel AI Gateway and the selected model provider. The current NVIDIA model listing does not claim zero data retention or a no-training guarantee; do not send sensitive information. Voice recordings are transmitted to Vercel AI Gateway and Microsoft Azure for transcription and are not saved by Zariya. Generated answers and transcripts can be inaccurate; review them before relying on or sending them.

The built-in knowledge engine supports selected calculations, translations and curated knowledge entries. It is not a general-purpose language model. Optional Google Search sends search terms to Google when enabled.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for the full text.
