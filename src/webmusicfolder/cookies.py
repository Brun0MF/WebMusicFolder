"""Store the user's exported cookies.txt for private and age restricted videos.

The file is a credential for the Google account. It is only ever written with mode 0600,
never served back and never logged: errors name a line number, not its content.
"""

from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

# A real YouTube export is a few KB; this only stops absurd input.
MAX_COOKIES_BYTES = 512 * 1024
COOKIES_FILE_NAME = "cookies.txt"
HEADER = "# Netscape HTTP Cookie File"
# Rows for these sites are the ones that carry a YouTube session.
SESSION_DOMAINS = ("youtube.com", "google.com")
# yt-dlp writes HttpOnly cookies with this prefix on the domain.
HTTP_ONLY_PREFIX = "#HttpOnly_"


class CookiesError(ValueError):
    """The submitted text is not a usable cookies.txt; the message is safe to show."""


@dataclass(frozen=True)
class CookiesStatus:
    loaded: bool
    saved_at: str | None = None


def _fields(line: str) -> list[str]:
    if "\t" in line:
        return line.split("\t")
    # Copied from a page, tabs often turn into spaces: accept 7 columns separated by spaces.
    parts = line.split(None, 6)
    return parts if len(parts) >= 6 and parts[1].upper() in ("TRUE", "FALSE") else [line]


def normalise(text: str) -> str:
    """Validate Netscape format and return it with tabs, LF endings and a header.

    Raises CookiesError without echoing any cookie content.
    """
    if "\x00" in text:
        raise CookiesError("The file is not text")
    rows: list[str] = []
    session_rows = 0
    for number, raw in enumerate(text.replace("\r\n", "\n").replace("\r", "\n").split("\n"), 1):
        line = raw.strip("\n")
        if not line.strip():
            continue
        is_http_only = line.startswith(HTTP_ONLY_PREFIX)
        if line.lstrip().startswith("#") and not is_http_only:
            continue
        parts = _fields(line.strip() if "\t" not in line else line)
        if len(parts) not in (6, 7):
            raise CookiesError(
                f"Line {number} is not a Netscape cookie row (7 tab separated columns)"
            )
        domain, include_sub, path, secure, expiry, name = (p.strip() for p in parts[:6])
        value = parts[6] if len(parts) == 7 else ""
        if (
            not domain
            or include_sub.upper() not in ("TRUE", "FALSE")
            or not path.startswith("/")
            or secure.upper() not in ("TRUE", "FALSE")
            or not expiry.isdigit()
            or not name
        ):
            raise CookiesError(f"Line {number} is not a valid cookie row")
        host = domain.removeprefix(HTTP_ONLY_PREFIX).lstrip(".").lower()
        if any(host == d or host.endswith(f".{d}") for d in SESSION_DOMAINS):
            session_rows += 1
        rows.append(
            "\t".join([domain, include_sub.upper(), path, secure.upper(), expiry, name, value])
        )
    if not rows:
        raise CookiesError("No cookies found in the text")
    if not session_rows:
        raise CookiesError(
            "No youtube.com or google.com cookies found; export them while on YouTube"
        )
    return "\n".join([HEADER, *rows]) + "\n"


class CookieStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def status(self) -> CookiesStatus:
        try:
            stamp = self.path.stat().st_mtime
        except OSError:
            return CookiesStatus(loaded=False)
        saved = datetime.fromtimestamp(stamp, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        return CookiesStatus(loaded=True, saved_at=saved)

    def save(self, text: str) -> CookiesStatus:
        """Validate, then replace the stored file atomically with mode 0600."""
        if len(text.encode("utf-8", "replace")) > MAX_COOKIES_BYTES:
            raise CookiesError("The file is too large to be a cookies.txt")
        clean = normalise(text)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f".{self.path.name}.tmp")
        with contextlib.suppress(FileNotFoundError):
            tmp.unlink()
        # O_EXCL plus an explicit mode: the secret is never readable by others, not even briefly.
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(clean)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)
        except BaseException:
            with contextlib.suppress(OSError):
                tmp.unlink()
            raise
        return self.status()

    def delete(self) -> bool:
        try:
            self.path.unlink()
        except FileNotFoundError:
            return False
        return True
