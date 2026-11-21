"""Vercel entry point for the Zariya Flask web application."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WEBAPP_DIR = ROOT / "webapp"
if str(WEBAPP_DIR) not in sys.path:
    sys.path.insert(0, str(WEBAPP_DIR))

# Vercel Functions are request-driven and do not run a persistent local
# Ollama daemon. Keep hosted inference on the bundled knowledge fallback
# unless the deployer configures a supported remote provider.
if os.environ.get("VERCEL"):
    os.environ.setdefault("DISABLE_LOCAL_MODEL", "1")

from webapp.app import app  # noqa: E402
