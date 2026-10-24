# F004: Queue worker, persistence and crash resume

- Status: done
- Phase: 1
- Depends on: f003
- Requirements: FR-10, FR-11, FR-12, FR-23, NFR-01, NFR-02, NFR-11, NFR-12

## Goal
A background worker that processes the persisted queue without any browser, survives crashes and reboots, and costs nothing at idle.

## Description
`queue_worker.py` runs in the FastAPI lifespan. It waits on an `asyncio.Event` (no polling), picks `queued` items (up to `WMF_CONCURRENCY`), runs `download_one()`, updates state on every transition and registers the Track on success. Startup recovery resets `downloading` to `queued` and wipes `/data/tmp`. SIGTERM handling interrupts the runner and requeues the item. Network errors retry with backoff; other errors mark the item `failed` and the worker continues.

## Acceptance criteria
- [x] Items queued via the store are processed with no browser open.
- [x] Kill -9 during a download, restart: the item completes, file is complete and tagged.
- [x] `docker stop` completes in under 10 s and the item resumes on next start. (Docker: stop took 360 ms; idle 41 MiB, 0.09% CPU, 3 pids; resume covered by the kill -9 test.)
- [x] One failing item does not block the others.
- [x] With an empty queue no child process exists and CPU stays near 0.
- [x] Concurrency setting is honoured.

## Steps
- [x] f004.s1: worker loop with Event wakeup and state transitions (verify: tests with fake runner, order and statuses)
- [x] f004.s2: startup recovery and tmp cleanup (verify: test seeds state with `downloading` item and stray tmp files)
- [x] f004.s3: retry with backoff for network errors, immediate fail for others (verify: tests with scripted errors and a fake clock)
- [x] f004.s4: graceful shutdown and requeue (verify: test sending cancellation, item back to `queued`)
- [x] f004.s5: concurrency limit (verify: test with 2 slow items and concurrency 1 vs 2)
- [x] f004.s6: crash test and idle measurement (verify: kill -9 integration test; `docker stats` and `pgrep` at idle recorded in progress.md)

Results: `tests/crash/test_worker_crash.py` passes. Idle measured locally (no Docker, uvicorn started from the venv): RSS 51 MB, CPU time 0 s over 20 s, no child processes. `docker stats` and `docker stop` timing still to be measured where Docker works.

## Test plan
Fake runner scripts for success, slow, error, hang. Integration crash test using a subprocess. Manual idle measurement.

## Notes
Maintain a `resume_count` in logs only; do not add fields to state for it. Skip completed work: if the final file for an item already exists and its video ID tag matches, mark done without redownloading.
