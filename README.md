# Zariya

[![Python](https://img.shields.io/badge/python-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/) [![Flask](https://img.shields.io/badge/flask-000000?style=for-the-badge&logo=flask&logoColor=white)](https://flask.palletsprojects.com/) [![Ollama](https://img.shields.io/badge/ollama-000000?style=for-the-badge&logo=ollama&logoColor=white)](https://ollama.com/)

Zariya is an offline-first assistant for Urdu and other low-resource languages. Conversations can run locally after a model is downloaded, without depending on a hosted API.

## Overview

The repository contains an actively developed Flask web app and an earlier Streamlit application. The web app uses Ollama for local inference; the original app loads a GGUF model through `llama.cpp`.

## Highlights

- Urdu and English support.
- Local model inference through Ollama in the web app.
- Token-by-token response streaming.
- Offline knowledge-base fallback when a local model is unavailable.
- Optional cloud integrations are configured by the deployer; users do not need to enter provider keys.

## Technology

Python, Flask, Ollama, Streamlit, `llama-cpp-python`, vanilla JavaScript, and CSS.

## Run locally

For the actively developed web app:

```bash
cd webapp
pip install -r requirements.txt
cp .env.example .env
python app.py
```

To run the original Streamlit version from the repository root:

```bash
pip install -r requirements.txt
streamlit run run.py
```

## Notes and limitations

The offline knowledge engine is a curated lookup system, not a full language model, and has gaps outside its stored vocabulary and entries. Local model quality and speed depend on the model and computer. The web app's configuration and tests are documented in `webapp/README.md`.

## Tests

- `pytest tests/` — core tests for the original app.
- `python webapp/test_kb_engine.py` — offline knowledge-engine checks.
- `pytest webapp/test_local_model.py webapp/test_embeddings.py` — local model and semantic-search tests.

## License

MIT — see `LICENSE`.
