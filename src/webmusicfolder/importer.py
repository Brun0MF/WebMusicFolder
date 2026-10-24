"""Link an External MP3 to a YouTube video so the app treats it as its own."""

from __future__ import annotations

import contextlib
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

from mutagen.id3 import ID3, TXXX, ID3NoHeaderError

from webmusicfolder.downloader import PART_SUFFIX, _fsync_dir
from webmusicfolder.library import MP3_SUFFIX, UNKNOWN, read_library_tags
from webmusicfolder.models import Track
from webmusicfolder.paths import PathError, resolve_inside
from webmusicfolder.tagging import DESC_URL, DESC_VIDEO_ID, clean_artist
from webmusicfolder.urls import video_url

QUALITY_IMPORTED = "imported"


class ImportConflictError(Exception):
    """The file or the video is already linked; the message is shown to the user."""


def _write_link_frames(source: Path, dest: Path, video_id: str, url: str) -> None:
    """Copy source to dest and add the two frames there, keeping every other frame."""
    shutil.copy2(source, dest)
    try:
        tags = ID3(dest)
        version = 3 if tags.version[:2] == (2, 3) else 4
    except ID3NoHeaderError:
        tags = ID3()
        version = 4
    tags.delall(f"TXXX:{DESC_VIDEO_ID}")
    tags.delall(f"TXXX:{DESC_URL}")
    tags.add(TXXX(encoding=3, desc=DESC_VIDEO_ID, text=video_id))
    tags.add(TXXX(encoding=3, desc=DESC_URL, text=url))
    tags.save(dest, v2_version=version)
    with open(dest, "rb") as fh:
        os.fsync(fh.fileno())


def link_file(music_dir: Path, relpath: str, video_id: str, tracks: dict[str, Track]) -> Track:
    """Tag `relpath` with the video id and return the Track to register.

    Raises PathError (bad or missing file), ImportConflictError (already linked) or OSError.
    The original is replaced only by a fully written copy, so a failure leaves it intact.
    """
    if not relpath.lower().endswith(MP3_SUFFIX) or "\x00" in relpath:
        raise PathError("not an mp3 file")
    path = resolve_inside(music_dir, *relpath.split("/"))
    if not path.is_file():
        raise PathError("file not found")

    current = read_library_tags(path)
    if current.video_id and current.video_id in tracks:
        raise ImportConflictError("This file is already linked to a video")
    other = tracks.get(video_id)
    if other is not None and resolve_inside(music_dir, *other.relpath.split("/")).is_file():
        raise ImportConflictError(f"That video is already in the library as {other.relpath}")

    url = video_url(video_id)
    part = path.with_name(f".{path.name}{PART_SUFFIX}")
    try:
        _write_link_frames(path, part, video_id, url)
        os.replace(part, path)
    except BaseException:
        with contextlib.suppress(OSError):
            part.unlink()
        raise
    _fsync_dir(path.parent)

    rel = path.relative_to(resolve_inside(music_dir)).as_posix()
    artist = "" if current.artist == UNKNOWN else clean_artist(current.artist)
    return Track(
        video_id=video_id,
        url=url,
        title=current.title,
        artist=artist,
        duration_s=current.duration_s,
        subfolder=rel.rsplit("/", 1)[0] if "/" in rel else "",
        relpath=rel,
        downloaded_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        quality=QUALITY_IMPORTED,
    )
