from __future__ import annotations
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

MODELS_DIR = Path(__file__).parent.parent / "models"
DEST_PATH = MODELS_DIR / "model.gguf"

# A short list of well-known quantized GGUF models that run reasonably on
# consumer hardware. These are convenience presets only - any direct .gguf
# URL can be downloaded via the "Custom URL" option in Settings.
RECOMMENDED_MODELS = [
    {
        "label": "Phi-3 Mini (fastest, ~2.2 GB)",
        "url": "https://huggingface.co/microsoft/Phi-3-mini-4k-instruct-gguf/resolve/main/Phi-3-mini-4k-instruct-q4.gguf?download=true",
        "size_gb": 2.2,
    },
    {
        "label": "Mistral 7B Instruct (~4.4 GB)",
        "url": "https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.2-GGUF/resolve/main/mistral-7b-instruct-v0.2.Q4_K_M.gguf?download=true",
        "size_gb": 4.4,
    },
    {
        "label": "Llama 3 8B Instruct (~4.9 GB)",
        "url": "https://huggingface.co/QuantFactory/Meta-Llama-3-8B-Instruct-GGUF/resolve/main/Meta-Llama-3-8B-Instruct.Q4_K_M.gguf?download=true",
        "size_gb": 4.9,
    },
]


class DownloadError(Exception):
    pass


def validate_url(url: str) -> Optional[str]:
    """Returns an error message if the URL looks unsafe/invalid, else None."""
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return "URL must start with https://"
    if not parsed.netloc:
        return "That doesn't look like a valid URL."
    return None


def download_model(
    url: str,
    dest: Path = DEST_PATH,
    progress_callback: Optional[Callable[[int, Optional[int]], None]] = None,
    chunk_size: int = 1024 * 1024,
) -> Path:
    """Streams a GGUF file to disk, writing to a temp file first so a failed
    or cancelled download never leaves a corrupt model.gguf in place.

    progress_callback(bytes_downloaded, total_bytes_or_none) is called after
    each chunk if provided.
    """
    err = validate_url(url)
    if err:
        raise DownloadError(err)

    try:
        import requests
    except ImportError as e:
        raise DownloadError(
            "`requests` is not installed. Run: pip install requests"
        ) from e

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = dest.with_suffix(".part")

    try:
        with requests.get(url, stream=True, timeout=30) as resp:
            resp.raise_for_status()
            total = resp.headers.get("content-length")
            total = int(total) if total is not None else None

            downloaded = 0
            with open(tmp_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=chunk_size):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback:
                        progress_callback(downloaded, total)

        if downloaded < 1_000_000:
            tmp_path.unlink(missing_ok=True)
            raise DownloadError(
                "Downloaded file is too small to be a real model - the URL "
                "may be wrong or require authentication."
            )

        tmp_path.replace(dest)
        return dest

    except DownloadError:
        raise
    except Exception as e:
        tmp_path.unlink(missing_ok=True)
        raise DownloadError(f"Download failed: {e}") from e
