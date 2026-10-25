"""MPMB Copilot Backend - FastAPI RAG Engine"""

import os

# ! Before any onnxruntime import: its default-on telemetry spawns a shell and writes a device id at import time
os.environ.setdefault("ORT_DISABLE_TELEMETRY", "1")

__version__ = "0.1.0"
