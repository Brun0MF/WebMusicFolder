# F017: Manual import of External files into the App index

- Status: done (browser check pending)
- Phase: 2
- Depends on: f008
- Requirements: new FR-28

## Goal
Let a file that was not downloaded by the app become an `App` file, so duplicate detection recognises it and a later submit of the same link offers skip or redownload.

## Description
The App index identifies a file by the video id in its tags and a Track in state. An External file has neither, so the user supplies the YouTube link. In the Library, an External row has a "Link to YouTube" action: the user pastes a video link, the server validates it, adds only the `youtube_id` and `youtube_url` frames to the file (title, artist, cover and all other frames stay as they are), and registers a Track built from the file's tags. The tag write is done on a copy and swapped with an atomic rename, so a crash never leaves a half written file. The file is not moved or renamed.

## Acceptance criteria
- [x] Linking an External file turns it into `App` and a repeat submit of that link shows the duplicate dialog.
- [x] Only the two custom frames are added; other tags are byte for byte equal in a read back.
- [x] Playlist links, invalid links and video ids already owned by another file are rejected (422 or 409) with a message.
- [x] Paths are validated inside the music dir; non MP3 and missing files are 404.
- [x] A failure while writing leaves the original file untouched.

## Steps
- [x] f017.s1: `importer.py` tag write on a copy with atomic swap, Track builder (verify: unit tests incl. failure injection)
- [x] f017.s2: `POST /api/library/link` with validation and cache invalidation (verify: integration tests)
- [x] f017.s3: Library UI action on External rows (verify: manual, browser check)

## Test plan
Unit and integration tests with generated MP3s, including traversal and conflict cases.

## Notes
Automatic matching by title is out of scope; it would guess and modify files silently.
