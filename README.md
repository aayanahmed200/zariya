# Zariya

> A bilingual Urdu-English assistant and workspace combining hosted AI chat, voice transcription, notes, and flashcards, with a curated fallback when hosted inference is unavailable.

**Live application:** [zariya.vercel.app](https://zariya.vercel.app/)

[![Python](https://img.shields.io/badge/python-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/) [![Flask](https://img.shields.io/badge/flask-000000?style=for-the-badge&logo=flask&logoColor=white)](https://flask.palletsprojects.com/) [![JavaScript](https://img.shields.io/badge/javascript-F7DF1E?style=for-the-badge&logo=javascript&logoColor=111)](https://developer.mozilla.org/en-US/docs/Web/JavaScript) [![Vercel](https://img.shields.io/badge/vercel-000000?style=for-the-badge&logo=vercel&logoColor=white)](https://vercel.com/) [![Supabase](https://img.shields.io/badge/supabase-3FCF8E?style=for-the-badge&logo=supabase&logoColor=white)](https://supabase.com/)

## Overview

Zariya provides an Urdu-English interface for asking questions, working with notes, and building flashcards. The hosted Flask application sends chat requests to an open-weight model through Vercel AI Gateway. On Vercel, server-side OIDC credentials authenticate those requests; visitors do not need to install Ollama, download a model, or provide a personal model API key to use the hosted app. When hosted inference is unavailable, selected requests can use the bundled knowledge engine.

The workspace also includes voice typing, response-style presets, and quick actions for tasks such as summaries, key points, translation, and flashcard creation. The repository retains an earlier local Streamlit interface as a separate experimentation path.

## Highlights

- Urdu and English interface with direction-aware text and a dedicated Urdu typeface.
- Hosted chat through Vercel AI Gateway, with a curated knowledge-engine fallback.
- Browser microphone capture and server-side transcription with language selection.
- Notes and flashcards, including spaced-repetition support and JSON backup/restore.
- Response-style presets, optional custom instructions, and task-specific quick actions.
- Optional Supabase workspace storage and GitHub sign-in integration.
- Legacy local Streamlit interface for experimenting with a local GGUF model.

## Implementation

The deployed web application is a Flask rewrite in `webapp/`, served through the Vercel entry point `index.py`. The hosted-model adapter uses Vercel's request-scoped OIDC token for server-to-server AI Gateway calls; the credential is not exposed to browser code. The fallback knowledge engine is bundled with the application.

The browser records voice input and sends audio to a server-side transcription route. The older Streamlit prototype and its local model helpers remain in `app/` and `core/`. Optional Supabase migrations and storage code support a synced-workspace configuration.

## Repository structure

- `index.py` — Vercel entry point for the hosted Flask app.
- `webapp/` — hosted Flask routes, AI Gateway adapter, knowledge engine, templates, and browser interface.
- `public/` — static browser assets, favicon, manifest, robots policy, and sitemap.
- `app/` and `core/` — earlier Streamlit interface and local-model helpers.
- `models/` — location for a local GGUF model used by the Streamlit prototype; model weights are not included.
- `supabase/migrations/` — optional synced-workspace database schema.
- `tests/` — automated tests for the hosted application and related integrations.
- `requirements.txt` and `requirements-streamlit.txt` — dependencies for the hosted Flask app and the legacy Streamlit path.

## Status and limitations

The built-in knowledge engine covers selected calculations, translations, and curated entries; it is not a general-purpose language model. Generated answers and transcripts can be inaccurate and should be checked. Chat and voice content is sent to the configured inference/transcription providers when those features are used; do not submit passwords, private records, or other sensitive information. Free model availability and provider limits can change. Supabase workspace syncing and GitHub sign-in depend on the corresponding server-side configuration. The deployed Vercel environment supplies the OIDC credential used for hosted AI Gateway calls; hosted inference anywhere else needs equivalent server-side authentication, and without it the bundled fallback answers the requests it supports. A separate Streamlit prototype in the repository needs a local GGUF model and is unrelated to the hosted site.

## License

MIT. See [LICENSE](LICENSE).
