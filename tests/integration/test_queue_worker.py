import asyncio
import shutil

import pytest

from webmusicfolder import tagging
from webmusicfolder.downloader import DownloadContext
from webmusicfolder.models import QueueItem
from webmusicfolder.queue_worker import QueueWorker
from webmusicfolder.store import StateStore


def vid(n: int) -> str:
    return f"vid{n:08d}"


def item(n: int, subfolder: str = "", overwrite: bool = False) -> QueueItem:
    return QueueItem(
        id=f"id{n}",
        video_id=vid(n),
        url=f"https://www.youtube.com/watch?v={vid(n)}",
        title="",
        subfolder=subfolder,
        added_at=f"2026-10-24T00:00:{n:02d}Z",
        overwrite=overwrite,
    )


async def until(predicate, timeout=10.0):
    end = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < end:
        if await predicate():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("condition not reached in time")


async def statuses(store) -> dict[str, str]:
    return {i.id: i.status for i in await store.list_queue()}


@pytest.fixture
def env(tmp_path, fake_runner):
    store = StateStore(tmp_path / "data" / "state.json")
    store.load()
    (tmp_path / "music").mkdir()

    def build(scenarios=None, titles=None, concurrency=1, backoff=(0.05, 0.05, 0.05), **kw):
        ctx = DownloadContext(
            music_dir=tmp_path / "music",
            tmp_root=tmp_path / "data" / "tmp",
            runner=fake_runner(scenarios=scenarios, titles=titles),
        )
        events = []
        worker = QueueWorker(
            store,
            ctx,
            concurrency=concurrency,
            backoff_s=backoff,
            on_event=lambda k, p: events.append((k, p)),
            **kw,
        )
        worker.events = events
        return worker

    build.store = store
    build.music = tmp_path / "music"
    build.tmp_root = tmp_path / "data" / "tmp"
    build.state_dir = fake_runner.state_dir
    return build


async def test_processes_queue_in_order_without_any_client(env):
    w = env(titles={vid(1): "One", vid(2): "Two"})
    await env.store.add_queue_items([item(1), item(2)])
    await w.start()
    try:
        await until(lambda: _all(env.store, "done"))
    finally:
        await w.stop()
    assert (env.music / "One.mp3").is_file() and (env.music / "Two.mp3").is_file()
    assert sorted(t.video_id for t in await env.store.list_tracks()) == [vid(1), vid(2)]
    queue = await env.store.list_queue()
    assert all(i.finished_at and i.error is None and i.attempts == 1 for i in queue)
    starts = [p["id"] for k, p in w.events if k == "item" and p["status"] == "downloading"]
    assert starts == ["id1", "id2"]
    assert any(k == "progress" for k, _ in w.events)


async def _all(store, status):
    return all(s == status for s in (await statuses(store)).values())


async def test_new_item_wakes_idle_worker(env):
    w = env()
    await w.start()
    try:
        await asyncio.sleep(0.1)
        await env.store.add_queue_items([item(1)])
        w.wake()
        await until(lambda: _all(env.store, "done"))
    finally:
        await w.stop()


async def test_failing_item_does_not_block_others(env):
    w = env(scenarios={vid(2): "error:unavailable", vid(4): "crash"})
    await env.store.add_queue_items([item(n) for n in range(1, 6)])
    await w.start()
    try:
        await until(lambda: _none_pending(env.store))
    finally:
        await w.stop()
    result = await statuses(env.store)
    assert result == {
        "id1": "done",
        "id2": "failed",
        "id3": "done",
        "id4": "failed",
        "id5": "done",
    }
    errors = {i.id: i.error for i in await env.store.list_queue()}
    assert errors["id2"].startswith("unavailable: ")
    assert errors["id4"].startswith("unknown: ")


async def _none_pending(store):
    return all(s in ("done", "failed") for s in (await statuses(store)).values())


async def test_recovery_requeues_and_wipes_tmp(env):
    stuck = item(1)
    stuck.status = "downloading"
    await env.store.add_queue_items([stuck, item(2)])
    env.tmp_root.mkdir(parents=True, exist_ok=True)
    (env.tmp_root / "id1").mkdir()
    (env.tmp_root / "id1" / "x.mp3").write_bytes(b"partial")
    (env.tmp_root / "stray.part").write_bytes(b"x")
    w = env()
    assert await w.recover() == 1
    assert await statuses(env.store) == {"id1": "queued", "id2": "queued"}
    assert list(env.tmp_root.iterdir()) == []
    await w.start()
    try:
        await until(lambda: _all(env.store, "done"))
    finally:
        await w.stop()


