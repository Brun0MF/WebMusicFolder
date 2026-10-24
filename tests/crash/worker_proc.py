"""Run a QueueWorker with the fake runner until killed. Used by test_worker_crash.py.

Usage: worker_proc.py DATA_DIR MUSIC_DIR
Reads the FAKE_* environment of tests/fixtures/fake_runner.py.
"""

import asyncio
import sys
from pathlib import Path

from webmusicfolder.downloader import DownloadContext
from webmusicfolder.queue_worker import QueueWorker
from webmusicfolder.runner_client import RunnerSpec
from webmusicfolder.store import StateStore

FAKE = Path(__file__).parents[1] / "fixtures" / "fake_runner.py"


async def main(data_dir: Path, music_dir: Path) -> None:
    store = StateStore(data_dir / "state.json")
    store.load()
    ctx = DownloadContext(
        music_dir=music_dir,
        tmp_root=data_dir / "tmp",
        runner=RunnerSpec(cmd=(sys.executable, str(FAKE))),
    )
    worker = QueueWorker(store, ctx)
    await worker.recover()
    await worker.start()
    print("ready", flush=True)
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1]), Path(sys.argv[2])))
