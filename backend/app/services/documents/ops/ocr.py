"""RapidOCR page transcription"""

from typing import Any, Optional

from app.logger import get_logger

logger = get_logger(__name__)

ID = "rapidocr"
VERSION = "1"


class RapidOcrTranscriber:
    id = ID
    version = VERSION

    def __init__(self) -> None:
        self._engine: Optional[Any] = None

    def check_availability(self) -> Optional[str]:
        try:
            self._ensure_engine()
        except Exception as e:
            return f"OCR is unavailable ({e})"
        return None

    def _ensure_engine(self) -> Any:
        if self._engine is None:
            from rapidocr_onnxruntime import RapidOCR

            self._engine = RapidOCR()
        return self._engine

    def transcribe(self, image: bytes) -> str:
        import io

        import numpy as np
        from PIL import Image

        engine = self._ensure_engine()
        array = np.array(Image.open(io.BytesIO(image)).convert("RGB"))
        result, _ = engine(array)
        if not result:
            return ""
        return "\n".join(str(line[1]) for line in result if len(line) > 1)
