# F010: yt-dlp update button

- Status: done (browser check pending)
- Phase: 1
- Depends on: f001, f003
- Requirements: FR-20

## Goal
Update yt-dlp from the UI so a YouTube breakage does not need an image rebuild.

## Description
`ytdlp_update.py` runs `python -m pip install --upgrade --target /data/ytdlp_pkg yt-dlp` in a subprocess and reports the old and new version. The runner prefixes `PYTHONPATH` with that directory when it exists, so the next download uses the new version with no reload. The Settings page shows the current version, a button, and the result or error. Updates are refused while the queue is downloading (or wait for it to be idle).

## Acceptance criteria
- [x] Clicking the button shows old and new version; after an update the displayed version equals the latest PyPI release. (API; the real run installed 2026.10.21, which was already the latest; button awaits the browser check)
- [x] The next download uses the new version. (the runner prefixes PYTHONPATH with the data package; covered by tests)
- [x] A failed update (offline) leaves the previous working version in place and shows the error.
- [x] The package survives container recreation (stored in the data volume). (Docker verified)
- [x] Only one update runs at a time.

## Steps
- [x] f010.s1: version query via runner (verify: unit test with fake runner, manual real version)
- [x] f010.s2: update into a temp target then swap into `/data/ytdlp_pkg` (verify: test with fake pip, failure keeps old dir)
- [x] f010.s3: runner uses the data package first (verify: test that PYTHONPATH is set when the dir exists)
- [x] f010.s4: Settings UI button, spinner, result (verify: manual; browser check pending)

## Test plan
Fake pip script for success and failure; manual real update in Docker, then recreate the container and check the version persists.

## Notes
`pip` is now a runtime dependency because the uv virtualenv ships without it. While an update runs (and when downloads are active) the worker is held with `QueueWorker.exclusive()`, so no runner imports yt-dlp modules from a directory being replaced.
Installing to a temp dir first and swapping makes the update atomic. The pip invocation uses the image's Python and needs outbound HTTPS to PyPI.
