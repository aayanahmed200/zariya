# Zariya

**Live:** [zariyas.vercel.app](https://zariyas.vercel.app/)

[![Python](https://img.shields.io/badge/python-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/) [![Flask](https://img.shields.io/badge/flask-000000?style=for-the-badge&logo=flask&logoColor=white)](https://flask.palletsprojects.com/) [![JavaScript](https://img.shields.io/badge/JavaScript-F7DF1E?style=for-the-badge&logo=javascript&logoColor=111)](https://developer.mozilla.org/en-US/docs/Web/JavaScript) [![Vercel](https://img.shields.io/badge/vercel-000000?style=for-the-badge&logo=vercel&logoColor=white)](https://vercel.com/) [![Supabase](https://img.shields.io/badge/supabase-3FCF8E?style=for-the-badge&logo=supabase&logoColor=white)](https://supabase.com/)

A bilingual Urdu and English workspace for AI chat, voice typing, notes and flashcards.

## Overview

The workspace combines chat, notepad and flashcard views with quick actions for summaries, key points, translation and flashcard creation. Chat runs on an open-weight language model through Vercel AI Gateway, so visitors do not need to install Ollama or bring an API key, and the app falls back to a built-in knowledge engine when hosted inference is unavailable. Urdu is rendered with a dedicated Noto Sans Arabic typeface, including Urdu phrases embedded in English answers, and response-style presets sit alongside optional custom instructions.

Notes, flashcards and chat history live in the browser, with JSON backup export and restore, and flashcard decks can be edited without resetting their spaced-repetition history. The older Streamlit app remains available for local experimentation with a separate GGUF model workflow.

## How it was made

Zariya started as a local Streamlit and GGUF experiment in `app/` and `core/`, and the hosted product is a Flask rewrite in `webapp/` deployed to Vercel through `index.py`. Chat requests go from the Flask server to Vercel AI Gateway using the short-lived OIDC token Vercel injects into each Function request as `x-vercel-oidc-token`, so no provider key ships to the browser and the model can be changed with an environment variable. The default model is `nvidia/nemotron-3.5-lightning-free`; when it is rate-limited or unavailable, the bundled knowledge engine answers instead.

The composer records microphone audio in the browser and posts a short WAV to a server-side transcription route, which Gateway routes to Microsoft MAI-Transcribe 2 with automatic language detection or explicit English/Urdu selection. That path was chosen over the browser's experimental Web Speech Recognition API. An optional Supabase migration adds synced workspaces, and the tests cover the hosted app, streaming, Gateway integration and SEO, run by a GitHub Actions workflow.

## Highlights

- Bilingual Urdu and English interface with a purpose-set typeface for Urdu.
- Chat on a hosted open-weight model through AI Gateway, with a local knowledge engine as fallback.
- Voice typing through a server-side transcription route rather than the browser speech API.
- Notepad and flashcard views with spaced repetition, inline editing and JSON backup and restore.
- Response-style presets, quick actions, and optional Google Search when enabled.

## Repository contents

- `index.py` — Vercel entry point for the Flask app.
- `webapp/` — Flask routes, hosted AI Gateway adapter, bilingual knowledge engine, templates and browser interface.
- `public/` — favicon, web manifest, robots policy, sitemap and static browser assets.
- `app/` and `core/` — local Streamlit interface and model helpers.
- `supabase/migrations/` — the optional synced-workspace schema.
- `tests/` — automated checks for the hosted app, streaming, Gateway integration and SEO.

## Notes and limitations

Chats, notes and flashcards are stored in the visitor's browser local storage; they are not synced across devices or accounts, and clearing browser storage removes them. Chat message content is transmitted to Vercel AI Gateway and the selected model provider, whose current listing does not claim zero data retention or a no-training guarantee, so passwords, private records and other sensitive information should stay out of chat. Voice recordings are transmitted to Vercel AI Gateway and Microsoft Azure for transcription and are not saved by Zariya. Generated answers and transcripts can be inaccurate and need reviewing before they are relied on. The built-in knowledge engine supports selected calculations, translations and curated entries; it is not a general-purpose language model. Free-model capacity and rate limits can change, and the optional Google Search sends search terms to Google when it is enabled.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for the full text.
