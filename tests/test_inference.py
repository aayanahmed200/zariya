"""
Tests for core/inference.py (InferenceEngine).

A fake llama_cpp module is installed into sys.modules before core.inference
is imported, since the real llama-cpp-python package needs a compiled
extension and an actual GGUF file this test environment doesn't have. The
fake exercises exactly the calling conventions InferenceEngine relies on:
create_chat_completion(), the raw __call__ completion fallback, and both
streaming and non-streaming modes.
"""
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class FakeLlama:
    """Stands in for llama_cpp.Llama."""

    def __init__(self, model_path, n_ctx, n_threads, n_gpu_layers, verbose):
        self.supports_chat_template = True

    def create_chat_completion(self, messages, max_tokens, temperature, top_p,
                                repeat_penalty, stream=False):
        if not self.supports_chat_template:
            raise RuntimeError("this model has no chat template")
        if stream:
            def gen():
                for word in ["Hello", " there", "!"]:
                    yield {"choices": [{"delta": {"content": word}}]}
            return gen()
        return {"choices": [{"message": {"content": "Hello from fake model!"}}]}

    def __call__(self, prompt, max_tokens, stop, temperature, top_p,
                 repeat_penalty, stream=False, echo=False):
        if stream:
            def gen():
                for word in ["Fallback", " token", " stream"]:
                    yield {"choices": [{"text": word}]}
            return gen()
        return {"choices": [{"text": "Fallback completion text"}]}


def _install_fake_llama_cpp():
    fake_module = types.ModuleType("llama_cpp")
    fake_module.Llama = FakeLlama
    sys.modules["llama_cpp"] = fake_module


def _tmp_model_path():
    f = tempfile.NamedTemporaryFile(suffix=".gguf", delete=False)
    f.write(b"fake gguf bytes")
    f.close()
    return Path(f.name)


def test_missing_model_file_gives_clear_error(monkeypatch):
    if "llama_cpp" in sys.modules:
        del sys.modules["llama_cpp"]
    import core.inference as inf
    engine = inf.InferenceEngine(model_path=Path("/nonexistent/model.gguf"))
    assert engine.is_ready is False
    assert "Model not found" in engine.error
    assert engine.chat([{"role": "user", "content": "hi"}]).startswith("Error:")


def test_llama_cpp_not_installed_gives_clear_error():
    # Setting the sys.modules entry to None (rather than deleting it) is the
    # documented way to force `import llama_cpp` to raise ImportError. Just
    # deleting the entry isn't enough when llama-cpp-python is actually
    # installed (as requirements.txt requires) -- the real package would
    # just get re-imported from site-packages and this test would instead
    # exercise the "failed to load an invalid file" path.
    sys.modules["llama_cpp"] = None
    import importlib
    import core.inference as inf
    importlib.reload(inf)
    model_path = _tmp_model_path()
    engine = inf.InferenceEngine(model_path=model_path)
    assert engine.is_ready is False
    assert "llama-cpp-python" in engine.error


def test_chat_via_chat_template_path():
    _install_fake_llama_cpp()
    import importlib
    import core.inference as inf
    importlib.reload(inf)
    engine = inf.InferenceEngine(model_path=_tmp_model_path())
    result = engine.chat([{"role": "user", "content": "hi"}])
    assert result == "Hello from fake model!"


def test_stream_via_chat_template_path():
    _install_fake_llama_cpp()
    import importlib
    import core.inference as inf
    importlib.reload(inf)
    engine = inf.InferenceEngine(model_path=_tmp_model_path())
    tokens = list(engine.stream([{"role": "user", "content": "hi"}]))
    assert tokens == ["Hello", " there", "!"]


def test_chat_falls_back_when_chat_template_unsupported():
    _install_fake_llama_cpp()
    import importlib
    import core.inference as inf
    importlib.reload(inf)
    engine = inf.InferenceEngine(model_path=_tmp_model_path())
    engine._try_load()
    engine._llm.supports_chat_template = False
    result = engine.chat([{"role": "user", "content": "hi"}])
    assert result == "Fallback completion text"


def test_stream_falls_back_when_chat_template_unsupported():
    _install_fake_llama_cpp()
    import importlib
    import core.inference as inf
    importlib.reload(inf)
    engine = inf.InferenceEngine(model_path=_tmp_model_path())
    engine._try_load()
    engine._llm.supports_chat_template = False
    tokens = list(engine.stream([{"role": "user", "content": "hi"}]))
    assert tokens == ["Fallback", " token", " stream"]
