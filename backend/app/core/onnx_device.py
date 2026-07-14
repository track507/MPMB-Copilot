"""
ONNX execution-device resolution for local models (embedding, reranking)

Detection is provider-based, not platform-based: whatever GPU-capable onnxruntime is installed decides what "gpu" means (DirectML on Windows, CUDA on Linux)
BM25 is token counting and never routes through this module
"""

# * Preference-ordered GPU execution providers; first available wins
_GPU_PROVIDERS: tuple[tuple[str, str], ...] = (
    ("DmlExecutionProvider", "DirectML"),
    ("CUDAExecutionProvider", "CUDA"),
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


def onnx_providers() -> list[str] | None:
    """
    Ordered EP list for the current settings; None = fastembed's CPU default
    """
    from app.settings import settings

    detected = detect_gpu_provider()
    if settings.inference_device == "gpu" and detected is not None:
        # ! Ordered fallback: a GPU failure degrades to CPU, never breaks a search
        return [detected[0], "CPUExecutionProvider"]
    return None