async def test_network_error_retries_then_succeeds(env):
    clock = [0.0]
    w = env(scenarios={vid(1): "flaky:2"}, backoff=(30.0, 120.0, 600.0), clock=lambda: clock[0])
    await env.store.add_queue_items([item(1)])
    await w.start()
    try:
        await until(lambda: _attempts(env.store, 1))
        queued = (await env.store.list_queue())[0]
        assert queued.status == "queued" and "retry 1 of 3" in queued.error
        # Not eligible until the backoff has elapsed on the (fake) clock.
        w.wake()
        await asyncio.sleep(0.2)
        assert (await env.store.list_queue())[0].attempts == 1
        clock[0] = 31.0
        w.wake()
        await until(lambda: _attempts(env.store, 2))
        clock[0] = 31.0 + 121.0
        w.wake()
        await until(lambda: _all(env.store, "done"))
    finally:
        await w.stop()
    final = (await env.store.list_queue())[0]
    assert final.attempts == 3 and final.error is None


async def _attempts(store, n):
    queue = await store.list_queue()
    return queue[0].attempts == n and queue[0].status == "queued"


async def test_network_error_gives_up_after_three_retries(env):
    clock = [0.0]
    w = env(scenarios={vid(1): "flaky:99"}, backoff=(1.0, 2.0, 3.0), clock=lambda: clock[0])
    await env.store.add_queue_items([item(1)])
    await w.start()
    try:
        for n in (1, 2, 3):
            await until(lambda n=n: _attempts(env.store, n))
            clock[0] += 10.0
            w.wake()
        await until(lambda: _none_pending(env.store))
    finally:
        await w.stop()
    final = (await env.store.list_queue())[0]
    assert (final.status, final.attempts) == ("failed", 4)
    assert final.error.startswith("network: ")


async def test_non_network_error_fails_immediately(env):
    w = env(scenarios={vid(1): "error:private"})
    await env.store.add_queue_items([item(1)])
    await w.start()
    try:
        await until(lambda: _none_pending(env.store))
    finally:
        await w.stop()
    final = (await env.store.list_queue())[0]
    assert (final.status, final.attempts) == ("failed", 1)


async def test_shutdown_requeues_active_item_quickly(env):
    w = env(scenarios={vid(1): "hang"})
    await env.store.add_queue_items([item(1), item(2)])
    await w.start()
    await until(lambda: _started(env.state_dir, vid(1)))
    loop = asyncio.get_running_loop()
    began = loop.time()
    await w.stop()
    assert loop.time() - began < 5
    queue = await env.store.list_queue()
    assert [(i.status, i.attempts) for i in queue] == [("queued", 0), ("queued", 0)]
    assert list(env.tmp_root.iterdir()) == []
    assert list(env.music.iterdir()) == []


async def _started(state_dir, video_id):
    return (state_dir / f"start_{video_id}").exists()


@pytest.mark.parametrize("concurrency", [1, 2])
async def test_concurrency_limit(env, concurrency):
    w = env(
        scenarios={vid(1): "slow:0.6", vid(2): "slow:0.6"},
        concurrency=concurrency,
    )
    await env.store.add_queue_items([item(1), item(2)])
    peak = 0
    await w.start()
    try:
        while not await _all(env.store, "done"):
            peak = max(peak, len(w.active_ids))
            await asyncio.sleep(0.02)
    finally:
        await w.stop()
    assert peak == concurrency


async def test_skips_download_when_file_already_there(env, sample_mp3):
    target = env.music / "geek"
    target.mkdir()
    existing = target / "Known.mp3"
    shutil.copy(sample_mp3, existing)
    tagging.write_tags(existing, "Known", "Band", vid(1), "https://u", None)
    queued = item(1, subfolder="geek")
    queued.title = "Known"
    await env.store.add_queue_items([queued])
    # A scenario that would fail proves the runner is never started.
    w = env(scenarios={vid(1): "error:unknown"})
    await w.start()
    try:
        await until(lambda: _none_pending(env.store))
    finally:
        await w.stop()
    final = (await env.store.list_queue())[0]
    assert final.status == "done" and final.attempts == 1
    track = await env.store.get_track(vid(1))
    assert track.relpath == "geek/Known.mp3" and track.artist == "Band"
    assert not (env.state_dir / f"start_{vid(1)}").exists()


async def test_overwrite_flag_redownloads(env, sample_mp3):
    existing = env.music / "Known.mp3"
    shutil.copy(sample_mp3, existing)
    tagging.write_tags(existing, "Known", "Old", vid(1), "https://u", None)
    queued = item(1, overwrite=True)
    queued.title = "Known"
    await env.store.add_queue_items([queued])
    w = env(titles={vid(1): "Known"})
    await w.start()
    try:
        await until(lambda: _all(env.store, "done"))
    finally:
        await w.stop()
    assert tagging.read_tags(existing).artist == "Some Artist"


async def test_pauses_after_repeated_disk_failures(env):
    w = env(scenarios={vid(n): "error:disk_full" for n in range(1, 5)})
    await env.store.add_queue_items([item(n) for n in range(1, 5)])
    await w.start()
    try:
        await until(lambda: _paused(w))
        await asyncio.sleep(0.2)
        result = await statuses(env.store)
        assert list(result.values()).count("failed") == 3
        assert result["id4"] == "queued"
        w.resume()
        await until(lambda: _none_pending(env.store))
    finally:
        await w.stop()


