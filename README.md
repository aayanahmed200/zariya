# Zariya

[![Python](https://img.shields.io/badge/python-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/) [![Flask](https://img.shields.io/badge/flask-000000?style=for-the-badge&logo=flask&logoColor=white)](https://flask.palletsprojects.com/) [![Ollama](https://img.shields.io/badge/ollama-000000?style=for-the-badge&logo=ollama&logoColor=white)](https://ollama.com/)

Zariya is an offline-first assistant for Urdu and other low-resource languages. Conversations can run locally after a model is downloaded, without depending on a hosted API.

## Overview

The repository contains an actively developed Flask web app and an earlier Streamlit application. The web app uses Ollama for local inference and a curated offline knowledge engine as a fallback; the original app loads a GGUF model through `llama.cpp`.

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

Run the tests with `pytest tests/`, `python webapp/test_kb_engine.py`, and `pytest webapp/test_local_model.py webapp/test_embeddings.py`.


## License

MIT — see `LICENSE`.
