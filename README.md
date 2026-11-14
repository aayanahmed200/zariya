# Zariya

[![Python](https://img.shields.io/badge/python-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/) [![Flask](https://img.shields.io/badge/flask-000000?style=for-the-badge&logo=flask&logoColor=white)](https://flask.palletsprojects.com/) [![Ollama](https://img.shields.io/badge/ollama-000000?style=for-the-badge&logo=ollama&logoColor=white)](https://ollama.com/)

Zariya is an offline-first assistant for Urdu and other low-resource languages.

## Overview

The repository contains an actively developed Flask web app and an earlier Streamlit application. The web app uses Ollama for local inference and a curated offline knowledge engine as a fallback. The original app loads a GGUF model through `llama.cpp`.

## Highlights

- Supports Urdu and English.
- Runs local model inference through Ollama in the web app.
- Streams responses token by token.
- Uses an offline knowledge-base fallback when a local model is unavailable.

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

Run the tests with:

```bash
pytest tests/
python webapp/test_kb_engine.py
pytest webapp/test_local_model.py webapp/test_embeddings.py
```

## Notes and limitations

Local model use requires a supported model to be downloaded and configured. The Flask/Ollama web app and the earlier Streamlit app are separate implementations. Optional cloud integrations are configured by the deployer.

## License

MIT — see `LICENSE`.