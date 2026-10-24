"""Stand in for `python -m pip` in update tests.

Usage mirrors pip: install ... --target DIR ... yt-dlp
Environment FAKE_PIP: "ok:<version>" writes DIR/version.txt (read by fake_runner),
"nothing" succeeds but creates no target, "broken" installs a package the runner rejects,
"fail" exits 1 with an error,
"slow:<seconds>" sleeps then behaves like ok:9999.
"""

import os
import sys
import time
from pathlib import Path


def main(argv):
    target = Path(argv[argv.index("--target") + 1])
    mode, _, arg = os.environ.get("FAKE_PIP", "ok:2099.01.01").partition(":")
    if mode == "fail":
        sys.stderr.write("ERROR: Could not find a version that satisfies the requirement yt-dlp\n")
        return 1
    if mode == "slow":
        time.sleep(float(arg))
        arg = "9999"
    if mode == "nothing":
        return 0
    target.mkdir(parents=True, exist_ok=True)
    if mode == "broken":
        (target / "broken.txt").write_text("")
    else:
        (target / "version.txt").write_text(arg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
