"""Download one queue item: run the runner in a temp dir, tag, then move into the library."""

from __future__ import annotations

import asyncio
import contextlib
import errno
import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from webmusicfolder import loudness, tagging
from webmusicfolder.errors import (
    CODE_DISK_FULL,
    CODE_FFMPEG,
    CODE_PERMISSION,
    CODE_UNKNOWN,
    DownloadError,
)
from webmusicfolder.models import QueueItem, Track
from webmusicfolder.paths import PathError, choose_filename, resolve_inside, validate_subfolder
from webmusicfolder.runner_client import RunnerSpec, run_download

PART_SUFFIX = ".part"


@dataclass(frozen=True)
class DownloadContext:
    music_dir: Path
    # Scratch space outside the music dir; wiped on startup by the worker.
    tmp_root: Path
    runner: RunnerSpec
    cookies: Path | None = None
    # 'firefox' or 'firefox:profile'; used only while no cookies file exists.
    cookies_from_browser: str | None = None


def _map_os_error(exc: OSError) -> DownloadError:
    if exc.errno in (errno.ENOSPC, errno.EDQUOT):
        return DownloadError(CODE_DISK_FULL, "Disk full")
    if exc.errno in (errno.EACCES, errno.EPERM, errno.EROFS):
        return DownloadError(CODE_PERMISSION, f"Cannot write to the music folder: {exc.strerror}")
    return DownloadError(CODE_UNKNOWN, f"File error: {exc}")


def _fsync_dir(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_move(src: Path, dest: Path) -> None:
    """Move src to dest so dest is either absent or complete.

    A rename works within one filesystem; across filesystems the file is copied to a
    hidden `.part` file in the target folder first and renamed when fully written.
    """
    try:
        os.replace(src, dest)
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
        part = dest.with_name(f".{dest.name}{PART_SUFFIX}")
        try:
            shutil.copyfile(src, part)
            with open(part, "rb") as fh:
                os.fsync(fh.fileno())
            os.replace(part, dest)
        except BaseException:
            with contextlib.suppress(OSError):
                part.unlink()
            raise
        src.unlink()
    _fsync_dir(dest.parent)


def existing_track_file(music_dir: Path, subfolder: str, video_id: str, title: str) -> Path | None:
    """The file already in the library for this video in this folder, if any."""
    try:
        directory = resolve_inside(music_dir, subfolder)
    except PathError:
        return None
    candidate = directory / choose_filename(directory, title, video_id, owned=True)
    if candidate.is_file() and tagging.read_video_id(candidate) == video_id:
        return candidate
    with contextlib.suppress(OSError):
        for candidate in directory.glob(f"* [[]{video_id}[]].mp3"):
            if candidate.is_file() and tagging.read_video_id(candidate) == video_id:
                return candidate
    return None


def _replace_target(
    ctx: DownloadContext, target_dir: Path, video_id: str, relpath: str | None
) -> Path | None:
    """The old file to overwrite on a redownload, kept at its path so playlists keep working."""
    if not relpath:
        return None
    try:
        old = resolve_inside(ctx.music_dir, *relpath.split("/"))
    except PathError:
        return None
    if old.parent == target_dir and old.is_file() and tagging.read_video_id(old) == video_id:
        return old
    return None


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _tag_and_place(
    ctx: DownloadContext,
    item: QueueItem,
    quality: str,
    result: Any,
    replace_relpath: str | None = None,
    replaygain: tuple[str, str] | None = None,
) -> Track:
    """Blocking part: tag in the temp dir, then move into the target folder."""
    try:
        subfolder = validate_subfolder(item.subfolder)
        target_dir = resolve_inside(ctx.music_dir, subfolder)
    except PathError as exc:
        raise DownloadError(CODE_PERMISSION, str(exc)) from exc

    cover = result.cover.read_bytes() if result.cover else None
    try:
        tagging.write_tags(
            result.path,
            result.title,
            result.artist,
            result.video_id,
            result.url,
            cover,
            replaygain,
        )
    except Exception as exc:
        raise DownloadError(CODE_FFMPEG, f"Tagging failed: {exc}") from exc

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        # Re-resolve after mkdir so a symlink created in between cannot redirect the write.
        target_dir = resolve_inside(ctx.music_dir, subfolder)
        final = _replace_target(ctx, target_dir, result.video_id, replace_relpath)
        if final is None:
            plain = target_dir / choose_filename(
                target_dir, result.title, result.video_id, owned=True
            )
            owned = plain.is_file() and tagging.read_video_id(plain) == result.video_id
            final = target_dir / choose_filename(
                target_dir, result.title, result.video_id, owned=owned
            )
        atomic_move(result.path, final)
    except PathError as exc:
        raise DownloadError(CODE_PERMISSION, str(exc)) from exc
    except OSError as exc:
        raise _map_os_error(exc) from exc

    relpath = final.relative_to(resolve_inside(ctx.music_dir)).as_posix()
    return Track(
        video_id=result.video_id,
        url=result.url,
        title=result.title,
        artist=tagging.clean_artist(result.artist),
        duration_s=result.duration_s,
        subfolder=subfolder,
        relpath=relpath,
        downloaded_at=_now_iso(),
        quality=quality,
    )


async def _measure_replaygain(
    path: Path, on_log: Callable[[str], None] | None
) -> tuple[str, str] | None:
    """ReplayGain text values for the file; a failed measurement only costs the tags."""
    try:
        found = await loudness.measure(path)
    except loudness.LoudnessError as exc:
        if on_log:
            on_log(f"WARNING: ReplayGain skipped: {exc}")
        return None
    return loudness.format_gain(found.gain_db), loudness.format_peak(found.peak)


async def download_one(
    ctx: DownloadContext,
    item: QueueItem,
    quality: str,
    on_event: Callable[[dict[str, Any]], None] | None = None,
    on_log: Callable[[str], None] | None = None,
    replace_relpath: str | None = None,
    sponsorblock: bool = False,
    replaygain: bool = False,
) -> Track:
    """Download, tag and place one item; the target folder only ever sees the finished file.

    `replace_relpath` is the existing file of a redownload; it is swapped atomically only
    after the new file is complete.

    Raises DownloadError on failure. Cancellation stops the runner and still cleans the
    temp dir.
    """
    work_dir = ctx.tmp_root / item.id
    try:
        shutil.rmtree(work_dir, ignore_errors=True)
        work_dir.mkdir(parents=True, exist_ok=True)
        result = await run_download(
            ctx.runner,
            item.url,
            work_dir,
            quality,
            ctx.cookies,
            on_event,
            on_log,
            sponsorblock=sponsorblock,
            browser=ctx.cookies_from_browser,
        )
        gain = await _measure_replaygain(result.path, on_log) if replaygain else None
        return await asyncio.to_thread(
            _tag_and_place, ctx, item, quality, result, replace_relpath, gain
        )
    except OSError as exc:
        raise _map_os_error(exc) from exc
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
