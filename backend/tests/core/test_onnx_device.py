"""
Device detection: provider-based, ordered, honest about absent runtimes
"""

import onnxruntime

from app.core.onnx_device import detect_gpu_provider, onnx_providers
from app.settings import settings

DML = "DmlExecutionProvider"
CUDA = "CUDAExecutionProvider"
CPU = "CPUExecutionProvider"


def _providers(monkeypatch, available: list[str]) -> None:
    monkeypatch.setattr(onnxruntime, "get_available_providers", lambda: available)


def test_detects_directml(monkeypatch):
    _providers(monkeypatch, [DML, CPU])
    assert detect_gpu_provider() == (DML, "DirectML")


def test_detects_cuda(monkeypatch):
    _providers(monkeypatch, [CUDA, CPU])
    assert detect_gpu_provider() == (CUDA, "CUDA")


def test_cpu_only_runtime_detects_nothing(monkeypatch):
    _providers(monkeypatch, ["AzureExecutionProvider", CPU])
    assert detect_gpu_provider() is None


def test_gpu_setting_with_runtime_yields_ordered_fallback(monkeypatch):
    _providers(monkeypatch, [DML, CPU])
    monkeypatch.setattr(settings, "inference_device", "gpu")
    assert onnx_providers() == [DML, CPU]


def test_cpu_setting_yields_default(monkeypatch):
    _providers(monkeypatch, [DML, CPU])
    monkeypatch.setattr(settings, "inference_device", "cpu")
    assert onnx_providers() is None


def test_gpu_setting_without_runtime_yields_default(monkeypatch):
    _providers(monkeypatch, [CPU])
    monkeypatch.setattr(settings, "inference_device", "gpu")
    assert onnx_providers() is None
