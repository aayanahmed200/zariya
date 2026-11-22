"""Tests for core/model_downloader.py."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import core.model_downloader as md


def test_validate_url_requires_https():
    assert md.validate_url("http://example.com/model.gguf") is not None
    assert md.validate_url("ftp://example.com/model.gguf") is not None
    assert md.validate_url("not a url") is not None


def test_validate_url_accepts_https():
    assert md.validate_url("https://example.com/model.gguf") is None


def test_validate_url_rejects_missing_host():
    assert md.validate_url("https://") is not None


def _mock_response(content: bytes):
    resp = MagicMock()
    resp.headers = {"content-length": str(len(content))}
    resp.iter_content = lambda chunk_size: [content]
    resp.raise_for_status = lambda: None
    resp.__enter__ = lambda self: resp
    resp.__exit__ = lambda *a: None
    return resp


def test_successful_download(tmp_path):
    dest = tmp_path / "model.gguf"
    content = b"X" * 2_000_000  # 2MB, over the size-sanity threshold
    progress_calls = []
    with patch("requests.get", return_value=_mock_response(content)):
        result = md.download_model(
            "https://example.com/model.gguf",
            dest=dest,
            progress_callback=lambda d, t: progress_calls.append((d, t)),
        )
    assert result == dest
    assert dest.read_bytes() == content
    assert not dest.with_suffix(".part").exists()
    assert progress_calls == [(2_000_000, 2_000_000)]


def test_too_small_file_is_rejected_and_cleaned_up(tmp_path):
    dest = tmp_path / "model.gguf"
    content = b"X" * 100  # well under the 1MB sanity threshold
    with patch("requests.get", return_value=_mock_response(content)):
        try:
            md.download_model("https://example.com/model.gguf", dest=dest)
            assert False, "expected DownloadError"
        except md.DownloadError:
            pass
    assert not dest.exists()
    assert not dest.with_suffix(".part").exists()


def test_network_failure_cleans_up_temp_file(tmp_path):
    dest = tmp_path / "model.gguf"
    resp = MagicMock()
    resp.raise_for_status.side_effect = Exception("connection reset")
    resp.__enter__ = lambda self: resp
    resp.__exit__ = lambda *a: None
    with patch("requests.get", return_value=resp):
        try:
            md.download_model("https://example.com/model.gguf", dest=dest)
            assert False, "expected DownloadError"
        except md.DownloadError:
            pass
    assert not dest.with_suffix(".part").exists()
