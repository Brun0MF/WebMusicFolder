"""Scan the music dir and build library entries from MP3 tags, with a per file cache."""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path

from mutagen.id3 import ID3
from mutagen.mp3 import MP3

from webmusicfolder.models import Track
from webmusicfolder.paths import PathError, resolve_inside
from webmusicfolder.tagging import DESC_VIDEO_ID

SOURCE_APP = "App"
SOURCE_EXTERNAL = "External"
UNKNOWN = "Unknown"
MP3_SUFFIX = ".mp3"
# Embedded pictures larger than this are not served; the placeholder is shown instead.
MAX_COVER_BYTES = 5 * 1024 * 1024
COVER_MIMES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


@dataclass(frozen=True)
class _Tags:
    title: str
    artist: str
    album: str
    duration_s: int
    has_cover: bool
    video_id: str | None


@dataclass(frozen=True)
class Entry:
    # Path relative to the music dir, with '/' separators.
    path: str
    title: str
    artist: str
    album: str
    duration_s: int
    size: int
    subfolder: str
    source: str
    has_cover: bool
    video_id: str | None


@dataclass(frozen=True)
class Cover:
    data: bytes
    mime: str


def _first_text(tags: ID3, frame: str) -> str:
    found = tags.get(frame)
    return str(found.text[0]).strip() if found is not None and found.text else ""


def read_library_tags(path: Path) -> _Tags:
    """Tags of one file with fallbacks; a corrupt or tagless file still yields an entry."""
    stem = path.stem
    try:
        audio = MP3(path)
    except Exception:
        return _Tags(stem, UNKNOWN, UNKNOWN, 0, False, None)
    tags = audio.tags if audio.tags is not None else ID3()
    return _Tags(
        title=_first_text(tags, "TIT2") or stem,
        artist=_first_text(tags, "TPE1") or UNKNOWN,
        album=_first_text(tags, "TALB") or UNKNOWN,
        duration_s=int(round(audio.info.length)),
        has_cover=bool(tags.getall("APIC")),
        video_id=_first_text(tags, f"TXXX:{DESC_VIDEO_ID}") or None,
    )


class Library:
    def __init__(self, music_dir: Path) -> None:
        self.music_dir = music_dir
        # relpath -> ((mtime_ns, size), tags)
        self._cache: dict[str, tuple[tuple[int, int], _Tags]] = {}
        self._lock = threading.Lock()

    def invalidate(self) -> None:
        with self._lock:
            self._cache = {}

    def _mp3_files(self, root: Path) -> list[tuple[Path, str]]:
        found = []
        # followlinks=False: symlinked directories are listed but never entered.
        for current, dirnames, filenames in os.walk(root, followlinks=False):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
            for name in sorted(filenames):
                if name.startswith(".") or not name.lower().endswith(MP3_SUFFIX):
                    continue
                path = Path(current, name)
                if path.is_symlink():
                    try:
                        resolve_inside(root, *path.relative_to(root).parts)
                    except PathError:
                        continue
                found.append((path, path.relative_to(root).as_posix()))
        return found

    def scan(self, tracks: dict[str, Track]) -> list[Entry]:
        """Blocking scan; call it from a worker thread."""
        try:
            root = self.music_dir.resolve(strict=True)
        except OSError:
            return []
        with self._lock:
            cache = self._cache
        fresh: dict[str, tuple[tuple[int, int], _Tags]] = {}
        entries = []
        for path, rel in self._mp3_files(root):
            try:
                stat = path.stat()
            except OSError:
                continue
            key = (stat.st_mtime_ns, stat.st_size)
            cached = cache.get(rel)
            tags = cached[1] if cached is not None and cached[0] == key else read_library_tags(path)
            fresh[rel] = (key, tags)
            # Source is derived on every scan so it follows the state, not the cache.
            is_app = tags.video_id is not None and tags.video_id in tracks
            entries.append(
                Entry(
                    path=rel,
                    title=tags.title,
                    artist=tags.artist,
                    album=tags.album,
                    duration_s=tags.duration_s,
                    size=stat.st_size,
                    subfolder=rel.rsplit("/", 1)[0] if "/" in rel else "",
                    source=SOURCE_APP if is_app else SOURCE_EXTERNAL,
                    has_cover=tags.has_cover,
                    video_id=tags.video_id,
                )
            )
        with self._lock:
            self._cache = fresh
        return entries

    def cover(self, relpath: str) -> Cover | None:
        """Embedded front cover of a library file, None when absent or too large.

        Raises PathError when the path leaves the music dir or is not an MP3.
        """
        if not relpath.lower().endswith(MP3_SUFFIX) or "\x00" in relpath:
            raise PathError("not an mp3 file")
        path = resolve_inside(self.music_dir, *relpath.split("/"))
        if not path.is_file():
            raise PathError("file not found")
        try:
            tags = ID3(path)
        except Exception:
            return None
        for frame in tags.getall("APIC"):
            if len(frame.data) <= MAX_COVER_BYTES:
                mime = frame.mime if frame.mime in COVER_MIMES else "image/jpeg"
                return Cover(bytes(frame.data), mime)
        return None


def filter_entries(
    entries: list[Entry], query: str = "", subfolder: str | None = None, source: str | None = None
) -> list[Entry]:
    """Case insensitive search over title and artist, plus exact subfolder and source filters."""
    needle = query.strip().casefold()
    result = []
    for entry in entries:
        if subfolder is not None and entry.subfolder != subfolder:
            continue
        if source is not None and entry.source != source:
            continue
        if (
            needle
            and needle not in entry.title.casefold()
            and needle not in entry.artist.casefold()
        ):
            continue
        result.append(entry)
    return result
