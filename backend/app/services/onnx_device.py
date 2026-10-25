"""
ONNX execution-device resolution for local models (embedding, reranking)

Detection is provider-based, not platform-based: whatever GPU-capable onnxruntime is installed decides what "gpu" means (DirectML on Windows, CUDA on Linux)
BM25 is token counting and never routes through this module
"""

import threading
from contextlib import AbstractContextManager, nullcontext

from app.logger import get_logger

logger = get_logger(__name__)

_serial_lock = threading.Lock()

# * Preference-ordered GPU execution providers; first available wins
_GPU_PROVIDERS: tuple[tuple[str, str], ...] = (
    ("DmlExecutionProvider", "DirectML"),
    ("CUDAExecutionProvider", "CUDA"),
)

# ! Process-wide latch: a GPU that faulted mid-run stays off until restart, so one hung device cannot fail every later batch
_cpu_fallback_reason: str | None = None

# * Substrings of the driver/runtime errors worth demoting the device for; a device hang reports as DXGI 887A0006 ("GPU will not respond to more commands")
_DEVICE_FAILURE_MARKERS: tuple[str, ...] = (
    "887a0006",
    "887a0005",
    "887a0007",
    "device hung",
    "device removed",
    "dmlexecutionprovider",
    "cudaexecutionprovider",
    "onnxruntimeerror",
    "cuda error",
    "out of memory",
)


def detect_gpu_provider() -> tuple[str, str] | None:
    """
    (execution provider, human label) of the installed GPU runtime, or None
    """
    # ? Detects the RUNTIME capability, not the hardware; a GPU session on a GPU-less machine falls through the ordered provider list at load time
    import onnxruntime

    available = onnxruntime.get_available_providers()
    for provider, label in _GPU_PROVIDERS:
        if provider in available:
            return provider, label
    return None


def effective_device() -> str:
    """
    'gpu' or 'cpu' for the current settings, honoring a runtime fallback
    """
    from app.settings import settings

    if _cpu_fallback_reason is not None:
        return "cpu"
    return settings.inference_device


def runs_serially(device: str) -> bool:
    """
    True when a session built on this device must not run while any other does

    DirectML segfaults or suspends the device on concurrent Run calls, even across sessions; CPU and CUDA do not
    """
    detected = detect_gpu_provider()
    return device == "gpu" and detected is not None and detected[0] == "DmlExecutionProvider"


def inference_slot(device: str) -> AbstractContextManager[object]:
    """Hold around a local ONNX run, passing the device its session was built on"""
    return _serial_lock if runs_serially(device) else nullcontext()


def cpu_fallback_reason() -> str | None:
    return _cpu_fallback_reason


def is_device_failure(exc: BaseException) -> bool:
    """
    True when an exception looks like the execution provider failing rather than bad input
    """
    text = f"{type(exc).__name__}: {exc}".lower()
    return any(marker in text for marker in _DEVICE_FAILURE_MARKERS)


def force_cpu_fallback(reason: str) -> bool:
    """
    Latch every local ONNX model onto CPU for the rest of the process

    Returns False when the fallback was already latched, so callers do not retry forever
    """
    global _cpu_fallback_reason

    if _cpu_fallback_reason is not None:
        return False

    _cpu_fallback_reason = reason
    logger.warning(f"GPU inference failed ({reason}); falling back to CPU for the rest of this process")
    return True


def reset_cpu_fallback() -> None:
    """
    Clear the latch (settings change or test setup)
    """
    global _cpu_fallback_reason

    _cpu_fallback_reason = None


def onnx_providers() -> list[str] | None:
    """
    Ordered EP list for the current settings; None = fastembed's CPU default
    """
    detected = detect_gpu_provider()
    if effective_device() == "gpu" and detected is not None:
        # ! Ordered fallback: a GPU failure degrades to CPU, never breaks a search
        return [detected[0], "CPUExecutionProvider"]
    return None
