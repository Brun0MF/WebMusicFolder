"""Background worker: takes queued items, downloads them and records the outcome."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import shutil
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from webmusicfolder import tagging
from webmusicfolder.downloader import DownloadContext, download_one, existing_track_file
from webmusicfolder.errors import (
    CODE_DISK_FULL,
    CODE_PERMISSION,
    CODE_UNKNOWN,
    USER_MESSAGES,
    DownloadError,
)
from webmusicfolder.models import (
    STATUS_DONE,
    STATUS_DOWNLOADING,
    STATUS_FAILED,
    STATUS_QUEUED,
    QueueItem,
    Track,
)
from webmusicfolder.store import StateStore

log = logging.getLogger("webmusicfolder.worker")

# Delays before retry 1, 2 and 3 of a network failure (seconds).
DEFAULT_BACKOFF_S = (30.0, 120.0, 600.0)
# Minimum spacing of progress events per item, so a busy download stays cheap to publish.
PROGRESS_INTERVAL_S = 1.0
# Consecutive disk or permission failures that pause the queue.
PAUSE_AFTER_FAILURES = 3
PAUSING_CODES = frozenset({CODE_DISK_FULL, CODE_PERMISSION})

EventSink = Callable[[str, dict[str, Any]], None]


def format_error(code: str, message: str) -> str:
    """Error text stored on a queue item: '<code>: <readable message>[: <raw detail>]'.

    The readable message comes first so the UI can show it alone; the raw yt-dlp text
    stays after it so unknown errors remain debuggable.
    """
    readable = USER_MESSAGES.get(code, "")
    if not message:
        return f"{code}: {readable}"
    if not readable or message.startswith(readable):
        return f"{code}: {message}"
    return f"{code}: {readable}: {message}"


class WorkerBusyError(RuntimeError):
    """Exclusive access was requested while downloads run or another task holds it."""


class QueueWorker:
    def __init__(
        self,
        store: StateStore,
        ctx: DownloadContext,
        concurrency: int = 1,
        quality: Callable[[], str] = lambda: "v0",
        backoff_s: tuple[float, ...] = DEFAULT_BACKOFF_S,
        clock: Callable[[], float] = time.monotonic,
        on_event: EventSink | None = None,
        on_log: Callable[[QueueItem, str], None] | None = None,
        redact: Callable[[str], str] = lambda text: text,
    ) -> None:
        self.store = store
        self.ctx = ctx
        self.concurrency = concurrency
        self._quality = quality
        self._backoff_s = backoff_s
        self._clock = clock
        self._on_event = on_event
        self._on_log = on_log
        self._redact = redact
        self._wake = asyncio.Event()
        self._runner_task: asyncio.Task[None] | None = None
        self._active: dict[str, asyncio.Task[None]] = {}
        # Item id to the clock time before which it must not start again.
        self._retry_at: dict[str, float] = {}
        self._timers: list[asyncio.TimerHandle] = []
        self._stopping = False
        self._consecutive_disk_failures = 0
        self._cancelled: set[str] = set()
        self._maintenance = False
        self._last_progress_at: dict[str, float] = {}
        # Latest progress event per active item, used for the snapshot of a new SSE client.
        self.progress: dict[str, dict[str, Any]] = {}
        # Set when the queue pauses itself; the UI shows it as a banner.
        self.paused_reason: str | None = None

    # Lifecycle

    async def recover(self) -> int:
        """Startup recovery: requeue interrupted items and wipe stale temp files."""
        requeued = await self.store.requeue_downloading()
        await asyncio.to_thread(self._wipe_tmp)
        if requeued:
            log.info("recovered %d interrupted download(s), resuming", requeued)
        return requeued

    def _wipe_tmp(self) -> None:
        root = self.ctx.tmp_root
        root.mkdir(parents=True, exist_ok=True)
        for entry in root.iterdir():
            if entry.is_dir() and not entry.is_symlink():
                shutil.rmtree(entry, ignore_errors=True)
            else:
                with contextlib.suppress(OSError):
                    entry.unlink()

    async def start(self) -> None:
        if self._runner_task is not None:
            return
        self._stopping = False
        self._runner_task = asyncio.create_task(self._loop(), name="queue-worker")
        # Process whatever is already queued without waiting for a submission.
        self.wake()

    async def stop(self) -> None:
        """Interrupt running downloads and put them back in the queue."""
        self._stopping = True
        for timer in self._timers:
            timer.cancel()
        self._timers.clear()
        interrupted = list(self._active)
        tasks = [self._runner_task, *self._active.values()]
        for task in tasks:
            if task is not None:
                task.cancel()
        await asyncio.gather(*(t for t in tasks if t is not None), return_exceptions=True)
        self._runner_task = None
        self._active.clear()
        if interrupted:
            await self.store.mutate(lambda s: self._requeue(s, set(interrupted)))

    @staticmethod
    def _requeue(state: Any, ids: set[str]) -> None:
        for index, item in enumerate(state.queue):
            if item.id in ids and item.status == STATUS_DOWNLOADING:
                # An interrupted attempt does not count against the retry budget.
                state.queue[index] = replace(
                    item, status=STATUS_QUEUED, attempts=max(0, item.attempts - 1)
                )

    def wake(self) -> None:
        self._wake.set()

    @contextlib.asynccontextmanager
    async def exclusive(self) -> AsyncIterator[None]:
        """Keep the worker idle while files the runner imports are replaced (yt-dlp update).

        Raises WorkerBusyError when a download is running or the worker is already held.
        """
        if self._active or self._maintenance:
            raise WorkerBusyError("downloads are running" if self._active else "already updating")
        self._maintenance = True
        try:
            yield
        finally:
            self._maintenance = False
            self.wake()

    @property
    def maintenance(self) -> bool:
        return self._maintenance

    def resume(self) -> None:
        """Clear a self imposed pause and continue."""
        self.paused_reason = None
        self._consecutive_disk_failures = 0
        self.wake()

    @property
    def active_ids(self) -> set[str]:
        return set(self._active)

    # Loop

    async def _loop(self) -> None:
        while True:
            await self._wake.wait()
            self._wake.clear()
            try:
                await self._fill()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("worker loop error")

    async def _fill(self) -> None:
        while not self._stopping and self.paused_reason is None and not self._maintenance:
            if len(self._active) >= self.concurrency:
                return
            item = await self._claim()
            if item is None:
                return
            if self._maintenance:
                # Held while the claim was in flight: hand the item back untouched.
                await self.store.mutate(lambda s, i=item.id: self._requeue(s, {i}))
                return
            task = asyncio.create_task(self._process(item), name=f"download-{item.id}")
            self._active[item.id] = task
            task.add_done_callback(lambda _t, item_id=item.id: self._finished(item_id))

    def _finished(self, item_id: str) -> None:
        self._active.pop(item_id, None)
        self._cancelled.discard(item_id)
        self._last_progress_at.pop(item_id, None)
        self.progress.pop(item_id, None)
        if not self._stopping:
            self.wake()

    async def _claim(self) -> QueueItem | None:
        """Mark the oldest eligible queued item as downloading and return it."""
        now = self._clock()

        def apply(state: Any) -> QueueItem | None:
            for index, item in enumerate(state.queue):
                if item.status != STATUS_QUEUED or item.id in self._active:
                    continue
                if self._retry_at.get(item.id, 0.0) > now:
                    continue
                claimed = replace(item, status=STATUS_DOWNLOADING, attempts=item.attempts + 1)
                state.queue[index] = claimed
                return claimed
            return None

        claimed = await self.store.mutate(apply)
        if claimed is not None:
            self._retry_at.pop(claimed.id, None)
            self._emit("item", claimed)
        return claimed

    # One item

    async def _process(self, item: QueueItem) -> None:
        try:
            track = await self._skip_if_present(item)
            if track is None:
                options = await self.store.get_settings()
                track = await download_one(
                    self._context(),
                    item,
                    self._quality(),
                    on_event=lambda e: self._on_runner_event(item.id, e),
                    on_log=self._log_for(item),
                    replace_relpath=await self._old_relpath(item),
                    sponsorblock=options.sponsorblock,
                    replaygain=options.replaygain,
                )
            done = await self.store.finish_item(item.id, track)
            self._consecutive_disk_failures = 0
            self._emit("item", done)
        except asyncio.CancelledError:
            if item.id in self._cancelled:
                # Cancelled by the user: drop the item instead of requeueing it.
                await self._drop(item.id)
                return
            # stop() requeues the item.
            raise
        except DownloadError as exc:
            await self._handle_error(item, exc)
        except Exception as exc:
            log.exception("unexpected error while downloading %s", item.video_id)
            await self._handle_error(item, DownloadError(CODE_UNKNOWN, f"Unexpected error: {exc}"))

    def _log_for(self, item: QueueItem) -> Callable[[str], None] | None:
        sink = self._on_log
        return None if sink is None else lambda line: sink(item, line)

    def _context(self) -> DownloadContext:
        cookies = self.ctx.cookies
        return self.ctx if cookies is None or cookies.is_file() else replace(self.ctx, cookies=None)

    async def _old_relpath(self, item: QueueItem) -> str | None:
        if not item.overwrite:
            return None
        track = await self.store.get_track(item.video_id)
        return track.relpath if track is not None else None

    def _on_runner_event(self, item_id: str, event: dict[str, Any]) -> None:
        kind = event.get("type")
        if kind not in ("progress", "stage"):
            return
        now = self._clock()
        if kind == "progress":
            last = self._last_progress_at.get(item_id)
            # The closing 100 % is never throttled, or a short track would show no movement.
            finished = (event.get("pct") or 0) >= 100
            if last is not None and now - last < PROGRESS_INTERVAL_S and not finished:
                return
            self._last_progress_at[item_id] = now
        # Unknown values (pct None while the size is unknown) must not wipe the last good one.
        payload = {"id": item_id, **{k: v for k, v in event.items() if v is not None}}
        # A stage event carries no percentage; keep the last one for the snapshot.
        self.progress[item_id] = {**self.progress.get(item_id, {}), **payload}
        self._emit("progress", payload)

    # User actions

    async def _drop(self, item_id: str) -> None:
        self._retry_at.pop(item_id, None)
        if await self.store.remove_queue_item(item_id):
            self._emit("removed", {"id": item_id})

    async def cancel(self, item_id: str) -> None:
        """Stop a running download or remove a queued, failed or finished item.

        Raises KeyError for an unknown id.
        """
        if await self.store.get_queue_item(item_id) is None:
            raise KeyError(item_id)
        task = self._active.get(item_id)
        if task is not None:
            self._cancelled.add(item_id)
            task.cancel()
            return
        await self._drop(item_id)

    async def cancel_pending(self) -> int:
        """Drop every queued item and stop the running ones; returns how many were affected."""
        items = await self.store.list_queue()
        # Queued first, so the worker cannot start the next one after a running item stops.
        order = {STATUS_QUEUED: 0, STATUS_DOWNLOADING: 1}
        pending = sorted((i for i in items if i.status in order), key=lambda i: order[i.status])
        count = 0
        for item in pending:
            try:
                await self.cancel(item.id)
                count += 1
            except KeyError:
                continue
        return count

    async def dismiss_finished(self) -> int:
        """Remove every done or failed item from the list; returns how many were removed."""
        finished = [
            i for i in await self.store.list_queue() if i.status in (STATUS_DONE, STATUS_FAILED)
        ]
        for item in finished:
            await self._drop(item.id)
        return len(finished)

    async def retry(self, item_id: str) -> QueueItem:
        """Requeue a failed item with a fresh retry budget.

        Raises KeyError for an unknown id and ValueError when the item did not fail.
        """
        item = await self.store.get_queue_item(item_id)
        if item is None:
            raise KeyError(item_id)
        if item.status != STATUS_FAILED:
            raise ValueError("only failed items can be retried")
        self._retry_at.pop(item_id, None)
        updated = await self.store.update_queue_item(
            item_id, status=STATUS_QUEUED, attempts=0, error=None, finished_at=None
        )
        self._emit("item", updated)
        self.wake()
        return updated

    async def retry_failed(self) -> int:
        """Requeue every failed item; returns how many were requeued."""
        failed = [i for i in await self.store.list_queue() if i.status == STATUS_FAILED]
        for item in failed:
            self._retry_at.pop(item.id, None)
            updated = await self.store.update_queue_item(
                item.id, status=STATUS_QUEUED, attempts=0, error=None, finished_at=None
            )
            self._emit("item", updated)
        if failed:
            self.resume()
        return len(failed)

    def _emit(self, kind: str, payload: Any) -> None:
        if self._on_event is not None:
            data = payload if isinstance(payload, dict) else payload.__dict__
            self._on_event(kind, dict(data))

    async def _skip_if_present(self, item: QueueItem) -> Track | None:
        """Resume shortcut: the final file is already there and tagged for this video."""
        if item.overwrite:
            return None
        return await asyncio.to_thread(self._find_finished, item)

    def _find_finished(self, item: QueueItem) -> Track | None:
        found = existing_track_file(self.ctx.music_dir, item.subfolder, item.video_id, item.title)
        if found is None:
            return None
        try:
            info = tagging.read_tags(found)
            relpath = found.relative_to(self.ctx.music_dir.resolve()).as_posix()
        except Exception:
            return None
        log.info("skipping %s: already downloaded as %s", item.video_id, relpath)
        return Track(
            video_id=item.video_id,
            url=info.url or item.url,
            title=info.title or item.title or item.video_id,
            artist=info.artist,
            duration_s=info.duration_s,
            subfolder=item.subfolder,
            relpath=relpath,
            downloaded_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            quality=self._quality(),
        )

    def _log_line(self, item: QueueItem, line: str) -> None:
        if self._on_log is not None:
            self._on_log(item, line)

    async def _handle_error(self, item: QueueItem, exc: DownloadError) -> None:
        # The error text is stored and shown in the browser, so it gets the same scrubbing.
        exc = DownloadError(exc.code, self._redact(exc.message))
        if exc.retryable and item.attempts <= len(self._backoff_s):
            delay = self._backoff_s[item.attempts - 1]
            self._retry_at[item.id] = self._clock() + delay
            attempt = f"retry {item.attempts} of {len(self._backoff_s)}"
            note = f"{format_error(exc.code, exc.message)} ({attempt})"
            updated = await self.store.update_queue_item(item.id, status=STATUS_QUEUED, error=note)
            self._emit("item", updated)
            self._timers.append(asyncio.get_running_loop().call_later(delay, self.wake))
            log.warning("%s: %s, retrying in %.0fs", item.video_id, exc.message, delay)
            self._log_line(item, f"WARNING: {note}, next try in {delay:.0f}s")
            return

        updated = await self.store.update_queue_item(
            item.id, status=STATUS_FAILED, error=format_error(exc.code, exc.message)
        )
        self._emit("item", updated)
        log.error("%s failed: %s", item.video_id, format_error(exc.code, exc.message))
        self._log_line(item, f"ERROR: {format_error(exc.code, exc.message)}")
        if exc.code in PAUSING_CODES:
            self._consecutive_disk_failures += 1
            if self._consecutive_disk_failures >= PAUSE_AFTER_FAILURES:
                self.paused_reason = USER_MESSAGES[exc.code]
                self._emit("paused", {"reason": self.paused_reason})
        else:
            self._consecutive_disk_failures = 0


def tmp_root_for(data_dir: Path) -> Path:
    return data_dir / "tmp"
