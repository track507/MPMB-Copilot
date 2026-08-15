"""
A GPU that faults mid-run demotes local inference to CPU instead of failing the batch

Windows resets a GPU whose dispatch outruns the TDR watchdog; onnxruntime surfaces that as DXGI 887A0006 ("The GPU will not respond to more commands") in the middle of a long re-index
"""

import pytest

from app.core import onnx_device
from app.services.embedding.service import EmbeddingService
from app.settings import settings

DEVICE_HUNG = (
    "[ONNXRuntimeError] : 1 : FAIL : DmlCommandRecorder.cpp(371) Exception(1) 887A0006 "
    "The GPU will not respond to more commands"
)


@pytest.fixture(autouse=True)
def _clear_latch():
    onnx_device.reset_cpu_fallback()
    yield
    onnx_device.reset_cpu_fallback()


class _Provider:
    """Fails on the first embed when raising=True, then succeeds"""

    def __init__(self, error: Exception | None):
        self.dimension = 3
        self._error = error
        self.calls = 0

    def embed_texts(self, texts):
        self.calls += 1
        if self._error is not None:
            raise self._error
        return [[0.1, 0.2, 0.3] for _ in texts]


def test_device_failure_markers():
    assert onnx_device.is_device_failure(RuntimeError(DEVICE_HUNG))
    assert onnx_device.is_device_failure(RuntimeError("CUDA error: out of memory"))
    assert not onnx_device.is_device_failure(ValueError("input must not be empty"))


def test_effective_device_honors_latch(monkeypatch):
    monkeypatch.setattr(settings, "inference_device", "gpu")
    assert onnx_device.effective_device() == "gpu"
    assert onnx_device.force_cpu_fallback(DEVICE_HUNG) is True
    assert onnx_device.effective_device() == "cpu"
    assert onnx_device.onnx_providers() is None
    # ! Latching twice would let a caller retry forever
    assert onnx_device.force_cpu_fallback(DEVICE_HUNG) is False


def test_embed_retries_on_cpu_after_device_hang(monkeypatch):
    monkeypatch.setattr(settings, "inference_device", "gpu")
    service = EmbeddingService()
    gpu_provider = _Provider(RuntimeError(DEVICE_HUNG))
    cpu_provider = _Provider(None)
    loaded_on: list[str] = []

    def load_provider():
        device = onnx_device.effective_device()
        loaded_on.append(device)
        return cpu_provider if device == "cpu" else gpu_provider

    monkeypatch.setattr(service, "_load_provider", load_provider)

    vectors = service.embed_texts(["chunk one", "chunk two"])

    assert vectors == [[0.1, 0.2, 0.3], [0.1, 0.2, 0.3]]
    assert loaded_on == ["gpu", "cpu"]  # reloaded once the latch flipped
    assert gpu_provider.calls == 1  # the GPU provider was tried once
    assert cpu_provider.calls == 1  # then the CPU reload served the same batch


def test_non_device_errors_propagate(monkeypatch):
    monkeypatch.setattr(settings, "inference_device", "gpu")
    service = EmbeddingService()
    monkeypatch.setattr(service, "_load_provider", lambda: _Provider(ValueError("bad input")))

    with pytest.raises(ValueError):
        service.embed_texts(["chunk"])

    assert onnx_device.effective_device() == "gpu"  # unrelated failures must not demote the device
