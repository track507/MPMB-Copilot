"""
The OCR job, its persisted progress, and the reader that queues it
"""

from pathlib import Path

import pytest

from app.config import config
from app.services.documents import ocr_job, registry, service
from app.services.documents.errors import DocumentError
from app.services.documents.ocr_job import OcrAwareReader, OcrProgress
from app.services.documents.protocol import CacheScope
from tests.services.documents.builders import FULL_PAGE_IMAGE, write_pdf

TENANT = "t1"
SCOPE = CacheScope.shared(TENANT)


class _Fake:
    id = "fake"
    version = "1"

    def __init__(self, text: str = "recovered words", fail: bool = False) -> None:
        self._text = text
        self._fail = fail
        self.calls = 0

    def check_availability(self):
        return None

    def transcribe(self, image: bytes) -> str:
        self.calls += 1
        if self._fail:
            raise RuntimeError("engine crashed")
        return self._text


@pytest.fixture(autouse=True)
def _extracted_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "extracted_dir", str(tmp_path / "extracted"), raising=False)


def _use(monkeypatch, transcriber):
    monkeypatch.setattr(registry, "configured_transcriber", lambda: transcriber)


def _upload(name: str = "scan.pdf", **pdf) -> Path:
    path = Path(config.tenants_dir) / TENANT / "library" / name
    pdf.setdefault("pages", [[]])
    pdf.setdefault("outline", [])
    pdf.setdefault("images", FULL_PAGE_IMAGE)
    return write_pdf(path, **pdf)


def _job_for(path: Path):
    storage_key = path.resolve().relative_to(Path(config.data_dir).resolve()).as_posix()
    return ocr_job.job_for(TENANT, storage_key, SCOPE, service.file_hash(path), ".pdf")


def test_progress_survives_a_restart():
    ocr_job.write_progress(SCOPE, "a" * 64, OcrProgress(attempts=2))
    assert ocr_job.read_progress(SCOPE, "a" * 64).attempts == 2


def test_missing_or_corrupt_progress_reads_as_fresh():
    assert ocr_job.read_progress(SCOPE, "b" * 64) == OcrProgress()
    ocr_job.write_progress(SCOPE, "c" * 64, OcrProgress())
    ocr_job._progress_path(SCOPE, "c" * 64).write_text("not json", encoding="utf-8")
    assert ocr_job.read_progress(SCOPE, "c" * 64) == OcrProgress()


def test_the_ceiling_and_a_stall_stop_further_runs():
    assert ocr_job.should_run(OcrProgress(attempts=2)) is True
    assert ocr_job.should_run(OcrProgress(attempts=3)) is False
    assert ocr_job.should_run(OcrProgress(attempts=1, stalled=True)) is False


def test_run_caches_the_transcription_under_the_ocr_version(monkeypatch):
    _use(monkeypatch, _Fake())
    path = _upload()
    ocr_job.run(_job_for(path))
    document = service.ensure_extracted(path, SCOPE)
    assert document.pages_without_text == []
    assert "recovered words" in document.text_path.read_text(encoding="utf-8")
    assert not ocr_job._progress_path(SCOPE, service.file_hash(path)).exists()


def test_a_text_pdf_is_never_transcribed(monkeypatch):
    fake = _Fake()
    _use(monkeypatch, fake)
    path = _upload("text.pdf", pages=[["Chapter One"]], images=None)
    ocr_job.run(_job_for(path))
    assert fake.calls == 0
    assert ocr_job.read_progress(SCOPE, service.file_hash(path)).attempts == 0


def test_a_failing_engine_stalls_at_the_ceiling(monkeypatch):
    fake = _Fake(fail=True)
    _use(monkeypatch, fake)
    path = _upload()
    job = _job_for(path)
    for _ in range(ocr_job.MAX_ATTEMPTS):
        with pytest.raises(DocumentError):
            ocr_job.run(job)
    progress = ocr_job.read_progress(SCOPE, service.file_hash(path))
    assert progress.attempts == ocr_job.MAX_ATTEMPTS
    assert progress.stalled is True
    ocr_job.run(job)
    assert fake.calls == ocr_job.MAX_ATTEMPTS


