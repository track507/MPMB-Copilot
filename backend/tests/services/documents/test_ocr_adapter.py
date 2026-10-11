"""
The OCR adapter's contract, without running a model
"""

from app.services.documents.ops.ocr import RapidOcrTranscriber


def test_unavailable_engine_reports_a_reason_rather_than_raising(monkeypatch):
    t = RapidOcrTranscriber()

    def boom():
        raise RuntimeError("models not found")

    monkeypatch.setattr(t, "_ensure_engine", boom)
    reason = t.check_availability()
    assert reason is not None
    assert "models not found" in reason


def test_identity_is_stable():
    assert RapidOcrTranscriber().id == "rapidocr"
    assert RapidOcrTranscriber().version == "1"
