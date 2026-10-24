"""yt-dlp log lines: an in-memory ring buffer and a size capped rotating file."""

from __future__ import annotations

import logging
import re
import threading
import time
from collections import deque
from collections.abc import Callable, Iterable
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

BUFFER_LINES = 1000
# 3 files of at most 5 MB: the live file plus two rotated copies.
MAX_FILE_BYTES = 5 * 1024 * 1024
BACKUP_FILES = 2
# One yt-dlp line can be huge (a dumped JSON); the UI and the file never need all of it.
MAX_LINE_CHARS = 2000
LOG_FILE_NAME = "ytdlp.log"

LogSink = Callable[[str, dict[str, Any]], None]

REDACTED = "[redacted]"
# Literal secrets shorter than this would mangle ordinary words in the log.
MIN_SECRET_CHARS = 4

# Header style and key=value style credentials; the value runs to the end of the token or line.
_COOKIE_HEADER = re.compile(r"(?i)\b((?:set-)?cookie)(\s*[:=]\s*).*")
_AUTH_HEADER = re.compile(r"(?i)\b(authorization)(\s*[:=]\s*)(?:bearer\s+|basic\s+)?\S+")
_KEY_VALUE = re.compile(
    r"(?i)\b(password|passwd|token|secret|api[_-]?key|sapisid|apisid|ssid|hsid|sid"
    r"|login_info|__secure-[\w-]+)(\s*[=:]\s*)[^\s&;,\"']+"
)
# Netscape cookie jar row: domain, flag, path, secure, expiry, name, value separated by tabs.
_JAR_ROW = re.compile(r"^\S+\t(?:TRUE|FALSE)\t\S*\t(?:TRUE|FALSE)\t\d+\t[^\t]*\t.*$")


class Redactor:
    """Strips credentials from text before it is stored, written or sent to a browser."""

    def __init__(self, secrets: Iterable[str] = ()) -> None:
        # Longest first so a path is replaced before any shorter secret inside it.
        self._secrets = sorted(
            {s for s in secrets if len(s) >= MIN_SECRET_CHARS}, key=len, reverse=True
        )

    def __call__(self, text: str) -> str:
        if _JAR_ROW.match(text):
            return f"{REDACTED} cookie row"
        for secret in self._secrets:
            text = text.replace(secret, REDACTED)
        text = _COOKIE_HEADER.sub(rf"\1\2{REDACTED}", text)
        text = _AUTH_HEADER.sub(rf"\1\2{REDACTED}", text)
        return _KEY_VALUE.sub(rf"\1\2{REDACTED}", text)


class LogBuffer:
    """Thread safe: the runner callbacks may arrive from any thread."""

    def __init__(
        self,
        log_dir: Path | None = None,
        sink: LogSink | None = None,
        capacity: int = BUFFER_LINES,
        max_bytes: int = MAX_FILE_BYTES,
        backups: int = BACKUP_FILES,
        redact: Callable[[str], str] | None = None,
    ) -> None:
        self._redact = redact or Redactor()
        self._entries: deque[dict[str, Any]] = deque(maxlen=capacity)
        self._lock = threading.Lock()
        self._seq = 0
        self._sink = sink
        self._handler: RotatingFileHandler | None = None
        if log_dir is not None:
            log_dir.mkdir(parents=True, exist_ok=True)
            self._handler = RotatingFileHandler(
                log_dir / LOG_FILE_NAME,
                maxBytes=max_bytes,
                backupCount=backups,
                encoding="utf-8",
            )

    def add(self, line: str, item_id: str | None = None, title: str | None = None) -> None:
        # Redact before truncating so a secret cut in half cannot slip through.
        text = self._redact(line.rstrip())[:MAX_LINE_CHARS]
        if not text:
            return
        with self._lock:
            self._seq += 1
            entry = {
                "seq": self._seq,
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "item": item_id,
                "title": title,
                "line": text,
            }
            self._entries.append(entry)
            self._write(entry)
        if self._sink is not None:
            self._sink("log", dict(entry))

    def _write(self, entry: dict[str, Any]) -> None:
        if self._handler is None:
            return
        who = entry["title"] or entry["item"] or "app"
        record = logging.makeLogRecord(
            {"msg": f"{entry['ts']} [{who}] {entry['line']}", "levelno": logging.INFO}
        )
        try:
            self._handler.emit(record)
        except Exception:
            # A full disk must not break downloads; the ring buffer still has the line.
            self._handler.handleError(record)

    def lines(self, item_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(e) for e in self._entries if item_id is None or e["item"] == item_id]

    def close(self) -> None:
        if self._handler is not None:
            self._handler.close()
            self._handler = None
