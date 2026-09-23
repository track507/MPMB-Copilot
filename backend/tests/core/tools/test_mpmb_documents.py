"""
The document read path through the tools: read, grep and outline over PDF and CSV uploads

Real temp directories and generated PDFs; only settings and the cache location are redirected
"""

from pathlib import Path

import pytest

from app.config import config
from app.core.tools.mpmb_tools import (
    Deps,
    _mpmb_function_impl,
    _mpmb_grep_impl,
    _mpmb_outline_impl,
    _mpmb_read_impl,
)
from app.services.documents import registry
from app.settings import settings
from tests.services.documents.builders import write_pdf

SESSION = "./data/uploads/session/"
SOURCE = "./data/mpmb_source/"


@pytest.fixture
def roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    monkeypatch.setattr(config, "extracted_dir", str(tmp_path / "extracted"), raising=False)
    monkeypatch.setattr(registry, "_availability", {})
    monkeypatch.setattr(settings, "documents", dict(settings.documents))
    session = tmp_path / "uploads" / "session" / "s1"
    session.mkdir(parents=True)
    source = tmp_path / "mpmb_source"
    source.mkdir()
    return {SESSION: session, SOURCE: source}


@pytest.fixture
def deps() -> Deps:
    return Deps(session_id="s1", edition="2014", user_id="u1")


def test_read_returns_the_extracted_text_with_page_markers(roots, deps):
    write_pdf(roots[SESSION] / "guide.pdf")
    text = _mpmb_read_impl(roots, deps, SESSION, "guide.pdf")
    assert text.startswith("[page 1]\nChapter One: Blood Hunters")
    assert "[page 3]" in text


def test_an_outline_line_is_a_line_read_can_open(roots, deps):
    write_pdf(roots[SESSION] / "guide.pdf")
    outline = _mpmb_outline_impl(roots, deps, SESSION, "guide.pdf")
    chapter_two = next(line for line in outline.splitlines() if line.endswith("Chapter Two"))
    line_number = int(chapter_two.split(":", 1)[0].removeprefix("L"))

    passage = _mpmb_read_impl(roots, deps, SESSION, "guide.pdf", line_number, line_number + 1)

    # ! The outline, grep and read must agree on what a line number means, or navigation lands on the wrong text
    assert passage == "[page 3]\nChapter Two: Grim Hollow"


def test_outline_reports_pages_and_the_pages_ocr_would_need(roots, deps):
    write_pdf(roots[SESSION] / "guide.pdf")
    outline = _mpmb_outline_impl(roots, deps, SESSION, "guide.pdf")
    assert outline.splitlines()[0] == "guide.pdf: 3 pages, 2 outline entries"
    assert "no text layer on pages 2" in outline
    assert "L1: Chapter One" in outline


def test_outline_says_so_when_a_format_has_no_divisions(roots, deps):
    (roots[SESSION] / "spells.csv").write_text("name,level\nFire Bolt,0\n", encoding="utf-8")
    outline = _mpmb_outline_impl(roots, deps, SESSION, "spells.csv")
    assert outline.startswith("spells.csv: 2 rows, 2 columns")
    assert "no navigable divisions" in outline


def test_outline_refuses_plain_text_and_points_at_read(roots, deps):
    (roots[SOURCE] / "Functions0.js").write_text("var a = 1;", encoding="utf-8")
    result = _mpmb_outline_impl(roots, deps, SOURCE, "Functions0.js")
    assert result.startswith("[error]") and "mpmb_read" in result


def test_grep_reports_the_original_path_and_a_line_read_agrees_with(roots, deps):
    write_pdf(roots[SESSION] / "guide.pdf")
    result = _mpmb_grep_impl(roots, deps, SESSION, "Wisdom saving throw")

    hit = result.splitlines()[0]
    # ! The original name, never the sidecar, so the model can pass it straight to mpmb_read
    assert hit.startswith("guide.pdf:")
    line_number = int(hit.split(":")[1])
    assert "Wisdom saving throw" in _mpmb_read_impl(roots, deps, SESSION, "guide.pdf", line_number, line_number)


