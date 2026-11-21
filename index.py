"""Vercel entry point for the Zariya Flask web application."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WEBAPP_DIR = ROOT / "webapp"
if str(WEBAPP_DIR) not in sys.path:
    sys.path.insert(0, str(WEBAPP_DIR))

# Hosted inference goes directly to Ollama Cloud. The API key is supplied as a
# Vercel environment variable; no local Ollama daemon is started in Functions.
if os.environ.get("VERCEL"):
    os.environ.setdefault("OLLAMA_BASE_URL", "https://ollama.com")

from webapp.app import app  # noqa: E402