def test_a_replaced_file_makes_the_job_stale(monkeypatch):
    fake = _Fake()
    _use(monkeypatch, fake)
    path = _upload()
    job = _job_for(path)
    write_pdf(path, pages=[["different bytes"]], outline=[])
    ocr_job.run(job)
    assert fake.calls == 0


def test_a_key_outside_the_tenants_tree_is_refused(monkeypatch):
    fake = _Fake()
    _use(monkeypatch, fake)
    job = _job_for(_upload())
    escaped = type(job)(job.kind, job.tenant_id, {**job.payload, "storage_key": "../../outside.pdf"}, job.key)
    ocr_job.run(escaped)
    assert fake.calls == 0


def test_an_unusable_engine_is_recorded_without_spending_an_attempt(monkeypatch):
    class _Broken(_Fake):
        def check_availability(self):
            return "models missing"

    _use(monkeypatch, _Broken())
    path = _upload()
    ocr_job.run(_job_for(path))
    progress = ocr_job.read_progress(SCOPE, service.file_hash(path))
    assert progress.attempts == 0
    assert progress.unavailable == "models missing"


def test_the_job_key_names_tenant_scope_hash_and_fingerprint(monkeypatch):
    _use(monkeypatch, _Fake())
    path = _upload()
    job = _job_for(path)
    digest = service.file_hash(path)
    fingerprint = registry.candidate_versions(".pdf")[0]
    assert job.key == f"ocr:{TENANT}:shared:{TENANT}:{digest}:{fingerprint}"


def test_no_job_for_a_non_pdf_a_pack_file_or_ocr_off(monkeypatch):
    _use(monkeypatch, _Fake())
    assert ocr_job.job_for(TENANT, "k", SCOPE, "d" * 64, ".csv") is None
    assert ocr_job.job_for(TENANT, "k", CacheScope.for_source_root("mpmb"), "d" * 64, ".pdf") is None
    _use(monkeypatch, None)
    assert ocr_job.job_for(TENANT, "k", SCOPE, "d" * 64, ".pdf") is None


def test_the_reader_queues_a_scan_and_reports_it_pending(monkeypatch):
    _use(monkeypatch, _Fake())
    queued = []
    reader = OcrAwareReader(service, submit=queued.append)
    document = reader.ensure_extracted(_upload(), SCOPE)
    assert document.summary["ocr"] == "pending"
    assert [job.kind for job in queued] == ["ocr"]


def test_the_reader_leaves_a_text_pdf_alone(monkeypatch):
    _use(monkeypatch, _Fake())
    queued = []
    reader = OcrAwareReader(service, submit=queued.append)
    document = reader.ensure_extracted(_upload("text.pdf", pages=[["Chapter One"]], images=None), SCOPE)
    assert "ocr" not in document.summary
    assert queued == []


def test_the_reader_reports_done_when_ocr_left_pages_unreadable(monkeypatch):
    _use(monkeypatch, _Fake(text=""))
    path = _upload()
    ocr_job.run(_job_for(path))
    queued = []
    document = OcrAwareReader(service, submit=queued.append).ensure_extracted(path, SCOPE)
    assert document.summary["ocr"] == "done"
    assert queued == []


def test_the_reader_reports_stalled_without_requeueing(monkeypatch):
    _use(monkeypatch, _Fake())
    path = _upload()
    ocr_job.write_progress(SCOPE, service.file_hash(path), OcrProgress(attempts=3, stalled=True))
    queued = []
    document = OcrAwareReader(service, submit=queued.append).ensure_extracted(path, SCOPE)
    assert document.summary["ocr"] == "stalled"
    assert queued == []


def test_the_reader_reports_off_when_ocr_is_disabled(monkeypatch):
    _use(monkeypatch, None)
    queued = []
    document = OcrAwareReader(service, submit=queued.append).ensure_extracted(_upload(), SCOPE)
    assert document.summary["ocr"] == "off"
    assert queued == []
