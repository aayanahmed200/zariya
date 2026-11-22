import os
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent
MODELS_DIR = ROOT / "models"
DATA_DIR = ROOT / "data"
UI = ROOT / "app" / "ui.py"


def check_model():
    model = MODELS_DIR / "model.gguf"
    if not model.exists() or model.stat().st_size < 1000:
        print("\nWARNING: No model found at models/model.gguf")
        print("The app will start but won't generate responses until a model is placed there.")
        print("See Settings > Model inside the app for instructions.\n")
        return False
    size_gb = model.stat().st_size / (1024**3)
    print(f"Model found: model.gguf ({size_gb:.2f} GB)")
    return True


def check_dependencies():
    missing = []
    for pkg in ["streamlit", "llama_cpp"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)

    if missing:
        print(f"\nMissing packages: {', '.join(missing)}")
        print("Run: pip install streamlit llama-cpp-python\n")

    return len(missing) == 0


def ensure_dirs():
    MODELS_DIR.mkdir(exist_ok=True)
    DATA_DIR.mkdir(exist_ok=True)
    hist = DATA_DIR / "chat_history.json"
    if not hist.exists():
        hist.write_text("[]")


def main():
    print("\nZariya — Offline AI Assistant")
    print("=" * 40)

    ensure_dirs()
    check_dependencies()
    check_model()

    print("Starting...\n")

    cmd = [
        sys.executable, "-m", "streamlit", "run",
        str(UI),
        "--server.headless", "false",
        "--browser.gatherUsageStats", "false",
        "--theme.base", "dark",
        "--theme.backgroundColor", "#0d1117",
        "--theme.secondaryBackgroundColor", "#161b22",
        "--theme.primaryColor", "#58a6ff",
        "--theme.textColor", "#e6edf3",
        "--theme.font", "sans serif",
    ]

    try:
        subprocess.run(cmd, cwd=str(ROOT))
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
