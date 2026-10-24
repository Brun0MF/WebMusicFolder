# F002: JSON state store

- Status: done
- Phase: 1
- Depends on: f001
- Requirements: FR-03

## Goal
A safe single-file JSON store for tracks, queue and settings.

## Description
`models.py` dataclasses and `store.py` with load, typed accessors, one asyncio lock and atomic save (tmp file, fsync, `os.replace`). Hourly `.bak` copy. Schema `version` field with a migration hook. Corrupt file raises a clear error and is never overwritten.

## Acceptance criteria
- [x] A fresh data dir creates a valid empty `state.json`.
- [x] Killing a process during saves 1000 times never leaves invalid JSON.
- [x] Corrupt `state.json` raises `StateCorruptError` and the file is untouched.
- [x] Concurrent mutations from several tasks do not lose updates.
- [x] Done queue items older than 7 days are pruned on load.

## Steps
- [x] f002.s1: models and JSON (de)serialisation (verify: round-trip unit tests)
- [x] f002.s2: atomic save and load (verify: unit tests, fsync and replace used)
- [x] f002.s3: lock and typed accessors for tracks, queue, settings (verify: concurrency test with 50 tasks)
- [x] f002.s4: backup and corruption handling and version field (verify: tests with truncated and invalid files)
- [x] f002.s5: crash simulation (verify: subprocess killed at random points over 1000 runs, state always loads)

## Test plan
Pure unit tests with `tmp_path`; one slow marked crash test.

## Notes
Progress percentages are not stored here (memory only) to avoid disk writes at 1 Hz.

## Implementation notes
- `QueueItem.finished_at` added (not in the original data model) so pruning uses the finish time.
- Mutations run on a deep copy that is saved first and published after, so a failed save never desyncs memory and disk.
- The 1000 kill crash test is marked `slow` and excluded from `scripts/check.sh`; run it with `uv run pytest -m slow` (about 2 minutes).
