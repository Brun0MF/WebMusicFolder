# F007: Live downloads list with progress (SSE)

- Status: done (browser check of the UI pending)
- Phase: 1
- Depends on: f004, f005
- Requirements: FR-14, NFR-01

## Goal
Show active, queued and finished items live, with progress bars and a remaining counter, at no cost when nobody is watching.

## Description
`events.py` provides an in-process pub/sub. `/events` streams SSE with item state changes and throttled progress (max 1 per second per item). The Downloads page shows a summary ("3 of 20 done, 17 remaining"), per item title, status, progress bar, speed and ETA, and buttons to cancel and retry. A reconnecting client first receives a full snapshot.

## Acceptance criteria
- [x] Progress updates at least once per second during a download.
- [x] The remaining counter decreases as items finish.
- [x] Opening the page mid download shows the current state immediately.
- [x] With no clients connected, no events are queued or generated beyond state changes.
- [x] A slow or dead client does not slow the worker.

## Steps
- [x] f007.s1: `events.py` pub/sub with bounded client queues (verify: unit tests for fan-out and drop of slow client)
- [x] f007.s2: `/events` SSE with snapshot on connect and keepalive (verify: TestClient stream test)
- [x] f007.s3: throttled progress publishing from the worker (verify: test counts events for a fast runner)
- [x] f007.s4: Downloads page list, progress bars and summary (verify: manual with a 10 item playlist)
- [x] f007.s5: cancel and retry buttons wired to the API (verify: manual and TestClient tests)

## Test plan
Unit tests for events, stream tests, manual run with a playlist.

## Notes
Keepalive comment every 15 s so proxies do not close the stream; this is the only periodic work and only while a client is connected.
