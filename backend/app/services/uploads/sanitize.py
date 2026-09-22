import re
from pathlib import PurePosixPath

from app.services.documents import EXTRACTABLE_EXTENSIONS
from app.services.uploads.errors import UploadError

# ! A document format is uploadable only while an adapter can read it, so the set is derived rather than listed
# ? Storing a format nothing reads leaves the user an unreadable file, which is worse than a legible refusal
UPLOAD_EXTENSIONS: frozenset[str] = frozenset({".js", ".txt", ".md", ".yml", ".yaml", ".json"}) | EXTRACTABLE_EXTENSIONS

_WINDOWS_RESERVED = frozenset(
    {"con", "prn", "aux", "nul"} | {f"com{i}" for i in range(1, 10)} | {f"lpt{i}" for i in range(1, 10)}
)
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def sanitize_filename(name: str) -> str:
    """Validate a client-supplied filename; returns it unchanged or raises UploadError."""
    cleaned = name.strip()
    if not cleaned:
        raise UploadError(400, "invalid_filename", "Filename is empty")
    if "/" in cleaned or "\\" in cleaned:
        raise UploadError(400, "invalid_filename", "Filename must not contain path separators")
    if cleaned.startswith("."):
        raise UploadError(400, "invalid_filename", "Hidden filenames are not allowed")
    if _CONTROL_CHARS.search(cleaned):
        raise UploadError(400, "invalid_filename", "Filename contains control characters")
    if len(cleaned) > 255:
        raise UploadError(400, "invalid_filename", "Filename is longer than 255 characters")

    path = PurePosixPath(cleaned)
    if path.stem.lower() in _WINDOWS_RESERVED:
        raise UploadError(400, "invalid_filename", f"'{path.stem}' is a reserved name on Windows")
    ext = path.suffix.lower()
    if ext not in UPLOAD_EXTENSIONS:
        raise UploadError(400, "extension_not_allowed", f"Extension not allowed: {ext or '(none)'}")
    return cleaned
