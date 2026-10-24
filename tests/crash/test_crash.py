import contextlib
import os
import random
import signal
import subprocess
import sys
from pathlib import Path

import pytest

from webmusicfolder.store import StateStore

SCRIPT = Path(__file__).with_name("save_loop.py")
SRC = str(Path(__file__).resolve().parents[2] / "src")
RUNS = 1000


@pytest.mark.slow
def test_state_always_loads_after_sigkill(tmp_path):
    rng = random.Random(1234)
    env = {**os.environ, "PYTHONPATH": SRC}
    for run in range(RUNS):
        # A fresh directory every 10th run also covers kills during first creation.
        data = tmp_path / ("fresh" + str(run) if run % 10 == 0 else "shared")
        data.mkdir(exist_ok=True)
        path = data / "state.json"
        proc = subprocess.Popen(
            [sys.executable, str(SCRIPT), str(path)],
            env=env,
            stdout=subprocess.PIPE,
        )
        # Wait for startup, then let it write for a random short time.
        proc.stdout.readline()
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=rng.uniform(0.0, 0.03))
        proc.send_signal(signal.SIGKILL)
        proc.wait()
        proc.stdout.close()
        if path.exists():
            StateStore(path).load()
