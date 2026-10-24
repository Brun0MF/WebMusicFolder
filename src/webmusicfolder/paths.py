"""Safe path helpers: name sanitising, subfolder validation and music dir boundary checks."""

from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path

MAX_SUBFOLDER_LEN = 80
# Most filesystems cap a name at 255 bytes; leave room for " [id]" and the extension.
MAX_NAME_BYTES = 200
FALLBACK_NAME = "untitled"

_FORBIDDEN_CHARS = re.compile(r'[\x00-\x1f\x7f<>:"/\\|?*]')
_WHITESPACE = re.compile(r"\s+")
_WINDOWS_RESERVED = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


class PathError(ValueError):
    """A name or path is not acceptable."""


def _truncate_bytes(text: str, limit: int) -> str:
    """Cut text to at most limit UTF-8 bytes without splitting a character."""
    return text.encode("utf-8")[:limit].decode("utf-8", errors="ignore")


def sanitize_name(raw: str, max_bytes: int = MAX_NAME_BYTES) -> str:
    """Turn a title into a safe single path component (no extension)."""
    name = unicodedata.normalize("NFC", raw)
    name = _FORBIDDEN_CHARS.sub(" ", name)
    name = _WHITESPACE.sub(" ", name).strip(" .")
    name = _truncate_bytes(name, max_bytes).strip(" .")
    if not name:
        return FALLBACK_NAME
    if name.split(".")[0].lower() in _WINDOWS_RESERVED:
        name = f"_{name}"
    return name


def validate_subfolder(raw: str) -> str:
    """Return the cleaned subfolder name, '' for the music dir root.

    Rejects separators, dot segments, a leading dot, control characters and long names.
    """
    name = raw.strip()
    if not name:
        return ""
    if len(name) > MAX_SUBFOLDER_LEN:
        raise PathError(f"subfolder name is longer than {MAX_SUBFOLDER_LEN} characters")
    if "/" in name or "\\" in name:
        raise PathError("subfolder name cannot contain path separators")
    if name.startswith("."):
        raise PathError("subfolder name cannot start with a dot")
    if any(ord(c) < 32 or ord(c) == 127 for c in name):
        raise PathError("subfolder name cannot contain control characters")
    if name != name.rstrip(" ."):
        raise PathError("subfolder name cannot end with a space or dot")
    return name


def resolve_inside(base: Path, *parts: str) -> Path:
    """Join parts under base and ensure the fully resolved result stays inside base.

    Symlinks are resolved, so one pointing outside the base is rejected.
    """
    root = base.resolve()
    target = root.joinpath(*parts).resolve()
    if target != root and not target.is_relative_to(root):
        raise PathError("path escapes the music directory")
    return target


def list_subfolders(music_dir: Path) -> list[str]:
    """Names of real, non hidden, first level directories inside the music dir."""
    try:
        entries = list(os.scandir(music_dir))
    except FileNotFoundError:
        return []
    names = []
    for entry in entries:
        if entry.name.startswith(".") or entry.is_symlink() or not entry.is_dir():
            continue
        try:
            validate_subfolder(entry.name)
        except PathError:
            continue
        names.append(entry.name)
    return sorted(names, key=str.casefold)


def choose_filename(directory: Path, title: str, video_id: str, owned: bool = False) -> str:
    """Pick the mp3 file name for a title inside directory.

    The plain sanitised title is used when free. On collision with a different
    video, ' [<id>]' is appended. `owned` means the existing plain file belongs to
    this same video (redownload), so it is reused.
    """
    base = sanitize_name(title)
    plain = f"{base}.mp3"
    if owned or not (directory / plain).exists():
        return plain
    suffix = f" [{video_id}]"
    trimmed = _truncate_bytes(base, MAX_NAME_BYTES - len(suffix.encode())).rstrip(" .")
    return f"{trimmed}{suffix}.mp3"
