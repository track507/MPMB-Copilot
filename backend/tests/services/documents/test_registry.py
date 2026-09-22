from pathlib import Path
from typing import Optional

import pytest

from app.services.documents import Extraction, registry
from app.services.documents.ops import csv as csv_ops
from app.services.documents.ops import pdf as pdf_ops
from app.settings import settings


def test_extractable_set_is_exactly_what_the_adapters_declare():
    # ! The allowlists derive from this set, so a format listed here without an adapter would be a dead end
    assert registry.EXTRACTABLE_EXTENSIONS == pdf_ops.EXTENSIONS | csv_ops.EXTENSIONS


@pytest.mark.parametrize("extension", sorted(registry.EXTRACTABLE_EXTENSIONS))
def test_every_extractable_extension_resolves_to_an_adapter_that_claims_it(extension: str):
    extractor = registry.extractor_for(extension)
    assert extractor is not None
    assert extension in extractor.extensions
    assert registry.extractor_id(extension) is not None


def test_an_unknown_extension_has_no_adapter_and_says_why():
    assert registry.extractor_for(".docx") is None
    assert registry.availability(".docx") == "no reader for .docx files"


def test_extension_matching_ignores_case():
    assert registry.is_extractable(".PDF")
    assert registry.extractor_id(".Csv") == "csv"


class _ProbeCounter:
    extensions = frozenset({".pdf"})
    version = "1"

    def __init__(self) -> None:
        self.probes = 0

    def check_availability(self) -> Optional[str]:
        self.probes += 1
        return None

    def extract(self, path: Path) -> Extraction:
        raise AssertionError("not called by availability")


def test_availability_is_cached_and_reprobes_when_a_documents_setting_changes(monkeypatch: pytest.MonkeyPatch):
    probe = _ProbeCounter()
    monkeypatch.setitem(registry._extractors, ".pdf", probe)
    monkeypatch.setattr(registry, "_availability", {})
    monkeypatch.setattr(settings, "documents", {"libreoffice_enabled": False})

    registry.availability(".pdf")
    registry.availability(".pdf")
    assert probe.probes == 1

    # ? Keyed on the settings value, so toggling one re-probes at once without any reload hook
    monkeypatch.setattr(settings, "documents", {"libreoffice_enabled": True})
    registry.availability(".pdf")
    assert probe.probes == 2
