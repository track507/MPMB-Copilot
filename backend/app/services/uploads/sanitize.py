import unicodedata
from pathlib import PurePosixPath

from app.core.storage_keys import RESERVED_NAMES
from app.services.documents import EXTRACTABLE_EXTENSIONS
from app.services.uploads.errors import UploadError

# ! A document format is uploadable only while an adapter can read it, so the set is derived rather than listed
# ? Storing a format nothing reads leaves the user an unreadable file, which is worse than a legible refusal
UPLOAD_EXTENSIONS: frozenset[str] = frozenset({".js", ".txt", ".md", ".yml", ".yaml", ".json"}) | EXTRACTABLE_EXTENSIONS

_WINDOWS_RESERVED = frozenset(
    {"con", "prn", "aux", "nul"} | {f"com{i}" for i in range(1, 10)} | {f"lpt{i}" for i in range(1, 10)}
)
# ! Control, format and line or paragraph separator characters change how a name displays without changing what it is
_INVISIBLE_CATEGORIES = frozenset({"Cc", "Cf", "Zl", "Zp"})
_LOOKALIKE_SEPARATORS = frozenset({"\uff0f", "\uff3c"})


def sanitize_filename(name: str) -> str:
    """Validate a client-supplied filename; returns it unchanged or raises UploadError"""
    cleaned = name.strip()
    if not cleaned:
        raise UploadError(400, "invalid_filename", "Filename is empty")
    if "/" in cleaned or "\\" in cleaned or any(ch in _LOOKALIKE_SEPARATORS for ch in cleaned):
        raise UploadError(400, "invalid_filename", "Filename must not contain path separators")
    # ! On Windows ':' makes a drive-relative path or names an NTFS stream, and either redirects the write
    if ":" in cleaned:
        raise UploadError(400, "invalid_filename", "Filename must not contain ':'")
    if cleaned.startswith("."):
        raise UploadError(400, "invalid_filename", "Hidden filenames are not allowed")
    if any(unicodedata.category(ch) in _INVISIBLE_CATEGORIES for ch in cleaned):
        raise UploadError(400, "invalid_filename", "Filename contains control or formatting characters")
    if len(cleaned) > 255:
        raise UploadError(400, "invalid_filename", "Filename is longer than 255 characters")

    if cleaned.lower() in RESERVED_NAMES:
        raise UploadError(400, "invalid_filename", f"'{cleaned}' is reserved for storage metadata")

    path = PurePosixPath(cleaned)
    if path.stem.lower() in _WINDOWS_RESERVED:
        raise UploadError(400, "invalid_filename", f"'{path.stem}' is a reserved name on Windows")
    ext = path.suffix.lower()
    if ext not in UPLOAD_EXTENSIONS:
        raise UploadError(400, "extension_not_allowed", f"Extension not allowed: {ext or '(none)'}")
    return cleaned
