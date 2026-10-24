"""Spawns the yt-dlp runner subprocess and turns its JSON lines into events and results."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import signal
import sys
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from webmusicfolder.errors import CODE_NETWORK, CODE_UNKNOWN, DownloadError, classify_error

# Seconds without any output before the runner is considered hung.
DEFAULT_IDLE_TIMEOUT_S = 300.0
# Seconds between SIGTERM and SIGKILL when stopping the runner.
KILL_GRACE_S = 3.0
STDERR_TAIL_LINES = 40
# A single flat playlist line can be long; asyncio's default limit is 64 KiB.
STREAM_LIMIT = 4 * 1024 * 1024

EventHandler = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class RunnerSpec:
    """How to start the runner; tests point `cmd` at a fake script."""

    cmd: tuple[str, ...] = (sys.executable, "-m", "webmusicfolder.ytdlp_runner")
    # A directory holding a newer yt-dlp (installed by the update button) is tried first.
    extra_pythonpath: Path | None = None
    idle_timeout_s: float = DEFAULT_IDLE_TIMEOUT_S
    env: dict[str, str] = field(default_factory=dict)

    def environment(self) -> dict[str, str]:
        env = {**os.environ, **self.env, "PYTHONUNBUFFERED": "1"}
        if self.extra_pythonpath is not None and self.extra_pythonpath.is_dir():
            old = env.get("PYTHONPATH")
            env["PYTHONPATH"] = (
                f"{self.extra_pythonpath}{os.pathsep}{old}" if old else str(self.extra_pythonpath)
            )
        return env


@dataclass(frozen=True)
class DownloadResult:
    path: Path
    cover: Path | None
    video_id: str
    title: str
    artist: str
    duration_s: int
    url: str


def _kill_group(proc: asyncio.subprocess.Process, sig: int) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(proc.pid, sig)


async def _stop(proc: asyncio.subprocess.Process) -> None:
    """Terminate the runner and its children (ffmpeg), escalating to SIGKILL."""
    if proc.returncode is None:
        _kill_group(proc, signal.SIGTERM)
        try:
            await asyncio.wait_for(proc.wait(), KILL_GRACE_S)
        except TimeoutError:
            _kill_group(proc, signal.SIGKILL)
            await proc.wait()
    else:
        # The runner is gone but a child may linger in its group.
        _kill_group(proc, signal.SIGKILL)


async def run_runner(
    spec: RunnerSpec,
    args: list[str],
    on_event: EventHandler | None = None,
    on_log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Run the runner, forward every event, and return the final `done` event.

    Raises DownloadError for an `error` event, a crash or a hang. Cancelling the
    awaiting task stops the subprocess group before the cancellation propagates.
    """
    proc = await asyncio.create_subprocess_exec(
        *spec.cmd,
        *args,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=spec.environment(),
        # Own process group so the whole tree can be signalled.
        start_new_session=True,
        limit=STREAM_LIMIT,
    )
    assert proc.stdout is not None and proc.stderr is not None
    stderr_tail: deque[str] = deque(maxlen=STDERR_TAIL_LINES)

    async def drain_stderr() -> None:
        async for raw in proc.stderr:  # type: ignore[union-attr]
            line = raw.decode("utf-8", "replace").rstrip()
            if line:
                stderr_tail.append(line)
                if on_log:
                    on_log(line)

    stderr_task = asyncio.create_task(drain_stderr())
    final: dict[str, Any] | None = None
    error: DownloadError | None = None
    try:
        while True:
            try:
                raw = await asyncio.wait_for(proc.stdout.readline(), spec.idle_timeout_s)
            except TimeoutError:
                await _stop(proc)
                raise DownloadError(CODE_NETWORK, "Runner stalled, no output") from None
            if not raw:
                break
            try:
                event = json.loads(raw)
            except ValueError:
                if on_log:
                    on_log(raw.decode("utf-8", "replace").rstrip())
                continue
            if not isinstance(event, dict):
                continue
            kind = event.get("type")
            if kind == "log" and on_log:
                on_log(str(event.get("line", "")))
            if on_event:
                on_event(event)
            if kind == "done":
                final = event
            elif kind == "error":
                error = DownloadError(
                    str(event.get("code", CODE_UNKNOWN)), str(event.get("message", ""))
                )
        await proc.wait()
        await stderr_task
    except asyncio.CancelledError:
        await _stop(proc)
        stderr_task.cancel()
        raise
    finally:
        if proc.returncode is None:
            await _stop(proc)
        else:
            _kill_group(proc, signal.SIGKILL)
        if not stderr_task.done():
            stderr_task.cancel()

    if error is not None:
        raise error
    if final is None:
        tail = " | ".join(list(stderr_tail)[-3:])
        text = tail or f"runner exited with code {proc.returncode}"
        raise DownloadError(classify_error(text), text[:300])
    return final


def cookie_args(cookies: Path | None, browser: str | None) -> list[str]:
    """Runner flags for the cookie source: an existing cookies file wins over the browser."""
    if cookies is not None and cookies.is_file():
        return ["--cookies", str(cookies)]
    if browser:
        return ["--cookies-from-browser", browser]
    return []


def build_download_args(
    url: str,
    tmp_dir: Path,
    quality: str,
    cookies: Path | None,
    sponsorblock: bool = False,
    browser: str | None = None,
) -> list[str]:
    args = ["download", url, "--tmp-dir", str(tmp_dir), "--quality", quality]
    args += cookie_args(cookies, browser)
    if sponsorblock:
        args.append("--sponsorblock")
    return args


async def run_download(
    spec: RunnerSpec,
    url: str,
    tmp_dir: Path,
    quality: str,
    cookies: Path | None = None,
    on_event: EventHandler | None = None,
    on_log: Callable[[str], None] | None = None,
    sponsorblock: bool = False,
    browser: str | None = None,
) -> DownloadResult:
    done = await run_runner(
        spec,
        build_download_args(url, tmp_dir, quality, cookies, sponsorblock, browser),
        on_event,
        on_log,
    )
    info = done.get("info") or {}
    path = done.get("path")
    if not path or not info.get("video_id"):
        raise DownloadError(CODE_UNKNOWN, "runner finished without a file")
    cover = done.get("cover")
    return DownloadResult(
        path=Path(path),
        cover=Path(cover) if cover else None,
        video_id=str(info["video_id"]),
        title=str(info.get("title") or info["video_id"]),
        artist=str(info.get("artist") or ""),
        duration_s=int(info.get("duration_s") or 0),
        url=str(info.get("url") or url),
    )
