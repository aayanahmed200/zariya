"""Vercel entry point for the Zariya Flask web application."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WEBAPP_DIR = ROOT / "webapp"
if str(WEBAPP_DIR) not in sys.path:
    sys.path.insert(0, str(WEBAPP_DIR))

# Hosted inference uses Vercel AI Gateway. Vercel injects a short-lived
# OIDC credential into each Function request; browser code never sees it.
from webapp.app import app  # noqa: E402
