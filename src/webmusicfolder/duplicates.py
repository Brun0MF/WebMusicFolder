"""Find submitted videos that the app already downloaded or already has in the queue."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from webmusicfolder.models import STATUS_DOWNLOADING, STATUS_QUEUED, QueueItem, Track
from webmusicfolder.paths import PathError, resolve_inside

KIND_EXISTS = "exists"
KIND_QUEUED = "queued"


@dataclass(frozen=True)
class Duplicate:
    video_id: str
    # 'exists' (file in the library) or 'queued' (waiting or downloading).
    kind: str
    title: str = ""
    # Path relative to the music dir, only for 'exists'.
    relpath: str = ""


def track_file_exists(music_dir: Path, track: Track) -> bool:
    """True when the track's file is still on disk, inside the music dir."""
    try:
        path = resolve_inside(music_dir, *track.relpath.split("/"))
    except PathError:
        return False
    return path.is_file()


def find_duplicates(
    music_dir: Path,
    tracks: dict[str, Track],
    queue: list[QueueItem],
    video_ids: list[str],
) -> dict[str, Duplicate]:
    """Map video id to its duplicate info.

    Only tracks the app registered count: files copied in by hand are never duplicates,
    and a track whose file was deleted is treated as new. Queue state wins over files so
    an item being redownloaded is reported as already queued.
    """
    active = {i.video_id: i for i in queue if i.status in (STATUS_QUEUED, STATUS_DOWNLOADING)}
    found: dict[str, Duplicate] = {}
    for video_id in video_ids:
        if video_id in active:
            found[video_id] = Duplicate(video_id, KIND_QUEUED, title=active[video_id].title)
            continue
        track = tracks.get(video_id)
        if track is not None and track_file_exists(music_dir, track):
            found[video_id] = Duplicate(
                video_id, KIND_EXISTS, title=track.title, relpath=os.fspath(track.relpath)
            )
    return found
