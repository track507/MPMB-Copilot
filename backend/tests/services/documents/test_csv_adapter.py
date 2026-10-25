import contextlib
import time
from pathlib import Path

import pytest

from app.services.documents import DocumentError, normalize
from app.services.documents.ops.csv import CsvExtractor


def test_each_row_is_one_line_even_when_a_cell_holds_a_newline(tmp_path: Path):
    path = tmp_path / "spells.csv"
    path.write_text('name,level\nFire Bolt,0\n"Shield\nof Faith",1\n', encoding="utf-8")
    result = CsvExtractor().extract(path)
    # ! One row must stay one line, or read and grep lose their place
    assert result.text.splitlines() == ["name | level", "Fire Bolt | 0", "Shield of Faith | 1"]


def test_tsv_splits_on_tabs(tmp_path: Path):
    path = tmp_path / "gear.tsv"
    path.write_text("item\tcost\nRope, hempen\t1 gp\n", encoding="utf-8")
    assert CsvExtractor().extract(path).text.splitlines() == ["item | cost", "Rope, hempen | 1 gp"]


def test_a_semicolon_dialect_is_sniffed(tmp_path: Path):
    path = tmp_path / "eu.csv"
    path.write_text("a;b;c\n1;2;3\n4;5;6\n", encoding="utf-8")
    assert CsvExtractor().extract(path).text.splitlines()[1] == "1 | 2 | 3"


def test_summary_describes_the_table_and_the_outline_is_empty(tmp_path: Path):
    path = tmp_path / "spells.csv"
    path.write_text("name,level\nFire Bolt,0\n", encoding="utf-8")
    result = CsvExtractor().extract(path)
    assert result.summary["rows"] == 2
    assert result.summary["columns"] == 2
    assert result.summary["first_row"] == ["name", "level"]
    # ? A table has no navigable divisions; mpmb_outline must say so rather than look broken
    assert result.outline == []
    assert result.pages_without_text == []


def test_output_is_normalized(tmp_path: Path):
    path = tmp_path / "quotes.csv"
    path.write_text("quote\n\u201cIt\u2019s a trap\u201d\n", encoding="utf-8")
    text = CsvExtractor().extract(path).text
    assert normalize(text) == text
    assert "It's a trap" in text


def test_an_unterminated_quote_is_a_clean_error(tmp_path: Path):
    # ? One stray quote swallows the rest of the file into a single field, which trips the csv field limit
    path = tmp_path / "broken.csv"
    path.write_text('a,"b\n' + "x" * 200_000 + "\n", encoding="utf-8")
    with pytest.raises(DocumentError) as exc:
        CsvExtractor().extract(path)
    assert exc.value.category == "extraction_failed"


def test_the_summary_keeps_a_bounded_preview_of_a_wide_first_row(tmp_path: Path):
    path = tmp_path / "wide.csv"
    path.write_text(",".join("c" * 500 for _ in range(1_000)) + "\n", encoding="utf-8")
    summary = CsvExtractor().extract(path).summary
    assert summary["columns"] == 1_000
    assert len(summary["first_row"]) == 50
    assert all(len(cell) == 200 for cell in summary["first_row"])


def test_sniffing_an_adversarial_sample_is_fast(tmp_path: Path):
    path = tmp_path / "slow.csv"
    path.write_text(',"' * 32_768, encoding="utf-8")
    start = time.perf_counter()
    with contextlib.suppress(DocumentError):
        CsvExtractor().extract(path)
    assert time.perf_counter() - start < 2.0