async def _paused(w):
    return w.paused_reason is not None


async def test_progress_events_are_throttled_per_item(env):
    from webmusicfolder.queue_worker import PROGRESS_INTERVAL_S

    now = [0.0]
    w = env(clock=lambda: now[0])
    for i in range(10):
        now[0] = i * 0.1
        w._on_runner_event("a", {"type": "progress", "pct": i})
    progress = [p for k, p in w.events if k == "progress"]
    # 1 s window: only the first of the burst passes, the next one at t >= 1 s.
    assert [p["pct"] for p in progress] == [0]
    now[0] = PROGRESS_INTERVAL_S + 0.5
    w._on_runner_event("a", {"type": "progress", "pct": 99})
    w._on_runner_event("b", {"type": "progress", "pct": 1})
    w._on_runner_event("a", {"type": "stage", "stage": "tagging"})
    assert [p["pct"] for k, p in w.events if k == "progress" and "pct" in p] == [0, 99, 1]
    assert w.progress["a"]["type"] == "stage"


async def test_fast_runner_emits_few_progress_events(env):
    w = env(titles={vid(1): "One"})
    await env.store.add_queue_items([item(1)])
    await w.start()
    try:
        await until(lambda: _all(env.store, "done"))
    finally:
        await w.stop()
    assert len([1 for k, _ in w.events if k == "progress"]) <= 3
    assert w.progress == {}


async def test_retry_requeues_failed_item_with_fresh_budget(env):
    w = env(scenarios={vid(1): "error:private"})
    await env.store.add_queue_items([item(1)])
    await w.start()
    try:
        await until(lambda: _all(env.store, "failed"))
        await w.stop()
        queued = await w.retry("id1")
        assert (queued.status, queued.error, queued.attempts) == ("queued", None, 0)
        assert queued.finished_at is None
        with pytest.raises(ValueError):
            await w.retry("id1")
    finally:
        await w.stop()


async def test_cancel_unknown_raises_key_error(env):
    w = env()
    with pytest.raises(KeyError):
        await w.cancel("nope")


@pytest.mark.parametrize("enabled", [False, True])
async def test_sponsorblock_setting_reaches_the_runner(env, enabled):
    await env.store.update_settings(sponsorblock=enabled)
    w = env()
    await env.store.add_queue_items([item(1)])
    await w.start()
    try:
        await until(lambda: _all(env.store, "done"))
    finally:
        await w.stop()
    flag = (env.state_dir / f"sponsorblock_{vid(1)}").read_text()
    assert flag == str(enabled)


async def _run_one(env, **setting):
    await env.store.update_settings(**setting)
    w = env(titles={vid(1): "One"})
    await env.store.add_queue_items([item(1)])
    await w.start()
    try:
        await until(lambda: _all(env.store, "done"))
    finally:
        await w.stop()
    return env.music / "One.mp3"


async def test_replaygain_on_writes_tags_without_touching_the_audio(env, sample_mp3):
    from mutagen.mp3 import MP3

    path = await _run_one(env, replaygain=True)
    tags = tagging.ID3(path)
    assert str(tags["TXXX:REPLAYGAIN_TRACK_GAIN"].text[0]).endswith(" dB")
    assert 0 <= float(str(tags["TXXX:REPLAYGAIN_TRACK_PEAK"].text[0])) <= 1
    assert tagging.read_tags(path).title == "One"
    # The audio frames are those of the source file.
    assert abs(MP3(path).info.length - MP3(sample_mp3).info.length) < 0.01


async def test_replaygain_off_adds_no_tags(env):
    path = await _run_one(env)
    assert "TXXX:REPLAYGAIN_TRACK_GAIN" not in tagging.ID3(path)


async def test_replaygain_failure_keeps_the_track(env, monkeypatch):
    from webmusicfolder import loudness

    async def boom(_path):
        raise loudness.LoudnessError("no ffmpeg")

    monkeypatch.setattr(loudness, "measure", boom)
    path = await _run_one(env, replaygain=True)
    assert path.is_file()
    assert "TXXX:REPLAYGAIN_TRACK_GAIN" not in tagging.ID3(path)


async def test_final_progress_is_not_throttled_and_none_keeps_last_value(env):
    now = [0.0]
    w = env(clock=lambda: now[0])
    w._on_runner_event("a", {"type": "progress", "pct": 40.0, "speed": 1.0})
    now[0] = 0.1
    w._on_runner_event("a", {"type": "progress", "pct": 100.0})
    assert [p["pct"] for k, p in w.events if k == "progress"] == [40.0, 100.0]
    now[0] = 5.0
    w._on_runner_event("a", {"type": "progress", "pct": None, "speed": 2.0})
    assert w.progress["a"]["pct"] == 100.0
