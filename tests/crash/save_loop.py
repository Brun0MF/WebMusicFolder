"""Child process for the crash test: saves state in a tight loop until killed."""

import asyncio
import sys
from pathlib import Path

from webmusicfolder.models import QueueItem
from webmusicfolder.store import StateStore


async def main(path: str) -> None:
    store = StateStore(Path(path))
    store.load()
    n = 0
    print("ready", flush=True)
    while True:
        n += 1
        item = QueueItem(
            id=str(n),
            video_id=f"v{n}",
            url="u" * 200,
            title="t" * 200,
            subfolder="",
            added_at="2026-10-24T00:00:00Z",
        )
        await store.add_queue_items([item])
        # Keep the file small enough that each write stays fast.
        if n % 50 == 0:
            await store.mutate(lambda s: s.queue.clear())


asyncio.run(main(sys.argv[1]))
