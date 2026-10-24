"""Single file JSON state store with atomic saves and one asyncio lock."""

from __future__ import annotations

import asyncio
import contextlib
import copy
import json
import os
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .models import (
    STATUS_DONE,
    STATUS_DOWNLOADING,
    STATUS_FAILED,
    STATUS_QUEUED,
    AppSettings,
    QueueItem,
    State,
    Track,
)

SCHEMA_VERSION = 1
BACKUP_INTERVAL_S = 3600
PRUNE_AFTER = timedelta(days=7)

# Maps a file version to a function that upgrades the raw dict to the next version.
MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {}


class StateCorruptError(RuntimeError):
    """The state file exists but cannot be read; it is left untouched."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _migrate(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("state root must be an object")
    version = data.get("version")
    if not isinstance(version, int) or isinstance(version, bool):
        raise ValueError("missing or invalid 'version' field")
    if version > SCHEMA_VERSION:
        raise ValueError(f"state version {version} is newer than supported {SCHEMA_VERSION}")
    while version < SCHEMA_VERSION:
        step = MIGRATIONS.get(version)
        if step is None:
            raise ValueError(f"no migration from state version {version}")
        data = step(data)
        version = data["version"]
    return data


def _fsync_dir(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_atomic(path: Path, payload: bytes) -> None:
    """Write payload to path so readers see either the old or the new file, never a mix."""
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as fh:
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    _fsync_dir(path.parent)


class StateStore:
    """Holds the in-memory State and persists every mutation before publishing it."""

    def __init__(self, path: Path, now: Callable[[], datetime] = _utc_now) -> None:
        self.path = Path(path)
        self.backup_path = self.path.with_name(self.path.name + ".bak")
        self._now = now
        self._lock = asyncio.Lock()
        self._state = State()

    def load(self) -> None:
        """Load the file (creating an empty one if missing) and prune old done items.

        Raises StateCorruptError without touching the file when it cannot be parsed.
        """
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._state = State(version=SCHEMA_VERSION)
            self._persist(self._state)
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self._state = State.from_dict(_migrate(raw))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise StateCorruptError(
                f"cannot read {self.path}: {exc}. The file was not modified; "
                f"restore it from {self.backup_path} if that copy is good."
            ) from exc
        if self._prune(self._state):
            self._persist(self._state)

    def _prune(self, state: State) -> bool:
        cutoff = self._now() - PRUNE_AFTER
        kept = []
        for item in state.queue:
            if item.status == STATUS_DONE:
                stamp = _parse_ts(item.finished_at) or _parse_ts(item.added_at)
                if stamp is not None and stamp < cutoff:
                    continue
            kept.append(item)
        changed = len(kept) != len(state.queue)
        state.queue = kept
        return changed

    def _backup_if_due(self) -> None:
        if not self.path.exists():
            return
        with contextlib.suppress(OSError):
            if time.time() - self.backup_path.stat().st_mtime < BACKUP_INTERVAL_S:
                return
        _write_atomic(self.backup_path, self.path.read_bytes())

    def _persist(self, state: State) -> None:
        self._backup_if_due()
        payload = json.dumps(state.to_dict(), indent=2, ensure_ascii=False).encode("utf-8")
        _write_atomic(self.path, payload)

    async def mutate[T](self, fn: Callable[[State], T]) -> T:
        """Apply fn to a copy of the state, save it, then publish it.

        If fn or the save fails, memory and disk stay unchanged. Use this for
        transitions that must touch several parts of the state at once.
        """
        async with self._lock:
            draft = copy.deepcopy(self._state)
            result = fn(draft)
            await asyncio.to_thread(self._persist, draft)
            self._state = draft
            return result

    async def _read[T](self, fn: Callable[[State], T]) -> T:
        async with self._lock:
            return copy.deepcopy(fn(self._state))

    # Settings

    def settings_snapshot(self) -> AppSettings:
        """Synchronous copy of the settings, for startup before the event loop runs."""
        return replace(self._state.settings)

    async def get_settings(self) -> AppSettings:
        return await self._read(lambda s: s.settings)

    async def update_settings(self, **changes: Any) -> AppSettings:
        def apply(state: State) -> AppSettings:
            state.settings = replace(state.settings, **changes)
            return state.settings

        return await self.mutate(apply)

    # Tracks

    async def get_track(self, video_id: str) -> Track | None:
        return await self._read(lambda s: s.tracks.get(video_id))

    async def list_tracks(self) -> list[Track]:
        return await self._read(lambda s: list(s.tracks.values()))

    async def upsert_track(self, track: Track) -> None:
        await self.mutate(lambda s: s.tracks.__setitem__(track.video_id, track))

    async def remove_track(self, video_id: str) -> bool:
        return await self.mutate(lambda s: s.tracks.pop(video_id, None) is not None)

    async def remove_tracks_by_relpath(self, relpath: str) -> int:
        return await self.remove_tracks_where(lambda t: t.relpath == relpath)

    async def remove_tracks_where(self, match: Callable[[Track], bool]) -> int:
        def apply(state: State) -> int:
            ids = [vid for vid, t in state.tracks.items() if match(t)]
            for vid in ids:
                del state.tracks[vid]
            return len(ids)

        return await self.mutate(apply)

    async def move_tracks(self, moves: dict[str, str]) -> int:
        """Point tracks at their new relpath; `moves` maps old relpath to new relpath."""

        def apply(state: State) -> int:
            count = 0
            for track in state.tracks.values():
                new = moves.get(track.relpath)
                if new is not None:
                    track.relpath = new
                    track.subfolder = new.rsplit("/", 1)[0] if "/" in new else ""
                    count += 1
            return count

        return await self.mutate(apply)

    # Queue

    async def list_queue(self) -> list[QueueItem]:
        return await self._read(lambda s: list(s.queue))

    async def get_queue_item(self, item_id: str) -> QueueItem | None:
        return await self._read(lambda s: next((i for i in s.queue if i.id == item_id), None))

    async def add_queue_items(self, items: list[QueueItem]) -> None:
        await self.mutate(lambda s: s.queue.extend(items))

    async def update_queue_item(self, item_id: str, **changes: Any) -> QueueItem:
        """Change fields of one item; stamps finished_at when it becomes done or failed."""

        def apply(state: State) -> QueueItem:
            for index, item in enumerate(state.queue):
                if item.id == item_id:
                    fields = dict(changes)
                    if fields.get("status") in (STATUS_DONE, STATUS_FAILED):
                        stamp = self._now().strftime("%Y-%m-%dT%H:%M:%SZ")
                        fields.setdefault("finished_at", stamp)
                    updated = replace(item, **fields)
                    state.queue[index] = updated
                    return updated
            raise KeyError(item_id)

        return await self.mutate(apply)

    async def remove_queue_item(self, item_id: str) -> bool:
        def apply(state: State) -> bool:
            before = len(state.queue)
            state.queue = [i for i in state.queue if i.id != item_id]
            return len(state.queue) != before

        return await self.mutate(apply)

    async def requeue_downloading(self) -> int:
        """Crash recovery: items left in `downloading` go back to `queued`."""

        def apply(state: State) -> int:
            count = 0
            for index, item in enumerate(state.queue):
                if item.status == STATUS_DOWNLOADING:
                    state.queue[index] = replace(item, status=STATUS_QUEUED)
                    count += 1
            return count

        return await self.mutate(apply)

    async def finish_item(self, item_id: str, track: Track) -> QueueItem:
        """Register the track and mark its queue item done in one atomic save."""

        def apply(state: State) -> QueueItem:
            for index, item in enumerate(state.queue):
                if item.id == item_id:
                    stamp = self._now().strftime("%Y-%m-%dT%H:%M:%SZ")
                    updated = replace(
                        item,
                        status=STATUS_DONE,
                        title=track.title,
                        error=None,
                        overwrite=False,
                        finished_at=stamp,
                    )
                    state.queue[index] = updated
                    state.tracks[track.video_id] = track
                    return updated
            raise KeyError(item_id)

        return await self.mutate(apply)
