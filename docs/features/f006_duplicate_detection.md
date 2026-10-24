# F006: Duplicate detection and skip or redownload dialog

- Status: done (browser check of the dialog pending)
- Phase: 1
- Depends on: f005
- Requirements: FR-13

## Goal
Tell the user which links are already in the library and let them skip or redownload.

## Description
The preview response marks each resolved video that exists in `tracks` and whose file still exists on disk. The UI shows a dialog listing duplicates with the existing path, with choices per item and bulk buttons "Skip all" and "Redownload all". Redownload sets `overwrite=true` on the queue item and replaces the file at the same path. Tracks whose file was deleted are not duplicates.

## Acceptance criteria
- [x] A known link shows the dialog; skip adds 0 items.
- [x] Redownload adds 1 item and the old file is replaced only after the new one is complete.
- [x] A track whose file was removed from disk is treated as new.
- [x] Items already queued or downloading are reported as "already in queue".
- [x] External files (not tracked by the app) never trigger the dialog.

## Steps
- [x] f006.s1: duplicate check function against store and filesystem (verify: unit tests for present, missing file, in queue)
- [x] f006.s2: preview response includes duplicates (verify: TestClient test)
- [x] f006.s3: dialog UI with per item and bulk choices (verify: manual with a real duplicate)
- [x] f006.s4: overwrite flow in `download_one()` (verify: test that the old file stays until the new one is ready)

## Test plan
Unit and TestClient tests, one manual end to end duplicate scenario.

## Notes
Overwrite keeps the same filename, so players and playlists pointing at it keep working.
