import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.services import onnx_device
from app.services.embedding.service import EmbeddingService
from app.services.rerank.service import RerankService


class _Device:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.active = 0
        self.peak = 0

    def run(self, result):
        with self._lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
        time.sleep(0.02)
        with self._lock:
            self.active -= 1
        return result


def _peak(monkeypatch, *, serial: bool) -> int:
    monkeypatch.setattr(onnx_device, "runs_serially", lambda device: serial)
    device = _Device()
    embedder = EmbeddingService()
    monkeypatch.setattr(
        embedder,
        "_ensure_provider",
        lambda: type("P", (), {"embed_texts": lambda self, texts: device.run([[0.0] for _ in texts])})(),
    )
    reranker = RerankService()
    monkeypatch.setattr(
        reranker,
        "_ensure_model",
        lambda: type("M", (), {"rerank": lambda self, query, docs: device.run([0.0] * len(docs))})(),
    )
    calls = [lambda: embedder.embed_texts(["q"]), lambda: reranker.rerank("q", [{"content": "d"}], 1)] * 4
    with ThreadPoolExecutor(4) as pool:
        list(pool.map(lambda call: call(), calls))
    return device.peak


def test_directml_never_runs_two_inferences_at_once_across_models(monkeypatch):
    assert _peak(monkeypatch, serial=True) == 1


def test_other_providers_run_in_parallel(monkeypatch):
    assert _peak(monkeypatch, serial=False) > 1


@pytest.mark.parametrize(
    ("detected", "device", "expected"),
    [
        (("DmlExecutionProvider", "DirectML"), "gpu", True),
        (("DmlExecutionProvider", "DirectML"), "cpu", False),
        (("CUDAExecutionProvider", "CUDA"), "gpu", False),
        (None, "gpu", False),
    ],
)
def test_only_directml_on_the_gpu_runs_serially(monkeypatch, detected, device, expected):
    monkeypatch.setattr(onnx_device, "detect_gpu_provider", lambda: detected)

    assert onnx_device.runs_serially(device) is expected


@pytest.mark.parametrize(
    ("selection", "device"), [(("openai", "m", "gpu"), "remote"), (("fastembed", "m", "gpu"), "gpu")]
)
def test_a_remote_embedder_never_takes_the_local_inference_slot(selection, device):
    service = EmbeddingService()
    service._selection = selection

    assert service._onnx_device() == device
