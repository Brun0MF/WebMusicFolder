import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from webmusicfolder import tagging
from webmusicfolder.models import QueueItem
from webmusicfolder.store import StateStore

SCRIPT = Path(__file__).with_name("worker_proc.py")
SRC = str(Path(__file__).resolve().parents[2] / "src")
VIDEO_ID = "crashvid001"


def wait_for(predicate, timeout=20.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError("condition not reached in time")


def test_sigkill_mid_download_resumes_and_completes(tmp_path, sample_mp3):
    data, music, fake_state = tmp_path / "data", tmp_path / "music", tmp_path / "fake"
    for d in (data, music, fake_state):
        d.mkdir()
    store = StateStore(data / "state.json")
    store.load()
    asyncio.run(
        store.add_queue_items(
            [
                QueueItem(
                    id="i1",
                    video_id=VIDEO_ID,
                    url=f"https://www.youtube.com/watch?v={VIDEO_ID}",
                    title="",
                    subfolder="geek",
                    added_at="2026-10-24T00:00:00Z",
                )
            ]
        )
    )
    env = {
        **os.environ,
        "PYTHONPATH": SRC,
        "FAKE_MP3": str(sample_mp3),
        "FAKE_STATE_DIR": str(fake_state),
        "FAKE_TITLES": json.dumps({VIDEO_ID: "Survivor"}),
        "FAKE_SCENARIOS": json.dumps({VIDEO_ID: "slow:30"}),
    }

    def spawn(env):
        return subprocess.Popen(
            [sys.executable, str(SCRIPT), str(data), str(music)],
            env=env,
            stdout=subprocess.PIPE,
            start_new_session=True,
        )

    first = spawn(env)
    first.stdout.readline()
    wait_for(lambda: (fake_state / f"start_{VIDEO_ID}").exists())
    # kill -9 takes the whole group down like a container dying.
    os.killpg(first.pid, signal.SIGKILL)
    first.wait()
    first.stdout.close()

    reloaded = StateStore(data / "state.json")
    reloaded.load()
    assert asyncio.run(reloaded.list_queue())[0].status == "downloading"
    assert not list(music.rglob("*.mp3"))

    second = spawn({**env, "FAKE_SCENARIOS": "{}"})
    second.stdout.readline()
    try:
        final = music / "geek" / "Survivor.mp3"
        wait_for(final.exists)
        wait_for(lambda: _status(data) == "done")
    finally:
        os.killpg(second.pid, signal.SIGKILL)
        second.wait()
        second.stdout.close()
    info = tagging.read_tags(final)
    assert (info.title, info.video_id, info.has_cover) == ("Survivor", VIDEO_ID, True)
    assert list((data / "tmp").iterdir()) == []


def _status(data):
    store = StateStore(data / "state.json")
    store.load()
    return asyncio.run(store.list_queue())[0].status