def test_grep_extracts_the_next_batch_on_each_call(roots, deps, monkeypatch):
    monkeypatch.setitem(settings.documents, "grep_extract_budget", 2)
    for i in range(5):
        write_pdf(roots[SESSION] / f"g{i}.pdf", pages=[[f"needle in g{i}"]], outline=[])

    first = _mpmb_grep_impl(roots, deps, SESSION, "needle")
    second = _mpmb_grep_impl(roots, deps, SESSION, "needle")
    third = _mpmb_grep_impl(roots, deps, SESSION, "needle")

    assert "[extracted 2 of 5 documents this call (3 remaining)" in first
    assert "[extracted 2 of 3 documents this call (1 remaining)" in second
    # ? Each call returns strictly more matches, because earlier batches are now cached
    hits = [sum(1 for line in r.splitlines() if ".pdf:" in line) for r in (first, second, third)]
    assert hits == [2, 4, 5]
    assert "remaining" not in third


def test_grep_never_calls_an_unsearched_document_absent(roots, deps, monkeypatch):
    monkeypatch.setitem(settings.documents, "grep_extract_budget", 0)
    write_pdf(roots[SESSION] / "guide.pdf")
    result = _mpmb_grep_impl(roots, deps, SESSION, "Wisdom")
    # ! "does not occur" would be a false negative when a document was skipped
    assert result.startswith("No matches yet")
    assert "does not occur" not in result


def test_grep_skips_documents_over_its_size_cap_until_opened_explicitly(roots, deps, monkeypatch):
    monkeypatch.setitem(settings.documents, "grep_extract_max_file_bytes", 10)
    write_pdf(roots[SESSION] / "guide.pdf")

    before = _mpmb_grep_impl(roots, deps, SESSION, "Wisdom")
    assert "too large to extract during grep: guide.pdf" in before

    _mpmb_outline_impl(roots, deps, SESSION, "guide.pdf")

    after = _mpmb_grep_impl(roots, deps, SESSION, "Wisdom")
    assert after.startswith("guide.pdf:")


def test_a_document_with_no_text_anywhere_is_refused_with_a_reason(roots, deps):
    write_pdf(roots[SESSION] / "scan.pdf", pages=[[], []], outline=[])
    result = _mpmb_read_impl(roots, deps, SESSION, "scan.pdf")
    assert result.startswith("[error]") and "no text layer" in result and "OCR" in result


def test_an_oversized_extraction_is_refused_for_read_but_still_outlined(roots, deps, monkeypatch):
    monkeypatch.setitem(settings.documents, "max_extracted_bytes", 10)
    write_pdf(roots[SESSION] / "guide.pdf")

    assert "extracts to" in _mpmb_read_impl(roots, deps, SESSION, "guide.pdf")
    # ? An outline stays small even when the text is too large to read whole, which is exactly when it is needed
    assert _mpmb_outline_impl(roots, deps, SESSION, "guide.pdf").startswith("guide.pdf: 3 pages")


def test_function_lookup_ignores_documents(roots, deps):
    # ! mpmb_function scans only **/*.js, which is what keeps sidecars and PDFs out of a symbol lookup
    write_pdf(roots[SOURCE] / "notes.pdf", pages=[["var AbilityScores = {};"]], outline=[])
    (roots[SOURCE] / "Functions0.js").write_text("var Other = 1;", encoding="utf-8")
    assert _mpmb_function_impl(roots, deps, SOURCE, "AbilityScores").startswith("[error]")


def test_source_root_documents_cache_outside_every_user_bucket(roots, deps, tmp_path: Path):
    write_pdf(roots[SOURCE] / "reference.pdf")
    _mpmb_outline_impl(roots, deps, SOURCE, "reference.pdf")
    buckets = {p.name for p in (tmp_path / "extracted").iterdir()}
    assert buckets == {"_source_roots"}
