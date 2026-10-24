# F008: Library page

- Status: done (browser check of the UI pending)
- Phase: 1
- Depends on: f002, f003
- Requirements: FR-15, FR-16, FR-17

## Goal
Browse every MP3 in the music dir with cover and details, and see whether each came from the app or from elsewhere.

## Description
`library.py` walks the music dir (not following symlinks out of it), reads tags with mutagen and builds entries: cover, title, artist, album, duration, size, subfolder, source. Source is `App` when the file's video ID tag matches a Track in state, otherwise `External`. For External files with missing tags: title from file name, other fields `Unknown`. Results are cached by `(path, mtime, size)`. The page has a search box, subfolder and source filters, a rescan button, and a cover endpoint that extracts the APIC frame (placeholder when none).

## Acceptance criteria
- [x] 500 files list in under 2 s after the first scan; second load under 300 ms.
- [x] Tagless `foo.mp3` shows title `foo` and artist `Unknown`.
- [x] App downloads show `App`, files copied in by hand show `External`.
- [x] Search filters title and artist; filters by subfolder and source work together.
- [x] A symlink pointing outside the music dir is not followed.

## Steps
- [x] f008.s1: scan and entry building with fallbacks (verify: unit tests with generated MP3 fixtures, tagless, partial tags, corrupt file)
- [x] f008.s2: source detection and cache invalidation (verify: tests for App and External, mtime change)
- [x] f008.s3: cover endpoint with size limit and placeholder (verify: TestClient returns image and placeholder, traversal rejected)
- [x] f008.s4: library page, grid or table, filters and search (verify: manual with a mixed folder, 360 px and 1440 px)
- [x] f008.s5: rescan button and auto refresh after downloads (verify: manual)

## Test plan
Fixture generated MP3s via ffmpeg or mutagen; TestClient for endpoints; manual UI check.

## Notes
Scanning runs in a thread pool so the event loop stays responsive. Only `.mp3` is indexed in the MVP.
