import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def test_importing_app_turns_onnxruntime_telemetry_off_before_onnxruntime_loads():
    code = "import os, sys, app; print('onnxruntime' in sys.modules, os.environ.get('ORT_DISABLE_TELEMETRY'))"
    env = {key: value for key, value in os.environ.items() if key != "ORT_DISABLE_TELEMETRY"}
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=BACKEND, env=env, capture_output=True, text=True, check=True
    )
    assert result.stdout.split() == ["False", "1"]
