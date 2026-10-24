import asyncio
import json
import os
import time
from datetime import UTC, datetime, timedelta

import pytest

from webmusicfolder import store as store_mod
from webmusicfolder.models import QueueItem, State, Track
from webmusicfolder.store import SCHEMA_VERSION, StateCorruptError, StateStore


def _item(item_id: str, **kw) -> QueueItem:
    base = dict(
        id=item_id,
        video_id="v" + item_id,
        url="u",
        title="t",
        subfolder="",
        added_at="2026-10-24T00:00:00Z",
    )
    base.update(kw)
    return QueueItem(**base)


def _track(video_id: str = "abc") -> Track:
    return Track(video_id, "u", "t", "a", 1, "", "t.mp3", "2026-10-24T00:00:00Z", "v0")


def _store(tmp_path, **kw) -> StateStore:
    s = StateStore(tmp_path / "state.json", **kw)
    s.load()
    return s


def test_fresh_dir_creates_valid_empty_state(tmp_path):
    _store(tmp_path / "data")
    data = json.loads((tmp_path / "data" / "state.json").read_text())
    assert data["version"] == SCHEMA_VERSION
    assert data["tracks"] == {} and data["queue"] == []
    assert State.from_dict(data) == State()


def test_save_uses_fsync_and_replace(tmp_path, monkeypatch):
    calls = []
    real_fsync, real_replace = os.fsync, os.replace
    monkeypatch.setattr(store_mod.os, "fsync", lambda fd: (calls.append("fsync"), real_fsync(fd)))
    monkeypatch.setattr(
        store_mod.os, "replace", lambda a, b: (calls.append("replace"), real_replace(a, b))
    )
    s = _store(tmp_path)
    calls.clear()
    asyncio.run(s.upsert_track(_track()))
    assert "replace" in calls
    assert calls.index("fsync") < calls.index("replace")
    assert calls.count("fsync") >= 2
    assert not (tmp_path / "state.json.tmp").exists()


async def test_state_survives_reload(tmp_path):
    s = _store(tmp_path)
    await s.upsert_track(_track())
    await s.add_queue_items([_item("1")])
    await s.update_settings(quality="320k")
    again = _store(tmp_path)
    assert (await again.get_track("abc")).title == "t"
    assert [i.id for i in await again.list_queue()] == ["1"]
    assert (await again.get_settings()).quality == "320k"


async def test_reads_return_copies(tmp_path):
    s = _store(tmp_path)
    await s.add_queue_items([_item("1")])
    (await s.list_queue())[0].title = "hacked"
    assert (await s.get_queue_item("1")).title == "t"


async def test_concurrent_mutations_do_not_lose_updates(tmp_path):
    s = _store(tmp_path)
    await asyncio.gather(*(s.add_queue_items([_item(str(n))]) for n in range(50)))
    assert len(await s.list_queue()) == 50
    await asyncio.gather(*(s.update_queue_item(str(n), attempts=n) for n in range(50)))
    assert sorted(i.attempts for i in await s.list_queue()) == list(range(50))
    assert len(await _store(tmp_path).list_queue()) == 50


async def test_failed_mutation_leaves_state_unchanged(tmp_path):
    s = _store(tmp_path)

    def boom(state):
        state.queue.append(_item("x"))
        raise RuntimeError("nope")

    with pytest.raises(RuntimeError):
        await s.mutate(boom)
    assert await s.list_queue() == []
    with pytest.raises(KeyError):
        await s.update_queue_item("missing", attempts=1)


async def test_failed_save_leaves_memory_unchanged(tmp_path, monkeypatch):
    s = _store(tmp_path)

    def fail(*_a):
        raise OSError("disk full")

    monkeypatch.setattr(s, "_persist", fail)
    with pytest.raises(OSError):
        await s.add_queue_items([_item("1")])
    assert await s.list_queue() == []


async def test_finished_at_stamped_on_done_and_failed(tmp_path):
    s = _store(tmp_path)
    await s.add_queue_items([_item("1"), _item("2")])
    assert (await s.update_queue_item("1", status="done")).finished_at
    assert (await s.update_queue_item("2", status="failed", error="x")).finished_at
    running = await s.update_queue_item("1", status="queued", finished_at=None)
    assert running.finished_at is None


async def test_remove_helpers(tmp_path):
    s = _store(tmp_path)
    await s.upsert_track(_track())
    await s.add_queue_items([_item("1")])
    assert await s.remove_track("abc") and not await s.remove_track("abc")
    assert await s.remove_queue_item("1") and not await s.remove_queue_item("1")


def test_old_done_items_pruned_on_load(tmp_path):
    now = datetime(2026, 11, 1, tzinfo=UTC)
    old = (now - timedelta(days=8)).strftime("%Y-%m-%dT%H:%M:%SZ")
    new = (now - timedelta(days=6)).strftime("%Y-%m-%dT%H:%M:%SZ")
    state = State(
        queue=[
            _item("old_done", status="done", finished_at=old),
            _item("new_done", status="done", finished_at=new),
            _item("old_failed", status="failed", finished_at=old),
            _item("old_queued", added_at=old),
        ]
    )
    (tmp_path / "state.json").write_text(json.dumps(state.to_dict()))
    s = StateStore(tmp_path / "state.json", now=lambda: now)
    s.load()
    ids = {i.id for i in asyncio.run(s.list_queue())}
    assert ids == {"new_done", "old_failed", "old_queued"}
    on_disk = json.loads((tmp_path / "state.json").read_text())
    assert {i["id"] for i in on_disk["queue"]} == ids


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b'{"version": 1, "queue": [',
        b"not json at all",
        b"[]",
        b'{"tracks": {}}',
        b'{"version": 99}',
        b'{"version": 0}',
        b'{"version": 1, "queue": [{"id": "1"}]}',
        b"\xff\xfe\x00",
    ],
)
def test_corrupt_file_raises_and_is_untouched(tmp_path, content):
    path = tmp_path / "state.json"
    path.write_bytes(content)
    with pytest.raises(StateCorruptError) as err:
        StateStore(path).load()
    assert path.read_bytes() == content
    assert "state.json.bak" in str(err.value)
    assert not (tmp_path / "state.json.tmp").exists()


def test_migration_hook_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(store_mod, "SCHEMA_VERSION", 2)
    monkeypatch.setitem(store_mod.MIGRATIONS, 1, lambda d: {**d, "version": 2})
    (tmp_path / "state.json").write_text('{"version": 1}')
    s = StateStore(tmp_path / "state.json")
    s.load()
    assert s._state.version == 2


def test_backup_written_at_most_hourly(tmp_path):
    s = _store(tmp_path)
    bak = tmp_path / "state.json.bak"
    asyncio.run(s.upsert_track(_track("a")))
    assert bak.exists()
    first = json.loads(bak.read_text())
    assert first["tracks"] == {}
    asyncio.run(s.upsert_track(_track("b")))
    assert json.loads(bak.read_text()) == first
    old = time.time() - 2 * 3600
    os.utime(bak, (old, old))
    asyncio.run(s.upsert_track(_track("c")))
    assert set(json.loads(bak.read_text())["tracks"]) == {"a", "b"}
