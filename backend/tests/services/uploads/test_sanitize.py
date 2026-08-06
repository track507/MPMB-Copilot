import pytest

from app.services.uploads.errors import UploadError
from app.services.uploads.sanitize import sanitize_filename


@pytest.mark.parametrize("name", ["spells.js", "notes.md", "a.PDF", "config.yaml", "data.json"])
def test_accepts_valid_names(name):
    assert sanitize_filename(name) == name


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("../escape.js", "invalid_filename"),
        ("dir/spells.js", "invalid_filename"),
        ("dir\\spells.js", "invalid_filename"),
        (".hidden.js", "invalid_filename"),
        ("con.txt", "invalid_filename"),
        ("COM3.md", "invalid_filename"),
        ("bad\x00name.js", "invalid_filename"),
        ("x" * 256 + ".js", "invalid_filename"),
        ("script.exe", "extension_not_allowed"),
        ("noext", "extension_not_allowed"),
        ("", "invalid_filename"),
    ],
)
def test_rejects(name, code):
    with pytest.raises(UploadError) as exc:
        sanitize_filename(name)
    assert exc.value.code == code
